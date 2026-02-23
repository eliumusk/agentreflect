"""Configuration management: TOML file + env vars + CLI flags (three-tier priority)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Minimal TOML parser (stdlib tomllib requires 3.11+, but we inline a tiny
# subset parser so we have zero dependency even on 3.11 where tomllib exists
# but we want to stay import-light).  We actually *do* use tomllib when
# available and fall back to our micro-parser otherwise.
# ---------------------------------------------------------------------------

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]


CONFIG_FILENAME = ".agentreflect.toml"
DATA_DIR_NAME = ".agentreflect"

# Supported LLM providers
PROVIDERS = ("openai", "anthropic")

# Default models per provider
DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-20250514",
}

DEFAULT_MAX_TOKENS = 2048


# ---------------------------------------------------------------------------
# Micro TOML fallback (handles only flat key=value and [section] headers)
# ---------------------------------------------------------------------------

def _micro_toml_parse(text: str) -> dict[str, Any]:
    """Parse a *very* small subset of TOML (flat tables, strings, ints, floats, bools)."""
    result: dict[str, Any] = {}
    current_section: dict[str, Any] = result
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        # Section header
        m = re.match(r"^\[([a-zA-Z0-9_.\-]+)]$", line)
        if m:
            section_name = m.group(1)
            current_section = result.setdefault(section_name, {})
            continue
        # key = value
        m = re.match(r'^([a-zA-Z0-9_.\-]+)\s*=\s*(.+)$', line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        # Detect type
        if val.startswith('"') and val.endswith('"'):
            current_section[key] = val[1:-1]
        elif val.startswith("'") and val.endswith("'"):
            current_section[key] = val[1:-1]
        elif val.lower() in ("true", "false"):
            current_section[key] = val.lower() == "true"
        elif re.match(r'^-?\d+$', val):
            current_section[key] = int(val)
        elif re.match(r'^-?\d+\.\d+$', val):
            current_section[key] = float(val)
        else:
            current_section[key] = val
    return result


def _load_toml(path: Path) -> dict[str, Any]:
    """Load a TOML file, return empty dict if not found."""
    if not path.is_file():
        return {}
    raw = path.read_text(encoding="utf-8")
    if tomllib is not None:
        return tomllib.loads(raw)
    return _micro_toml_parse(raw)


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------

@dataclass
class Config:
    """Resolved configuration (lowest → highest priority: file → env → CLI)."""

    provider: str = "openai"
    model: str = ""
    api_key: str = ""
    api_base: str = ""
    max_tokens: int = DEFAULT_MAX_TOKENS
    data_dir: str = ""
    # Populated but not persisted — transient per invocation
    _source: str = field(default="default", repr=False)

    # -- helpers ----------------------------------------------------------

    @property
    def resolved_model(self) -> str:
        return self.model or DEFAULT_MODELS.get(self.provider, DEFAULT_MODELS["openai"])

    @property
    def resolved_data_dir(self) -> Path:
        if self.data_dir:
            return Path(self.data_dir)
        return Path.home() / DATA_DIR_NAME

    def validate(self) -> list[str]:
        """Return list of validation errors (empty == OK)."""
        errs: list[str] = []
        if self.provider not in PROVIDERS:
            errs.append(f"Unknown provider '{self.provider}'. Choose from: {', '.join(PROVIDERS)}")
        if not self.api_key:
            errs.append(
                f"No API key set. Use --api-key, env AGENTREFLECT_API_KEY / "
                f"{'OPENAI_API_KEY' if self.provider == 'openai' else 'ANTHROPIC_API_KEY'}, "
                f"or set api_key in {CONFIG_FILENAME}"
            )
        return errs


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------

def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def load_config(
    *,
    cli_provider: str | None = None,
    cli_model: str | None = None,
    cli_api_key: str | None = None,
    cli_api_base: str | None = None,
    cli_max_tokens: int | None = None,
    cli_data_dir: str | None = None,
) -> Config:
    """Build a Config by merging file → env → CLI flags."""

    # 1. File
    file_cfg = _load_toml(Path.home() / CONFIG_FILENAME)
    llm_section: dict[str, Any] = file_cfg.get("llm", {})

    # 2. Resolve provider first (needed for env-key lookup)
    provider = (
        cli_provider
        or _env("AGENTREFLECT_PROVIDER")
        or llm_section.get("provider", "")
        or "openai"
    )

    # 3. API key: CLI > AGENTREFLECT_API_KEY > provider-specific env > file
    provider_env_key = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
    api_key = (
        cli_api_key
        or _env("AGENTREFLECT_API_KEY")
        or _env(provider_env_key)
        or str(llm_section.get("api_key", ""))
    )

    api_base = (
        cli_api_base
        or _env("AGENTREFLECT_API_BASE")
        or str(llm_section.get("api_base", ""))
    )

    model = (
        cli_model
        or _env("AGENTREFLECT_MODEL")
        or str(llm_section.get("model", ""))
    )

    max_tokens_str = _env("AGENTREFLECT_MAX_TOKENS")
    max_tokens = (
        cli_max_tokens
        or (int(max_tokens_str) if max_tokens_str else 0)
        or int(llm_section.get("max_tokens", 0))
        or DEFAULT_MAX_TOKENS
    )

    storage_section: dict[str, Any] = file_cfg.get("storage", {})
    data_dir = (
        cli_data_dir
        or _env("AGENTREFLECT_DATA_DIR")
        or str(storage_section.get("data_dir", ""))
    )

    return Config(
        provider=provider,
        model=model,
        api_key=api_key,
        api_base=api_base,
        max_tokens=max_tokens,
        data_dir=data_dir,
    )
