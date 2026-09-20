#!/usr/bin/env python3
"""Turn a proposal spec into a real GoHighLevel estimate, verify it landed, and
leave a run log. Claude drafts the spec; this script does everything that must
not be improvised: pricing, API calls, retries, verification, alerting.

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

import runlog  # noqa: E402
from ghl import GHL, GHLError  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent
LIVE = True
UNDELIVERABLE = ("example.com", "example.org", "example.net", ".test", ".invalid", ".localhost")


class SpecError(ValueError):
    """The spec Claude wrote is wrong. Nothing was touched; fix it and rerun."""


class VerifyError(RuntimeError):
    """GHL said yes but the thing that exists is not what we asked for."""


def say(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- spec + price
def validate_spec(spec: dict, card: dict) -> None:
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
    items = spec.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 10:
        errs.append("items must be a list of 1-10 entries")
        items = []
    seen: set[str] = set()
    for i, it in enumerate(items):
        extra = set(it) - {"sku", "note", "qty", "name", "description", "amount"}
        if extra:
            errs.append(f"items[{i}] has unknown keys {sorted(extra)}")
        sku = it.get("sku")
        if sku is not None:
            if sku not in card["items"]:
                errs.append(f"items[{i}].sku {sku!r} is not in the rate card ({', '.join(card['items'])}); "
                            f"for something else, give it a name, description and amount instead of a sku")
            if sku in seen:
                errs.append(f"items[{i}].sku {sku!r} appears twice; use qty instead")
            seen.add(sku)
        else:  # custom line: the user's own price for something not on the card
            if not str(it.get("name", "")).strip():
                errs.append(f"items[{i}] needs a sku, or a name + description + amount")
            if not str(it.get("description", "")).strip():
                errs.append(f"items[{i}] custom line needs a description")
            if "amount" not in it:
                errs.append(f"items[{i}] custom line needs an amount")
        if "amount" in it and (isinstance(it["amount"], bool) or not isinstance(it["amount"], (int, float))
                               or not 0 < it["amount"] <= 1_000_000):
            errs.append(f"items[{i}].amount must be a number between 0 and 1,000,000")
        if not isinstance(it.get("qty", 1), int) or not 1 <= it.get("qty", 1) <= 20:
            errs.append(f"items[{i}].qty must be an integer 1-20")
        if len(it.get("note", "")) > 300:
            errs.append(f"items[{i}].note is over 300 characters")
    for a in spec.get("assumptions", []):
        if not isinstance(a, str) or not a.strip():
            errs.append("assumptions must be non-empty strings")
    if errs:
        raise SpecError("; ".join(errs))


def price(spec: dict, card: dict) -> tuple[list[dict], float]:
    """Amounts come from the rate card unless the spec carries one — which must be
    a price the user gave, since nothing here can check that. Each line records
    where its number came from so the dry run and run log make it visible."""
    lines = []
    for it in spec["items"]:
        qty = it.get("qty", 1)
        if "sku" in it:
            r = card["items"][it["sku"]]
            name, base = r["name"], r["description"]
            amount = it.get("amount", r["amount"])
            source = "override" if "amount" in it and it["amount"] != r["amount"] else "rate_card"
        else:
            name, base, amount, source = it["name"].strip(), it["description"].strip(), it["amount"], "custom"
        desc = base + (f" {it['note'].strip()}" if it.get("note") else "")
        lines.append({"name": name, "description": desc, "currency": card["currency"],
                      "amount": amount, "qty": qty, "type": "one_time", "_source": source})
    return lines, sum(l["amount"] * l["qty"] for l in lines)


def clean(lines: list[dict]) -> list[dict]:
    return [{k: v for k, v in l.items() if not k.startswith("_")} for l in lines]


def terms_html(spec: dict, card: dict) -> str:
    esc = html.escape
    out = [f"<p>{esc(spec['intro'].strip())}</p>"]
    if spec.get("assumptions"):
        out.append("<h4>Assumptions</h4><ul>" + "".join(f"<li>{esc(a)}</li>" for a in spec["assumptions"]) + "</ul>")
    skus = {i.get("sku") for i in spec["items"]}
    terms = [t if isinstance(t, str) else t["text"] for t in card["terms"]
             if isinstance(t, str) or not t.get("only_with") or t["only_with"] in skus]
    out.append("<h4>Terms</h4><ul>" + "".join(f"<li>{esc(t)}</li>" for t in terms) + "</ul>")
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


RUNBOOK = {401: "§1 credentials", 403: "§1 credentials", 422: "§2 payload rejected"}


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
    ap.add_argument("--send", action="store_true", help="email the estimate to the client")
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
        card = json.loads(Path(os.environ.get("GHL_PROPOSAL_RATE_CARD") or SKILL_DIR / "rate_card.json").read_text())
        try:
            spec = json.loads(Path(args.spec).read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise SpecError(f"cannot read spec: {exc}")
        with stage(run_id, "validate", stages):
            validate_spec(spec, card)
            lines, total = price(spec, card)
        if args.dry_run:
            runlog.event(run_id, "finish", status="dry_run", total=total)
            print(json.dumps({"status": "dry_run", "run_id": run_id, "total": total,
                              "items": [{"name": l["name"], "amount": l["amount"], "qty": l["qty"], "price_from": l["_source"]}
                                        for l in lines]}, indent=2))
            return 0
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

        c = spec["client"]
        with stage(run_id, "contact", stages):
            up = ghl.upsert_contact(name=c["name"], email=c["email"], company=c["company"],
                                    phone=c.get("phone", ""))
            contact = up.get("contact") or {}
            if not contact.get("id"):
                raise VerifyError(f"contact upsert returned no id: {list(up)}")
            contact_id, contact_new = contact["id"], bool(up.get("new"))

        with stage(run_id, "estimate", stages):
            biz = ghl.location()
            body = {
                "altId": loc, "altType": "location", "liveMode": LIVE, "currency": card["currency"],
                "name": estimate_name(c["company"], run_id),
                "title": f"Proposal for {c['company']}",
                "businessDetails": {k: v for k, v in {"name": biz.get("name"), "phoneNo": biz.get("phone"),
                                                       "website": biz.get("website")}.items() if v},
                "contactDetails": {"id": contact_id, "name": c["name"], "email": c["email"],
                                   "phoneNo": c.get("phone", ""), "companyName": c["company"]},
                "items": clean(lines), "discount": {"type": "percentage", "value": 0},
                "frequencySettings": {"enabled": False, "schedule": {}},
                "termsNotes": terms_html(spec, card), "userId": ghl.user_id(),
                "issueDate": date.today().isoformat(),
                "expiryDate": (date.today() + timedelta(days=card["valid_days"])).isoformat(),
                "meta": {"runId": run_id},
            }
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
                  "url": f"{app}/v2/location/{loc}/payments/v2/estimates/edit/{estimate_id}", "price_sources": {l["name"]: l["_source"] for l in lines}, "estimate_id": estimate_id,
                  "estimate_number": e.get("estimateNumber"), "total": total,
                  "currency": card["currency"], "contact_id": contact_id, "contact_new": contact_new,
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
