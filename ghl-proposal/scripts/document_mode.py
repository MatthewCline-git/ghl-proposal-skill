"""Proposal-as-document mode: fill a GHL proposal template through contact
custom fields and create a draft document from it.

The public API can send a template but can't create or edit one, so a person
builds one template once (see template/README.md). Everything else is here.
What the API can NOT tell us is how the merge renders; the caller says so and
hands back a link to look at."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone

import runlog
from errors import SetupError, VerifyError
from ghl import GHL, GHLError, http

FIELDS = [("proposal_intro", "Proposal intro", "LARGE_TEXT"),
          ("proposal_scope", "Proposal scope", "LARGE_TEXT"),
          ("proposal_total", "Proposal total", "TEXT"),
          ("proposal_terms", "Proposal terms", "LARGE_TEXT"),
          ("proposal_valid_through", "Proposal valid through", "TEXT")]
PLACEHOLDER = re.compile(r"\{\{\s*contact\.(proposal_[a-z_]+)\s*\}\}")


def resolve_template(ghl: GHL) -> dict:
    """GHL_PROPOSAL_TEMPLATE_ID, else the one proposal template named 'Proposal'."""
    ts = [t for t in ghl.templates() if not t.get("deleted") and t.get("type") == "proposal"]
    want = os.environ.get("GHL_PROPOSAL_TEMPLATE_ID")
    if want:
        hit = [t for t in ts if t["_id"] == want]
        if not hit:
            raise SetupError(f"GHL_PROPOSAL_TEMPLATE_ID {want} is not a proposal template in this location")
        return hit[0]
    hit = [t for t in ts if t.get("name", "").strip().lower() == "proposal"]
    if len(hit) == 1:
        return hit[0]
    names = ", ".join(repr(t.get("name")) for t in ts) or "none"
    raise SetupError(
        ("several templates are named 'Proposal'; set GHL_PROPOSAL_TEMPLATE_ID" if hit else
         f"no proposal template named 'Proposal' (found: {names}). Build it once from "
         "template/README.md and name it 'Proposal', or use --format estimate"))


def ensure_fields(ghl: GHL) -> dict[str, str]:
    """key -> custom field id, creating any that are missing."""
    have = ghl.custom_fields()
    ids = {}
    for key, name, dtype in FIELDS:
        f = have.get(f"contact.{key}")
        if not f:
            f = ghl.create_custom_field(name, dtype)
        ids[key] = f["id"]
    return ids


def money(amount: float, currency: str) -> str:
    sym = "$" if currency == "USD" else f"{currency} "
    return f"{sym}{amount:,.0f}" if float(amount).is_integer() else f"{sym}{amount:,.2f}"


def field_values(spec: dict, card: dict, lines: list[dict], total: float) -> dict[str, str]:
    cur = card["currency"]
    scope = "\n".join(
        f"{l['name']} ({money(l['amount'] * l['qty'], cur)}{' for ' + str(l['qty']) if l['qty'] > 1 else ''}): {l['description']}"
        for l in lines)
    skus = {i.get("sku") for i in spec["items"]}
    terms = spec["terms"] if "terms" in spec else [
        t if isinstance(t, str) else t["text"] for t in card["terms"]
        if isinstance(t, str) or not t.get("only_with") or t["only_with"] in skus]
    terms = list(terms) + [f"Assumes: {a}" for a in spec.get("assumptions", [])]
    valid = date.today() + timedelta(days=card["valid_days"])
    return {"proposal_intro": spec["intro"].strip(), "proposal_scope": scope,
            "proposal_total": money(total, cur), "proposal_terms": "\n".join(terms),
            "proposal_valid_through": f"{valid.strftime('%B')} {valid.day}, {valid.year}"}


def _created_after(doc: dict, since: datetime) -> bool:
    return datetime.fromisoformat(doc["createdAt"].replace("Z", "+00:00")).timestamp() >= since.timestamp() - 5


def find_document(ghl: GHL, contact_id: str, template_name: str, since: datetime) -> dict | None:
    hits = [d for d in ghl.list_documents()
            if not d.get("deleted") and d.get("name") == template_name
            and any(r.get("id") == contact_id for r in d.get("recipients", []))
            and _created_after(d, since)]
    if len(hits) > 1:
        raise VerifyError(f"{len(hits)} documents for this contact were created during this run; expected at most 1")
    return hits[0] if hits else None


def create_document(ghl: GHL, template: dict, contact_id: str, run_id: str, counters: dict) -> tuple[dict, dict | None]:
    """(document, send response or None). Checks for an existing document from this
    run before every attempt so a retry can never duplicate."""
    since = runlog.first_start(run_id) or datetime.now(timezone.utc) - timedelta(minutes=5)
    user = ghl.user_id()
    for attempt in range(1, 5):
        existing = find_document(ghl, contact_id, template["name"], since)
        if existing:
            print(f"    document already exists for {run_id}; not creating a duplicate", file=sys.stderr)
            return existing, None
        try:
            r = ghl.create_document(template["_id"], contact_id, user)
            return r["document"], r
        except GHLError as exc:
            if not exc.retryable or attempt == 4:
                raise
            counters["retries"] += 1
            wait = ghl.backoff(attempt)
            print(f"    transient failure ({exc}); retry {attempt}/3 in {wait:g}s", file=sys.stderr)
            runlog.event(run_id, "retry", attempt=attempt, error=str(exc)[:200])
            time.sleep(wait)
    raise AssertionError("unreachable")


def stored_copy(resp: dict) -> list:
    url = resp["document"]["versionHistory"][0]["downloadUrl"]
    code, raw = http("GET", url, headers={})
    if code != 200:
        raise VerifyError(f"could not fetch the stored document copy (HTTP {code})")
    return json.loads(raw)


def walk(node, out: list):
    if isinstance(node, dict):
        out.append(node)
        for v in node.values():
            walk(v, out)
    elif isinstance(node, list):
        for v in node:
            walk(v, out)


def verify(ghl: GHL, doc_id: str, *, contact_id: str, template: dict, ids: dict, values: dict,
           resp: dict | None) -> dict:
    problems = []
    got = ghl.contact_field_values(contact_id)
    for key, want in values.items():
        if got.get(ids[key]) != want:
            problems.append(f"contact field {key} does not hold the value we wrote")
    d = next((x for x in ghl.list_documents() if x.get("_id") == doc_id), None)
    if not d:
        problems.append("document not found in GHL after create")
    else:
        if d.get("status") != "draft":
            problems.append(f"status is {d.get('status')!r}, expected 'draft'")
        if not any(r.get("id") == contact_id for r in d.get("recipients", [])):
            problems.append("document is not addressed to this contact")
    checked = ["fields written and read back", "document exists, draft, addressed to the contact"]
    if resp is not None:  # only available on creation, not on a resumed run
        nodes: list = []
        walk(stored_copy(resp), nodes)
        html_text = " ".join(str((n.get("component") or {}).get("options", {}).get("text", ""))
                             for n in nodes if isinstance(n, dict))
        placeholders = set(PLACEHOLDER.findall(html_text))
        if not placeholders:
            problems.append("the template has no {{contact.proposal_*}} merge fields; was it pasted correctly?")
        if unknown := placeholders - set(values):
            problems.append(f"template uses merge fields the skill doesn't fill: {sorted(unknown)}")
        if missing := set(values) - placeholders:
            problems.append(f"template is missing merge fields for: {sorted(missing)} (content would be dropped)")
        if not any(n.get("type") == "Signature" for n in nodes):
            problems.append("the template has no signature field")
        checked.append("template has every merge field and a signature field")
    if problems:
        raise VerifyError("; ".join(problems))
    return {"checked": checked, "not_checked": "how the merge renders and page layout: open the document in GHL"}
