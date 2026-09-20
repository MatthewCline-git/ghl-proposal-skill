#!/usr/bin/env python3
"""Turn a proposal spec into a real GoHighLevel proposal document (or estimate),
verify it landed, and leave a run log. Claude drafts the spec from what the user
said; this script does everything that must not be improvised: API calls,
retries, duplicate guard, verification, alerting.

  create_proposal.py spec.json [--dry-run] [--send] [--run-id ID]
                               [--inject transient|hard]

stdout is one JSON object (the result). Progress goes to stderr.
Exit codes: 0 ok · 1 failed after alerting · 2 the spec itself is bad.
"""
from __future__ import annotations

import argparse
import html
import os
import json
import re
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: E402

_env.load()

import document_mode  # noqa: E402
import runlog  # noqa: E402
from errors import SetupError, SpecError, VerifyError  # noqa: E402
from ghl import GHL, GHLError  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent
LIVE = True
UNDELIVERABLE = ("example.com", "example.org", "example.net", ".test", ".invalid", ".localhost")


def say(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- spec
def load_defaults() -> dict:
    d = json.loads(Path(os.environ.get("GHL_PROPOSAL_DEFAULTS") or SKILL_DIR / "defaults.json").read_text())
    d.setdefault("currency", "USD")
    d.setdefault("valid_days", 14)
    d.setdefault("terms", [])
    return d


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1_000_000


def validate_spec(spec: dict, fmt: str, defaults: dict) -> None:
    errs: list[str] = []
    c = spec.get("client") or {}
    for k in ("name", "company", "email"):
        if not str(c.get(k, "")).strip():
            errs.append(f"client.{k} is required")
    if c.get("email") and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", c["email"]):
        errs.append(f"client.email {c['email']!r} is not an email address")
    intro = spec.get("intro", "")
    if not isinstance(intro, str) or not 20 <= len(intro.strip()) <= 900:
        errs.append("intro must be 20-900 characters: what we heard and why this scope")
    if fmt == "document":
        scope = spec.get("scope")
        if not isinstance(scope, list) or not 1 <= len(scope) <= 12 or not all(
                isinstance(x, str) and 0 < len(x.strip()) <= 400 for x in scope):
            errs.append("scope must be a list of 1-12 deliverable lines (each up to 400 characters)")
        if not _num(spec.get("total")):
            errs.append("total is required: the price as a number the user gave (0 is allowed)")
    else:
        items = spec.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= 10:
            errs.append("items must be a list of 1-10 entries")
            items = []
        for i, it in enumerate(items):
            if not str(it.get("name", "")).strip():
                errs.append(f"items[{i}].name is required")
            if not _num(it.get("amount")):
                errs.append(f"items[{i}].amount is required: a number the user gave")
            if not isinstance(it.get("qty", 1), int) or not 1 <= it.get("qty", 1) <= 20:
                errs.append(f"items[{i}].qty must be an integer 1-20")
        n = spec.get("estimate_number")
        if n is not None and (isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 999_999):
            errs.append("estimate_number must be an integer 1-999999 (GHL rejects one already in use)")
    terms = spec["terms"] if "terms" in spec else defaults["terms"]
    if not isinstance(terms, list) or not terms or not all(isinstance(t, str) and t.strip() for t in terms):
        errs.append("terms are required: the user's payment/other terms for this proposal "
                    "(or save default terms in defaults.json)")
    vd = spec.get("valid_days", defaults["valid_days"])
    if isinstance(vd, bool) or not isinstance(vd, int) or not 1 <= vd <= 365:
        errs.append("valid_days must be an integer 1-365")
    for a in spec.get("assumptions", []):
        if not isinstance(a, str) or not a.strip():
            errs.append("assumptions must be non-empty strings")
    if errs:
        raise SpecError("; ".join(errs))


def terms_of(spec: dict, defaults: dict) -> list[str]:
    return list(spec["terms"] if "terms" in spec else defaults["terms"])


def estimate_lines(spec: dict, defaults: dict) -> tuple[list[dict], float]:
    lines = [{"name": it["name"].strip(), "description": (it.get("description") or "").strip(),
              "currency": defaults["currency"], "amount": it["amount"], "qty": it.get("qty", 1),
              "type": "one_time"} for it in spec["items"]]
    return lines, sum(l["amount"] * l["qty"] for l in lines)


def terms_html(spec: dict, defaults: dict) -> str:
    esc = html.escape
    out = [f"<p>{esc(spec['intro'].strip())}</p>"]
    if spec.get("assumptions"):
        out.append("<h4>Assumptions</h4><ul>" + "".join(f"<li>{esc(a)}</li>" for a in spec["assumptions"]) + "</ul>")
    out.append("<h4>Terms</h4><ul>" + "".join(f"<li>{esc(t)}</li>" for t in terms_of(spec, defaults)) + "</ul>")
    return "".join(out)


# ---------------------------------------------------------------- stages
@contextmanager
def stage(run_id: str, name: str, stages: list):
    t0 = time.time()
    say(f"  … {name}")
    try:
        yield
    except Exception as exc:
        ms = int((time.time() - t0) * 1000)
        stages.append({"stage": name, "ok": False, "ms": ms})
        runlog.event(run_id, "stage", stage=name, ok=False, ms=ms, error=str(exc)[:300])
        say(f"  ✗ {name}: {exc}")
        exc.stage = name  # type: ignore[attr-defined]
        raise
    ms = int((time.time() - t0) * 1000)
    stages.append({"stage": name, "ok": True, "ms": ms})
    runlog.event(run_id, "stage", stage=name, ok=True, ms=ms)
    say(f"  ✓ {name} ({ms}ms)")


def fit(text: str, limit: int = 40) -> str:
    """GHL rejects estimate titles over 40 characters too."""
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def estimate_name(company: str, run_id: str) -> str:
    """GHL rejects estimate names over 40 characters (a real 422, found in the live test)."""
    suffix = f" — {run_id}"
    return company[: 40 - len(suffix)].rstrip() + suffix


def find_estimate(ghl: GHL, run_id: str) -> dict | None:
    hits = [e for e in ghl.list_estimates(search=run_id)
            if (e.get("meta") or {}).get("runId") == run_id and not e.get("deleted")]
    if len(hits) > 1:
        raise VerifyError(f"{len(hits)} estimates carry run id {run_id}; expected at most 1")
    return hits[0] if hits else None


def create_estimate(ghl: GHL, body: dict, run_id: str, counters: dict) -> dict:
    """Create once, however many retries it takes. Before every attempt, check
    whether a previous attempt (or a previous run with this id) already made
    it — a 5xx can hide a successful write, and a duplicate proposal in front
    of a customer is worse than a failure."""
    for attempt in range(1, 5):
        existing = find_estimate(ghl, run_id)
        if existing:
            say(f"    estimate already exists for {run_id}; not creating a duplicate")
            return existing
        try:
            return ghl.create_estimate(body)
        except GHLError as exc:
            if not exc.retryable or attempt == 4:
                raise
            counters["retries"] += 1
            wait = ghl.backoff(attempt)
            say(f"    transient failure ({exc}); retry {attempt}/3 in {wait:g}s")
            runlog.event(run_id, "retry", attempt=attempt, error=str(exc)[:200])
            time.sleep(wait)
    raise AssertionError("unreachable")


def verify(ghl: GHL, run_id: str, *, contact_id: str, lines: list[dict], total: float,
           intro: str, want_status: set[str]) -> dict:
    e = find_estimate(ghl, run_id)
    if not e:
        raise VerifyError(f"no estimate with run id {run_id} found in GHL after create")
    problems = []
    if (e.get("contactDetails") or {}).get("id") != contact_id:
        problems.append("attached to the wrong contact")
    if round(float(e.get("total", -1)) * 100) != round(total * 100):
        problems.append(f"total is {e.get('total')}, expected {total}")
    got = [(i["name"], i["amount"], i["qty"]) for i in e.get("items", [])]
    want = [(l["name"], l["amount"], l["qty"]) for l in lines]
    if got != want:
        problems.append(f"line items differ: got {got}, expected {want}")
    rendered = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", e.get("termsNotes") or "")).split())
    if " ".join(intro.split()) not in rendered:
        problems.append("intro text missing from the estimate's notes")
    if e.get("estimateStatus") not in want_status:
        problems.append(f"status is {e.get('estimateStatus')!r}, expected one of {sorted(want_status)}")
    if problems:
        raise VerifyError("; ".join(problems))
    return e


RUNBOOK = {401: "§1 credentials", 403: "§1 credentials", 400: "§2 payload rejected", 422: "§2 payload rejected"}


def runbook_ref(exc: Exception) -> str:
    if isinstance(exc, VerifyError):
        return "§4 verification mismatch"
    if isinstance(exc, GHLError):
        if exc.status in RUNBOOK:
            return RUNBOOK[exc.status]
        if exc.retryable:
            return "§3 GHL unavailable"
    return "§5 anything else"


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec")
    ap.add_argument("--dry-run", action="store_true", help="validate and price only; touch nothing")
    ap.add_argument("--format", choices=["document", "estimate"],
                    default=os.environ.get("GHL_PROPOSAL_FORMAT", "document"),
                    help="document: fill your GHL proposal template (default). estimate: create a GHL estimate")
    ap.add_argument("--send", action="store_true", help="estimate format only: email it to the client")
    ap.add_argument("--run-id", help="reuse an id to resume a failed run without duplicating anything")
    ap.add_argument("--inject", choices=["transient", "hard"], help="failure demo: fake outage or revoked token")
    args = ap.parse_args()

    run_id = args.run_id or f"p-{uuid.uuid4().hex[:8]}"
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,24}", run_id):
        ap.error("--run-id must be 1-24 letters, digits, - or _")
    stages: list[dict] = []
    counters = {"retries": 0}
    runlog.event(run_id, "start", spec=args.spec, dry_run=args.dry_run, send=args.send, inject=args.inject)
    say(f"run {run_id}")

    try:
        defaults = load_defaults()
        try:
            spec = json.loads(Path(args.spec).read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise SpecError(f"cannot read spec: {exc}")
        with stage(run_id, "validate", stages):
            validate_spec(spec, args.format, defaults)
            if args.format == "estimate":
                lines, total = estimate_lines(spec, defaults)
            else:
                lines, total = [], spec["total"]
        if args.dry_run:
            runlog.event(run_id, "finish", status="dry_run", total=total)
            out = {"status": "dry_run", "run_id": run_id, "format": args.format, "total": total,
                   "terms": terms_of(spec, defaults),
                   "valid_days": spec.get("valid_days", defaults["valid_days"])}
            if args.format == "document":
                out["scope"] = spec["scope"]
            else:
                out["items"] = [{"name": l["name"], "amount": l["amount"], "qty": l["qty"]} for l in lines]
            print(json.dumps(out, indent=2))
            return 0
        if args.send and args.format == "document":
            raise SpecError("--send is for estimates. Documents are created as drafts: review and send them from GHL.")
        if args.send and any(spec["client"]["email"].lower().endswith(d) for d in UNDELIVERABLE):
            raise SpecError(f"refusing to send: {spec['client']['email']} is a placeholder domain that will not deliver")

        try:
            token, loc = _env.need("GHL_TOKEN", "GHL_LOCATION_ID")
        except SystemExit as exc:  # a config problem is a finished run, not a hung one
            runlog.event(run_id, "finish", status="misconfigured", error=str(exc))
            raise
        ghl = GHL(token, loc)
        if args.inject:
            ghl.inject = {"transient": 2} if args.inject == "transient" else {"hard": True}
            say(f"  (failure demo: injecting {args.inject})")

        template = None
        if args.format == "document":
            with stage(run_id, "template", stages):
                template = document_mode.resolve_template(ghl)

        c = spec["client"]
        with stage(run_id, "contact", stages):
            up = ghl.upsert_contact(name=c["name"], email=c["email"], company=c["company"],
                                    phone=c.get("phone", ""))
            contact = up.get("contact") or {}
            if not contact.get("id"):
                raise VerifyError(f"contact upsert returned no id: {list(up)}")
            contact_id, contact_new = contact["id"], bool(up.get("new"))

        if args.format == "document":
            with stage(run_id, "fields", stages):
                ids = document_mode.ensure_fields(ghl)
                values = document_mode.field_values(spec, defaults)
                ghl.set_contact_fields(contact_id, [{"id": ids[k], "field_value": v} for k, v in values.items()])
            with stage(run_id, "document", stages):
                doc, resp = document_mode.create_document(ghl, template, contact_id, run_id, counters)
            with stage(run_id, "verify", stages):
                report = document_mode.verify(ghl, doc["_id"], contact_id=contact_id, template=template,
                                              ids=ids, values=values, resp=resp)
            status = "recovered" if counters["retries"] else "success"
            result = {"status": status, "run_id": run_id, "format": "document", "document_id": doc["_id"],
                      "template": template["name"], "total": total, "currency": defaults["currency"],
                      "contact_id": contact_id,
                      "contact_new": contact_new, "retries": counters["retries"], "sent": False,
                      "document_status": "draft", **report,
                      "next": "Open it in GHL (Payments > Documents & Contracts > Documents), check it, and press Send."}
            runlog.event(run_id, "finish", **{k: v for k, v in result.items() if k != "run_id"},
                         http_attempts=ghl.attempts, stages=stages)
            if status == "recovered":
                runlog.alert(run_id, "info", f"recovered after {counters['retries']} retries; document {doc['_id']} verified.")
            print(json.dumps(result, indent=2))
            return 0

        with stage(run_id, "estimate", stages):
            biz = ghl.location()
            body = {
                "altId": loc, "altType": "location", "liveMode": LIVE, "currency": defaults["currency"],
                "name": estimate_name(c["company"], run_id),
                "title": fit(f"Proposal for {c['company']}"),
                "businessDetails": {k: v for k, v in {"name": biz.get("name"), "phoneNo": biz.get("phone"),
                                                       "website": biz.get("website")}.items() if v},
                "contactDetails": {"id": contact_id, "name": c["name"], "email": c["email"],
                                   "phoneNo": c.get("phone", ""), "companyName": c["company"]},
                "items": lines, "discount": {"type": "percentage", "value": 0},
                "frequencySettings": {"enabled": False, "schedule": {}},
                "termsNotes": terms_html(spec, defaults), "userId": ghl.user_id(),
                "issueDate": date.today().isoformat(),
                "expiryDate": (date.today() + timedelta(days=spec.get("valid_days", defaults["valid_days"]))).isoformat(),
                "meta": {"runId": run_id},
            }
            if spec.get("estimate_number"):
                body["estimateNumber"] = spec["estimate_number"]
            created = create_estimate(ghl, body, run_id, counters)
            estimate_id = created.get("_id")

        with stage(run_id, "verify", stages):
            e = verify(ghl, run_id, contact_id=contact_id, lines=lines, total=total,
                       intro=spec["intro"], want_status={"draft"})

        sent = False
        if args.send:
            with stage(run_id, "send", stages):
                ghl.send_estimate(estimate_id, body["userId"], body["name"])
                verify(ghl, run_id, contact_id=contact_id, lines=lines, total=total,
                       intro=spec["intro"], want_status={"sent", "viewed", "accepted"})
                sent = True

        status = "recovered" if counters["retries"] else "success"
        app = os.environ.get("GHL_APP_URL", "https://app.gohighlevel.com").rstrip("/")
        result = {"status": status, "run_id": run_id,
                  "url": f"{app}/v2/location/{loc}/payments/v2/estimates/edit/{estimate_id}", "estimate_id": estimate_id,
                  "estimate_number": e.get("estimateNumber"), "total": total,
                  "currency": defaults["currency"], "contact_id": contact_id, "contact_new": contact_new,
                  "retries": counters["retries"], "sent": sent, "estimate_status": "sent" if sent else "draft"}
        runlog.event(run_id, "finish", **{k: v for k, v in result.items() if k != "run_id"},
                     http_attempts=ghl.attempts, stages=stages)
        if status == "recovered":
            runlog.alert(run_id, "info", f"recovered after {counters['retries']} retries; estimate {estimate_id} verified.")
        print(json.dumps(result, indent=2))
        return 0

    except SpecError as exc:
        runlog.event(run_id, "finish", status="invalid_spec", error=str(exc))
        say(f"spec rejected, nothing was created: {exc}")
        print(json.dumps({"status": "invalid_spec", "run_id": run_id, "error": str(exc)}, indent=2))
        return 2
    except SetupError as exc:
        runlog.event(run_id, "finish", status="misconfigured", error=str(exc))
        say(f"setup problem, nothing was created: {exc}")
        print(json.dumps({"status": "misconfigured", "run_id": run_id, "error": str(exc)}, indent=2))
        return 2
    except (GHLError, VerifyError) as exc:
        where = getattr(exc, "stage", "unknown")
        ref = runbook_ref(exc)
        trace = f" trace={exc.trace_id}" if isinstance(exc, GHLError) and exc.trace_id else ""
        delivered = runlog.alert(run_id, "error", f"failed at '{where}': {exc}{trace} — RUNBOOK {ref}. "
                                 f"Safe to resume: --run-id {run_id}")
        runlog.event(run_id, "finish", status="failed", stage=where, error=str(exc)[:500], runbook=ref,
                     alert_delivered=delivered, stages=stages)
        print(json.dumps({"status": "failed", "run_id": run_id, "stage": where, "error": str(exc),
                          "runbook": ref, "alert_delivered": delivered,
                          "resume": f"create_proposal.py {args.spec} --run-id {run_id}"}, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
