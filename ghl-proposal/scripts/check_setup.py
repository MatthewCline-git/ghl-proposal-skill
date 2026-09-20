#!/usr/bin/env python3
"""Read-only setup check: proves the token, location and each scope the skill
needs actually work, and says exactly what to fix. Creates nothing.

  check_setup.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: E402

_env.load()
import os  # noqa: E402

from ghl import GHL, GHLError  # noqa: E402

missing = [n for n in ("GHL_TOKEN", "GHL_LOCATION_ID") if not os.environ.get(n)]
if missing:
    print(f"✗ {', '.join(missing)} not set. Put them in the .env next to SKILL.md (see .env.example).")
    sys.exit(1)

tok, loc = os.environ["GHL_TOKEN"], os.environ["GHL_LOCATION_ID"]
if not tok.startswith("pit-"):
    print("✗ GHL_TOKEN should start with 'pit-' (a Private Integration token from the sub-account, not an agency key).")
    sys.exit(1)

g = GHL(tok, loc)
checks = [
    ("location", "Locations: view", lambda: g.location().get("name") or "ok"),
    ("contacts", "Contacts: view and edit", lambda: g.request("GET", "/contacts/", params={"locationId": loc, "limit": 1}) and "ok"),
    ("estimates", "Invoices/Estimates: view and edit", lambda: f"{len(g.list_estimates())} found"),
    ("user", "Users: view (or set GHL_USER_ID)", lambda: g.user_id() and "ok"),
]
bad = 0
for name, scope, fn in checks:
    try:
        print(f"✓ {name}: {fn()}")
    except GHLError as exc:
        bad += 1
        hint = ""
        if exc.status == 401 and "location" in str(exc).lower():
            hint = " — the token doesn't belong to this location id, or the sub-account is inactive."
        elif exc.status in (401, 403):
            hint = f" — token is missing the scope: {scope}. Edit the integration in Settings > Private Integrations."
        print(f"✗ {name}: {exc}{hint}")
print("\nAll good." if not bad else f"\n{bad} problem(s) above.")
sys.exit(1 if bad else 0)
