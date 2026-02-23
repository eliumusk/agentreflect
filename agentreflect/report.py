"""Report generation — aggregate reflections into summary reports."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agentreflect.config import Config
from agentreflect.llm import call_llm
from agentreflect.storage import load_reflections

# ---------------------------------------------------------------------------
# Period helpers
# ---------------------------------------------------------------------------

PERIOD_DAYS = {
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
    "all": 0,
}


def _filter_by_period(records: list[dict[str, Any]], period: str) -> list[dict[str, Any]]:
    """Filter records to those within the given period."""
    days = PERIOD_DAYS.get(period, 0)
    if days == 0:
        return records

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    filtered: list[dict[str, Any]] = []
    for r in records:
        ts_str = r.get("timestamp", "")
        if not ts_str:
            continue
        try:
            # Handle both formats
            ts_str_clean = ts_str.replace("Z", "+00:00")
            ts = datetime.fromisoformat(ts_str_clean)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                filtered.append(r)
        except (ValueError, TypeError):
            # If we can't parse timestamp, include it
            filtered.append(r)
    return filtered


# ---------------------------------------------------------------------------
# Stats (no LLM needed)
# ---------------------------------------------------------------------------

def _compute_stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute basic statistics from reflection records."""
    total = len(records)
    if total == 0:
        return {"total": 0}

    outcomes = {"success": 0, "partial": 0, "failure": 0}
    confidence_scores: list[float] = []
    all_lessons: list[str] = []
    all_action_items: list[str] = []

    for r in records:
        outcome = r.get("outcome", "partial")
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        try:
            confidence_scores.append(float(r.get("confidence_score", 0.5)))
        except (TypeError, ValueError):
            pass
        all_lessons.extend(r.get("lessons_learned", []))
        all_action_items.extend(r.get("action_items", []))

    avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0

    return {
        "total_reflections": total,
        "outcomes": outcomes,
        "success_rate": f"{outcomes['success'] / total * 100:.0f}%",
        "avg_confidence": round(avg_confidence, 2),
        "unique_lessons": len(set(all_lessons)),
        "pending_action_items": len(all_action_items),
    }


# ---------------------------------------------------------------------------
# Summary report (uses LLM to synthesize)
# ---------------------------------------------------------------------------

REPORT_SYSTEM_PROMPT = """\
You are an analytical report writer. Given a set of AI agent self-reflections, \
produce a concise summary report highlighting patterns, recurring issues, and \
recommendations. Be specific and data-driven. Output plain text (not JSON)."""

REPORT_USER_TEMPLATE = """\
Here are {count} agent reflections from the {period} period:

{reflections_json}

Statistics:
{stats_json}

Write a concise summary report covering:
1. Overall performance trend
2. Recurring issues and root causes
3. Top lessons learned
4. Recommended focus areas going forward
"""


def generate_report(
    cfg: Config,
    *,
    period: str = "weekly",
    use_llm: bool = True,
) -> str:
    """Generate a summary report for the given period."""
    records = load_reflections(cfg.resolved_data_dir)
    records = _filter_by_period(records, period)

    if not records:
        return f"No reflections found for period: {period}\n"

    stats = _compute_stats(records)
    stats_text = json.dumps(stats, indent=2)

    # Basic stats section
    header = (
        f"═══ Agent Reflection Report ({period}) ═══\n\n"
        f"  Reflections: {stats['total_reflections']}\n"
        f"  Success rate: {stats['success_rate']}\n"
        f"  Avg confidence: {stats['avg_confidence']}\n"
        f"  Unique lessons: {stats['unique_lessons']}\n"
        f"  Action items: {stats['pending_action_items']}\n"
    )

    if not use_llm:
        return header + "\n(Use --llm to generate an AI-powered narrative summary)\n"

    # LLM-powered narrative
    reflections_json = json.dumps(records, indent=2, ensure_ascii=False)
    # Truncate if too long
    if len(reflections_json) > 12000:
        reflections_json = reflections_json[:12000] + "\n... (truncated)"

    user_prompt = REPORT_USER_TEMPLATE.format(
        count=len(records),
        period=period,
        reflections_json=reflections_json,
        stats_json=stats_text,
    )

    try:
        narrative = call_llm(cfg, REPORT_SYSTEM_PROMPT, user_prompt)
        return header + "\n" + narrative + "\n"
    except Exception as exc:
        return header + f"\n(LLM summary failed: {exc})\n"
