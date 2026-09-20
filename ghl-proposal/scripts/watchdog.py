#!/usr/bin/env python3
"""Run on a schedule (cron / launchd / a Claude routine). Alerts on runs that
started and never finished, and on failures nobody has resolved. This is the
piece that turns 'a workflow sat broken for 14 days' into a same-day message.

  watchdog.py [--max-age-min 30] [--failure-age-min 240]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: E402

_env.load()
import runlog  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--max-age-min", type=float, default=30)
ap.add_argument("--failure-age-min", type=float, default=240)
a = ap.parse_args()

problems = 0
for r in runlog.stuck_runs(a.max_age_min):
    problems += 1
    d = runlog.alert(r["run_id"], "error", f"run started {r['age_min']} min ago and never finished (likely crashed or hung). RUNBOOK §5.")
    print(f"STUCK   {r['run_id']} {r['age_min']}min alert={d}")
for r in runlog.unresolved_failures(a.failure_age_min):
    problems += 1
    d = runlog.alert(r["run_id"], "warn", f"failure unresolved for {r['age_min']} min: {r['error'][:160]}")
    print(f"UNFIXED {r['run_id']} {r['age_min']}min alert={d}")
print("all clear" if not problems else f"{problems} problem(s)")
sys.exit(1 if problems else 0)
