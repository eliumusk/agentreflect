"""LLM API calls — OpenAI and Anthropic, using only urllib.request."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from agentreflect.config import Config

# ---------------------------------------------------------------------------
# Provider endpoints
# ---------------------------------------------------------------------------

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _http_post(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    """POST JSON, return parsed response. Raises on HTTP error."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"LLM API error {exc.code}: {error_body}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error: {exc.reason}") from exc


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

def _call_openai(cfg: Config, system: str, user: str) -> str:
    url = cfg.api_base.rstrip("/") + "/chat/completions" if cfg.api_base else OPENAI_URL
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.api_key}",
    }
    payload = {
        "model": cfg.resolved_model,
        "max_tokens": cfg.max_tokens,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    resp = _http_post(url, headers, payload)
    try:
        return resp["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected OpenAI response: {json.dumps(resp)[:500]}") from exc


def _call_anthropic(cfg: Config, system: str, user: str) -> str:
    url = cfg.api_base.rstrip("/") + "/messages" if cfg.api_base else ANTHROPIC_URL
    headers = {
        "Content-Type": "application/json",
        "x-api-key": cfg.api_key,
        "anthropic-version": ANTHROPIC_VERSION,
    }
    payload = {
        "model": cfg.resolved_model,
        "max_tokens": cfg.max_tokens,
        "system": system,
        "messages": [
            {"role": "user", "content": user},
        ],
    }
    resp = _http_post(url, headers, payload)
    try:
        return resp["content"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected Anthropic response: {json.dumps(resp)[:500]}") from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def call_llm(cfg: Config, system: str, user: str) -> str:
    """Send a prompt to the configured LLM provider, return raw text."""
    if cfg.provider == "openai":
        return _call_openai(cfg, system, user)
    elif cfg.provider == "anthropic":
        return _call_anthropic(cfg, system, user)
    else:
        raise ValueError(f"Unknown provider: {cfg.provider}")
