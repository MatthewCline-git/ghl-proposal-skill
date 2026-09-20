"""Credential loading. Inside the upwork repo this defers to lib.env (single
source of truth). Standalone (someone dropped the skill folder into
~/.claude/skills), it reads real environment variables, then a `.env` sitting
next to SKILL.md. Values are never printed."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_SKILL_DIR = Path(__file__).resolve().parent.parent


def load() -> None:
    root = _SKILL_DIR
    while not (root / ".git").exists() and root != root.parent:
        root = root.parent
    if (root / "lib" / "env.py").exists():
        sys.path.insert(0, str(root))
        from lib.env import load_env  # type: ignore

        load_env(__file__)
        return
    local = _SKILL_DIR / ".env"
    if local.exists():
        for line in local.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                v = v.strip()
                if v[:1] in ("'", '"'):
                    v = v.strip("'\"")
                else:  # drop a trailing "  # comment"
                    v = re.split(r"\s+#", v, maxsplit=1)[0].strip()
                if v:  # an empty value means "not set"
                    os.environ.setdefault(k.strip(), v)


def need(*names: str) -> list[str]:
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise SystemExit(
            f"missing credentials: {', '.join(missing)}. Set them as environment "
            f"variables or in {_SKILL_DIR / '.env'} (see SKILL.md > Setup)."
        )
    return [os.environ[n] for n in names]
