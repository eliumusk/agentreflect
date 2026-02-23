"""Core reflection logic — orchestrates prompt building, LLM call, and parsing."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from typing import Any

from agentreflect.config import Config
from agentreflect.llm import call_llm
from agentreflect.prompt import (
    INTERACTIVE_QUESTIONS,
    SYSTEM_PROMPT,
    USER_PROMPT_MINIMAL,
    USER_PROMPT_TEMPLATE,
)
from agentreflect.storage import save_reflection

# ---------------------------------------------------------------------------
# Expected schema keys
# ---------------------------------------------------------------------------

REQUIRED_KEYS = {
    "task",
    "outcome",
    "what_went_well",
    "what_went_wrong",
    "root_causes",
    "lessons_learned",
    "action_items",
    "confidence_score",
}


# ---------------------------------------------------------------------------
# JSON extraction helper
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict[str, Any]:
    """Extract JSON from LLM response, tolerating markdown fences."""
    # Try direct parse first
    text = text.strip()
    # Strip markdown code fences if present
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()

    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse LLM response as JSON: {exc}\nRaw:\n{text[:500]}") from exc

    if not isinstance(obj, dict):
        raise ValueError(f"Expected JSON object, got {type(obj).__name__}")

    return obj


def _validate_reflection(data: dict[str, Any]) -> dict[str, Any]:
    """Normalise and lightly validate a reflection dict."""
    missing = REQUIRED_KEYS - set(data.keys())
    if missing:
        # Be lenient — fill missing keys with sensible defaults
        for key in missing:
            if key == "confidence_score":
                data[key] = 0.5
            elif key in ("what_went_well", "what_went_wrong", "root_causes", "lessons_learned", "action_items"):
                data[key] = []
            else:
                data[key] = ""

    # Clamp confidence
    try:
        data["confidence_score"] = max(0.0, min(1.0, float(data["confidence_score"])))
    except (TypeError, ValueError):
        data["confidence_score"] = 0.5

    # Normalise outcome
    outcome = str(data.get("outcome", "")).lower().strip()
    if outcome not in ("success", "partial", "failure"):
        # Best-effort mapping
        if "succ" in outcome:
            outcome = "success"
        elif "fail" in outcome:
            outcome = "failure"
        else:
            outcome = "partial"
    data["outcome"] = outcome

    return data


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def reflect(
    cfg: Config,
    *,
    task: str,
    result: str,
    log: str = "",
) -> dict[str, Any]:
    """Run a full reflection cycle: build prompt → call LLM → parse → store."""

    # Build user prompt
    if log:
        user_prompt = USER_PROMPT_TEMPLATE.format(task=task, result=result, log=log)
    else:
        user_prompt = USER_PROMPT_MINIMAL.format(task=task, result=result)

    # Call LLM
    raw_response = call_llm(cfg, SYSTEM_PROMPT, user_prompt)

    # Parse
    data = _extract_json(raw_response)
    data = _validate_reflection(data)

    # Add timestamp
    data["timestamp"] = datetime.now(timezone.utc).isoformat()

    # Store
    storage_path = save_reflection(cfg.resolved_data_dir, data)

    return data


def reflect_interactive(cfg: Config) -> dict[str, Any]:
    """Interactive reflection: prompt user for inputs, then reflect."""
    answers: dict[str, str] = {}
    for key, prompt_text in INTERACTIVE_QUESTIONS:
        try:
            val = input(prompt_text)
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(1)
        answers[key] = val.strip()

    return reflect(
        cfg,
        task=answers.get("task", ""),
        result=answers.get("result", ""),
        log=answers.get("log", ""),
    )
