"""Evaluation engine for agentreflect.

Orchestrates session parsing → prompt building → LLM call → result parsing.
Scores across 5 dimensions with a pluggable architecture.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agentreflect.llm import call_llm, LLMError, ConfigError
from agentreflect.parser import Session
from agentreflect.prompt import (
    ALL_DIMENSION_KEYS,
    DIMENSIONS,
    SYSTEM_PROMPT,
    build_evaluation_prompt,
)


@dataclass
class DimensionScore:
    """Score for a single evaluation dimension."""

    key: str                    # e.g., "goal_completion"
    name: str                   # e.g., "Goal Completion"
    emoji: str                  # e.g., "🎯"
    score: int                  # 1-10
    explanation: str            # one-sentence explanation
    max_score: int = 10

    @property
    def bar(self) -> str:
        """Unicode progress bar representation."""
        filled = "█" * self.score
        empty = "░" * (self.max_score - self.score)
        return filled + empty

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "score": self.score,
            "max_score": self.max_score,
            "explanation": self.explanation,
        }


@dataclass
class EvaluationResult:
    """Complete evaluation result."""

    overall_score: float                        # weighted average, 1 decimal
    summary: str                                # 1-2 sentence summary
    dimensions: List[DimensionScore]            # individual dimension scores
    recommendations: List[str]                  # actionable recommendations
    session_source: str = ""                    # filename / stdin
    provider: str = ""                          # LLM provider used
    model: str = ""                             # LLM model used
    session_stats: Dict[str, Any] = field(default_factory=dict)
    raw_response: str = ""                      # raw LLM response for debugging

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "overall_score": self.overall_score,
            "summary": self.summary,
            "dimensions": {d.key: d.to_dict() for d in self.dimensions},
            "recommendations": self.recommendations,
            "session_source": self.session_source,
            "provider": self.provider,
            "model": self.model,
            "session_stats": self.session_stats,
        }

    def dimension_by_key(self, key: str) -> Optional[DimensionScore]:
        """Get a dimension score by its key."""
        for d in self.dimensions:
            if d.key == key:
                return d
        return None


class EvaluationError(Exception):
    """Raised when evaluation fails."""
    pass


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _extract_json_from_response(text: str) -> dict:
    """Extract a JSON object from LLM response text.

    Handles cases where the LLM wraps JSON in markdown code fences
    or adds commentary around it.

    Args:
        text: Raw LLM response.

    Returns:
        Parsed JSON dict.

    Raises:
        EvaluationError: If no valid JSON can be extracted.
    """
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code fences
    fence_pattern = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)
    match = fence_pattern.search(text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try finding a JSON object by braces
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        candidate = text[brace_start:brace_end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    raise EvaluationError(
        f"Could not parse LLM response as JSON. Raw response:\n{text[:1000]}"
    )


def _parse_evaluation_response(
    response_text: str,
    dimension_keys: List[str],
) -> dict:
    """Parse and validate the evaluation response from the LLM.

    Args:
        response_text: Raw LLM response text.
        dimension_keys: Expected dimension keys.

    Returns:
        Validated evaluation dict with keys: overall_score, summary,
        dimensions, recommendations.

    Raises:
        EvaluationError: If validation fails.
    """
    data = _extract_json_from_response(response_text)

    # Validate overall_score
    overall = data.get("overall_score")
    if overall is None:
        # Calculate from dimensions
        dims = data.get("dimensions", {})
        if dims:
            scores = [d.get("score", 5) for d in dims.values() if isinstance(d, dict)]
            overall = round(sum(scores) / len(scores), 1) if scores else 5.0
        else:
            overall = 5.0

    try:
        overall = round(float(overall), 1)
    except (TypeError, ValueError):
        overall = 5.0

    overall = max(1.0, min(10.0, overall))

    # Validate summary
    summary = data.get("summary", "No summary provided.")
    if not isinstance(summary, str):
        summary = str(summary)

    # Validate dimensions
    raw_dims = data.get("dimensions", {})
    if not isinstance(raw_dims, dict):
        raise EvaluationError("'dimensions' in response is not a dict")

    validated_dims: dict[str, dict] = {}
    for key in dimension_keys:
        dim_data = raw_dims.get(key, {})
        if not isinstance(dim_data, dict):
            dim_data = {}

        score = dim_data.get("score", 5)
        try:
            score = int(score)
        except (TypeError, ValueError):
            score = 5
        score = max(1, min(10, score))

        explanation = dim_data.get("explanation", "No explanation provided.")
        if not isinstance(explanation, str):
            explanation = str(explanation)

        validated_dims[key] = {
            "score": score,
            "explanation": explanation,
        }

    # Validate recommendations
    recommendations = data.get("recommendations", [])
    if not isinstance(recommendations, list):
        recommendations = [str(recommendations)]
    recommendations = [str(r) for r in recommendations if r]
    if not recommendations:
        recommendations = ["No specific recommendations."]

    return {
        "overall_score": overall,
        "summary": summary,
        "dimensions": validated_dims,
        "recommendations": recommendations,
    }


# ---------------------------------------------------------------------------
# Main evaluation function
# ---------------------------------------------------------------------------

def evaluate_session(
    session: Session,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    dimensions: Optional[List[str]] = None,
) -> EvaluationResult:
    """Evaluate an agent session across specified dimensions.

    This is the main entry point for the evaluation engine. It:
    1. Converts the session to text
    2. Builds the evaluation prompt
    3. Calls the LLM
    4. Parses and validates the response
    5. Returns a structured EvaluationResult

    Args:
        session: Parsed session object.
        provider: LLM provider ("openai" or "anthropic"). Auto-detected if None.
        model: Specific model to use. Provider default if None.
        dimensions: List of dimension keys to evaluate. All 5 if None.

    Returns:
        An EvaluationResult with scores, explanations, and recommendations.

    Raises:
        EvaluationError: If evaluation fails.
        LLMError: If the LLM API call fails.
        ConfigError: If API key is missing.
    """
    # Resolve dimensions
    if dimensions is None:
        dimension_keys = ALL_DIMENSION_KEYS.copy()
    else:
        dimension_keys = []
        for d in dimensions:
            d_clean = d.strip().lower().replace(" ", "_").replace("-", "_")
            if d_clean in DIMENSIONS:
                dimension_keys.append(d_clean)
            else:
                # Try fuzzy match
                for key in ALL_DIMENSION_KEYS:
                    if d_clean in key or key in d_clean:
                        dimension_keys.append(key)
                        break
                else:
                    raise EvaluationError(
                        f"Unknown dimension: '{d}'. "
                        f"Available: {', '.join(ALL_DIMENSION_KEYS)}"
                    )

    if not dimension_keys:
        raise EvaluationError("No valid dimensions specified")

    # Convert session to text
    session_text = session.to_text()
    session_stats = session.stats()

    # Build prompt
    user_prompt = build_evaluation_prompt(session_text, dimension_keys)

    # Call LLM
    try:
        response_text, provider_used, model_used = call_llm(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            provider=provider,
            model=model,
        )
    except (LLMError, ConfigError):
        raise
    except Exception as exc:
        raise EvaluationError(f"Unexpected error calling LLM: {exc}") from exc

    # Parse response
    parsed = _parse_evaluation_response(response_text, dimension_keys)

    # Build DimensionScore objects
    dim_scores: list[DimensionScore] = []
    for key in dimension_keys:
        meta = DIMENSIONS[key]
        dim_data = parsed["dimensions"].get(key, {"score": 5, "explanation": "N/A"})
        dim_scores.append(DimensionScore(
            key=key,
            name=meta["name"],
            emoji=meta["emoji"],
            score=dim_data["score"],
            explanation=dim_data["explanation"],
        ))

    return EvaluationResult(
        overall_score=parsed["overall_score"],
        summary=parsed["summary"],
        dimensions=dim_scores,
        recommendations=parsed["recommendations"],
        session_source=session.source,
        provider=provider_used,
        model=model_used,
        session_stats=session_stats,
        raw_response=response_text,
    )
