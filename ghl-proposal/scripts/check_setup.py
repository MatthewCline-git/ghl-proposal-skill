#!/usr/bin/env python3
"""Setup check: proves the token, location, scopes and proposal template work,
and says exactly what to fix. Its only write is creating the five proposal
custom fields if they are missing (harmless, and needed anyway).

  check_setup.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: E402

_env.load()
import os  # noqa: E402

import document_mode  # noqa: E402
from errors import SetupError  # noqa: E402
from ghl import GHL, GHLError  # noqa: E402

missing = [n for n in ("GHL_TOKEN", "GHL_LOCATION_ID") if not os.environ.get(n)]
if missing:
    print(f"✗ {', '.join(missing)} not set. Put them in the .env next to SKILL.md (see .env.example).")
    sys.exit(1)

tok, loc = os.environ["GHL_TOKEN"], os.environ["GHL_LOCATION_ID"]
if not tok.startswith("pit-"):
    print("✗ GHL_TOKEN should start with 'pit-': a Private Integration token from the sub-account, not an agency key.")
    sys.exit(1)

g = GHL(tok, loc)
state: dict = {}


def template():
    t = document_mode.resolve_template(g)
    state["template"] = t
    return f"found '{t['name']}'"


checks = [
    ("location", "locations.readonly", lambda: g.location().get("name") or "ok"),
    ("contacts", "contacts.readonly + contacts.write", lambda: g.request("GET", "/contacts/", params={"locationId": loc, "limit": 1}) and "readable"),
    ("users", "users.readonly (or set GHL_USER_ID)", lambda: g.user_id() and "ok"),
    ("custom fields", "locations/customFields.readonly + .write", lambda: f"{len(document_mode.ensure_fields(g))} proposal fields ready"),
    ("proposal template", "Documents & Contracts templates: view", template),
    ("estimates (optional format)", "invoices/estimate.readonly + .write", lambda: f"{len(g.list_estimates())} found"),
]
bad = 0
for name, scope, fn in checks:
    try:
        print(f"✓ {name}: {fn()}")
    except SetupError as exc:
        bad += 1
        print(f"✗ {name}: {exc}")
    except GHLError as exc:
        hint = ""
        if exc.retryable:
            hint = " — GHL is flaky right now; run this again."
        elif exc.status == 401 and "location" in str(exc).lower():
            hint = " — the token doesn't belong to this location id, or the sub-account is inactive."
        elif exc.status in (401, 403):
            hint = f" — the token is missing: {scope}. Edit the integration in Settings > Private Integrations."
        if "estimates" not in name:
            bad += 1
        print(f"{'✗' if 'estimates' not in name else '·'} {name}: {exc}{hint}")
print("\nAll good." if not bad else f"\n{bad} problem(s) above.")
sys.exit(1 if bad else 0)
