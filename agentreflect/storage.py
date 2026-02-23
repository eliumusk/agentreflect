"""Reflection storage — local JSON file with search/filter/export."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REFLECTIONS_FILE = "reflections.json"


def _storage_path(data_dir: Path) -> Path:
    return data_dir / REFLECTIONS_FILE


def _ensure_dir(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)


def _load_all(data_dir: Path) -> list[dict[str, Any]]:
    path = _storage_path(data_dir)
    if not path.is_file():
        return []
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if isinstance(data, list):
        return data
    return []


def _save_all(data_dir: Path, records: list[dict[str, Any]]) -> None:
    _ensure_dir(data_dir)
    path = _storage_path(data_dir)
    path.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_reflection(data_dir: Path, reflection: dict[str, Any]) -> Path:
    """Append a reflection record and return the storage file path."""
    records = _load_all(data_dir)
    # Ensure timestamp
    if "timestamp" not in reflection:
        reflection["timestamp"] = datetime.now(timezone.utc).isoformat()
    records.append(reflection)
    _save_all(data_dir, records)
    return _storage_path(data_dir)


def load_reflections(
    data_dir: Path,
    *,
    last: int | None = None,
    outcome: str | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    """Load reflections with optional filters."""
    records = _load_all(data_dir)

    if outcome:
        records = [r for r in records if r.get("outcome") == outcome]

    if search:
        q = search.lower()
        def _matches(r: dict[str, Any]) -> bool:
            text = json.dumps(r, ensure_ascii=False).lower()
            return q in text
        records = [r for r in records if _matches(r)]

    if last is not None and last > 0:
        records = records[-last:]

    return records


def export_markdown(records: list[dict[str, Any]]) -> str:
    """Convert reflection records to a Markdown string."""
    if not records:
        return "_No reflections found._\n"

    lines: list[str] = ["# Agent Reflections\n"]
    for i, r in enumerate(records, 1):
        lines.append(f"## #{i} — {r.get('task', 'Untitled')}\n")
        lines.append(f"- **Outcome:** {r.get('outcome', 'N/A')}")
        lines.append(f"- **Confidence:** {r.get('confidence_score', 'N/A')}")
        lines.append(f"- **Timestamp:** {r.get('timestamp', 'N/A')}\n")

        if r.get("what_went_well"):
            lines.append("### What Went Well")
            for item in r["what_went_well"]:
                lines.append(f"- {item}")
            lines.append("")

        if r.get("what_went_wrong"):
            lines.append("### What Went Wrong")
            for item in r["what_went_wrong"]:
                lines.append(f"- {item}")
            lines.append("")

        if r.get("root_causes"):
            lines.append("### Root Causes")
            for item in r["root_causes"]:
                lines.append(f"- {item}")
            lines.append("")

        if r.get("lessons_learned"):
            lines.append("### Lessons Learned")
            for item in r["lessons_learned"]:
                lines.append(f"- {item}")
            lines.append("")

        if r.get("action_items"):
            lines.append("### Action Items")
            for item in r["action_items"]:
                lines.append(f"- [ ] {item}")
            lines.append("")

        lines.append("---\n")

    return "\n".join(lines)
