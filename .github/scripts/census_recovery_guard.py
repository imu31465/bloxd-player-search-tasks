#!/usr/bin/env python3
"""Fail-safe recovery decision for an overdue hourly production census."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

CENSUS_WORKFLOW_ID = 426133178
WRITER_WORKFLOW_IDS = {426133178, 426133230, 426133266}
ACTIVE_STATUSES = {"queued", "in_progress", "waiting", "requested"}
CENSUS_INTERVAL = timedelta(minutes=80)
CENSUS_SLOT_MINUTE = 47
SLOT_GRACE_MINUTES = 15


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("workflow timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def census_recovery_decision(
    workflow_runs: list[dict[str, Any]],
    now: datetime,
) -> tuple[bool, str]:
    """Return whether a census may be dispatched without overlapping writers.

    The 80-minute age threshold leaves room for the hourly :47 UTC schedule and
    GitHub's observed delivery delay. A 15-minute guard on either side of the
    reserved slot avoids racing a delayed scheduled run.
    """
    now = now.astimezone(timezone.utc)

    active_writers = [
        run
        for run in workflow_runs
        if int(run.get("workflow_id", 0)) in WRITER_WORKFLOW_IDS
        and run.get("status") in ACTIVE_STATUSES
    ]
    if active_writers:
        names = ",".join(
            f"{run.get('name', 'writer')}#{run.get('run_number', '?')}"
            for run in active_writers[:3]
        )
        return False, f"writer-active-or-queued:{names}"

    census_runs: list[tuple[datetime, dict[str, Any]]] = []
    for run in workflow_runs:
        if int(run.get("workflow_id", 0)) != CENSUS_WORKFLOW_ID:
            continue
        created_at = run.get("created_at")
        if not isinstance(created_at, str):
            continue
        try:
            census_runs.append((_parse_time(created_at), run))
        except (TypeError, ValueError):
            continue

    if census_runs:
        latest_at, latest_run = max(census_runs, key=lambda item: item[0])
        age = now - latest_at
        if age < CENSUS_INTERVAL:
            return False, (
                f"latest-census-is-recent:run#{latest_run.get('run_number', '?')}:"
                f"{max(0.0, age.total_seconds() / 60):.1f}m"
            )
        age_minutes = age.total_seconds() / 60
    else:
        age_minutes = float("inf")

    this_hour_slot = now.replace(
        minute=CENSUS_SLOT_MINUTE, second=0, microsecond=0
    )
    last_slot = this_hour_slot if this_hour_slot <= now else this_hour_slot - timedelta(hours=1)
    minutes_since_slot = (now - last_slot).total_seconds() / 60
    next_slot = last_slot + timedelta(hours=1)
    minutes_to_next_slot = (next_slot - now).total_seconds() / 60

    if minutes_since_slot <= SLOT_GRACE_MINUTES:
        return False, f"inside-delayed-census-grace:{minutes_since_slot:.1f}m"
    if minutes_to_next_slot <= SLOT_GRACE_MINUTES:
        return False, f"next-census-slot-is-near:{minutes_to_next_slot:.1f}m"

    age_label = "never-run" if age_minutes == float("inf") else f"{age_minutes:.1f}m"
    return True, f"overdue-census:{age_label}:no-active-writer"


def _self_test() -> None:
    def run(workflow_id: int, status: str, created_at: str, number: int = 1) -> dict[str, Any]:
        return {
            "workflow_id": workflow_id,
            "status": status,
            "created_at": created_at,
            "run_number": number,
            "name": "census" if workflow_id == CENSUS_WORKFLOW_ID else "writer",
        }

    now = datetime(2026, 11, 28, 12, 10, tzinfo=timezone.utc)
    old_census = run(CENSUS_WORKFLOW_ID, "completed", "2026-11-28T10:30:00Z", 21)
    recent_census = run(CENSUS_WORKFLOW_ID, "completed", "2026-11-28T11:40:00Z", 22)

    assert census_recovery_decision([], now)[0] is True
    assert census_recovery_decision([old_census], now)[0] is True
    assert census_recovery_decision([recent_census], now)[0] is False
    assert census_recovery_decision(
        [old_census, run(426133266, "in_progress", "2026-11-28T12:00:00Z")],
        now,
    )[0] is False
    assert census_recovery_decision(
        [old_census, run(CENSUS_WORKFLOW_ID, "queued", "2026-11-28T12:05:00Z", 23)],
        now,
    )[0] is False

    inside_grace = datetime(2026, 11, 28, 12, 0, tzinfo=timezone.utc)
    assert census_recovery_decision([old_census], inside_grace)[0] is False

    near_next_slot = datetime(2026, 11, 28, 12, 32, tzinfo=timezone.utc)
    stale_before_next_slot = run(
        CENSUS_WORKFLOW_ID, "completed", "2026-11-28T11:00:00Z", 21
    )
    assert census_recovery_decision([stale_before_next_slot], near_next_slot)[0] is False


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        _self_test()
        print("census recovery guard self-tests passed")
        return 0
    if len(sys.argv) != 2:
        print(
            "usage: census_recovery_guard.py <workflow-runs.json> | --self-test",
            file=sys.stderr,
        )
        return 2

    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    runs = data.get("workflow_runs", [])
    if not isinstance(runs, list):
        raise SystemExit("GitHub Actions response is missing workflow_runs")
    due, reason = census_recovery_decision(runs, datetime.now(timezone.utc))
    print(f"{str(due).lower()}|{reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
