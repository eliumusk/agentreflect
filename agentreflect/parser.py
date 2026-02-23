"""Session log parser for agentreflect.

Supports multiple input formats:
  - JSON: array of message objects [{role, content}, ...]
  - JSONL: one JSON object per line
  - Markdown / plain text: recognizes role markers like User: / Assistant:
  - nanobot session format: auto-detected
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class Message:
    """A single message in a session."""

    role: str          # "user", "assistant", "system", "tool", etc.
    content: str       # message body
    metadata: dict = field(default_factory=dict)  # optional extra info

    def __str__(self) -> str:
        return f"[{self.role.upper()}]\n{self.content}"


@dataclass
class Session:
    """A parsed agent session."""

    messages: List[Message]
    source: str = ""          # filename or "stdin"
    format_detected: str = "" # "json", "jsonl", "text", "nanobot"

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def user_messages(self) -> List[Message]:
        return [m for m in self.messages if m.role == "user"]

    @property
    def assistant_messages(self) -> List[Message]:
        return [m for m in self.messages if m.role == "assistant"]

    def to_text(self) -> str:
        """Convert session to a readable text representation."""
        parts: list[str] = []
        for msg in self.messages:
            parts.append(str(msg))
        return "\n\n".join(parts)

    def stats(self) -> dict:
        """Basic session statistics."""
        total_chars = sum(len(m.content) for m in self.messages)
        return {
            "total_messages": self.message_count,
            "user_messages": len(self.user_messages),
            "assistant_messages": len(self.assistant_messages),
            "total_chars": total_chars,
            "estimated_tokens": total_chars // 4,  # rough estimate
        }


class ParseError(Exception):
    """Raised when a session log cannot be parsed."""
    pass


# ---------------------------------------------------------------------------
# Role normalization
# ---------------------------------------------------------------------------

_ROLE_MAP = {
    "user": "user",
    "human": "user",
    "customer": "user",
    "assistant": "assistant",
    "ai": "assistant",
    "bot": "assistant",
    "agent": "assistant",
    "system": "system",
    "tool": "tool",
    "function": "tool",
}


def _normalize_role(raw: str) -> str:
    """Normalize role string to a standard set."""
    return _ROLE_MAP.get(raw.lower().strip(), raw.lower().strip())


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

def detect_format(content: str) -> str:
    """Detect the format of a session log string.

    Returns one of: 'json', 'jsonl', 'nanobot', 'text'.
    """
    stripped = content.strip()

    # JSON array
    if stripped.startswith("["):
        try:
            data = json.loads(stripped)
            if isinstance(data, list) and len(data) > 0:
                first = data[0]
                if isinstance(first, dict) and ("role" in first or "content" in first):
                    return "json"
        except (json.JSONDecodeError, IndexError):
            pass

    # JSONL — check first few lines
    lines = stripped.split("\n", 5)
    jsonl_count = 0
    for line in lines[:5]:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                jsonl_count += 1
        except json.JSONDecodeError:
            break
    if jsonl_count >= 2:
        return "jsonl"

    # nanobot session format detection
    # nanobot sessions often have specific markers
    if _is_nanobot_format(stripped):
        return "nanobot"

    return "text"


def _is_nanobot_format(content: str) -> bool:
    """Check if content looks like a nanobot session file."""
    markers = [
        "## Human",
        "## Assistant",
        "---",
    ]
    score = sum(1 for m in markers if m in content)
    # Also check for nanobot-specific metadata lines
    if re.search(r"^(session_id|agent|model|timestamp)\s*[:=]", content, re.MULTILINE):
        score += 2
    return score >= 3


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_json(content: str) -> List[Message]:
    """Parse a JSON array of message objects."""
    try:
        data = json.loads(content.strip())
    except json.JSONDecodeError as exc:
        raise ParseError(f"Invalid JSON: {exc}") from exc

    if not isinstance(data, list):
        raise ParseError("JSON content is not an array")

    messages: list[Message] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ParseError(f"Item {i} is not a JSON object")

        role = _normalize_role(item.get("role", "unknown"))
        content_str = item.get("content", "")

        # Handle content that might be a list (OpenAI multi-part format)
        if isinstance(content_str, list):
            text_parts = []
            for part in content_str:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(part.get("text", ""))
                elif isinstance(part, str):
                    text_parts.append(part)
            content_str = "\n".join(text_parts)
        elif not isinstance(content_str, str):
            content_str = str(content_str)

        metadata = {k: v for k, v in item.items() if k not in ("role", "content")}
        messages.append(Message(role=role, content=content_str, metadata=metadata))

    return messages


def parse_jsonl(content: str) -> List[Message]:
    """Parse JSONL format — one JSON object per line."""
    messages: list[Message] = []
    for lineno, line in enumerate(content.strip().split("\n"), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ParseError(f"Invalid JSON on line {lineno}: {exc}") from exc

        if not isinstance(obj, dict):
            continue

        role = _normalize_role(obj.get("role", "unknown"))
        content_str = obj.get("content", "")
        if not isinstance(content_str, str):
            content_str = str(content_str)
        metadata = {k: v for k, v in obj.items() if k not in ("role", "content")}
        messages.append(Message(role=role, content=content_str, metadata=metadata))

    return messages


def parse_text(content: str) -> List[Message]:
    """Parse plain text / markdown session logs.

    Recognizes patterns like:
      User: ...
      Assistant: ...
      Human: ...
      AI: ...
      **User**: ...
      ## User
    """
    # Pattern matches role markers at the start of a line
    role_pattern = re.compile(
        r"^(?:\*\*|##\s*)?("
        r"User|Human|Customer|"
        r"Assistant|AI|Bot|Agent|"
        r"System|Tool"
        r")(?:\*\*)?[:\s]*\n?",
        re.IGNORECASE | re.MULTILINE,
    )

    parts = role_pattern.split(content)

    # parts[0] is text before the first role marker (preamble / metadata)
    # parts[1] is first role, parts[2] is first content, etc.

    messages: list[Message] = []

    if len(parts) < 3:
        # No role markers found — treat the whole thing as a single message
        cleaned = content.strip()
        if cleaned:
            messages.append(Message(role="unknown", content=cleaned))
        return messages

    # Skip preamble (parts[0])
    i = 1
    while i < len(parts) - 1:
        raw_role = parts[i].strip()
        body = parts[i + 1].strip()
        role = _normalize_role(raw_role)
        if body:
            messages.append(Message(role=role, content=body))
        i += 2

    return messages


def parse_nanobot(content: str) -> List[Message]:
    """Parse nanobot-specific session format.

    nanobot sessions use:
      ## Human
      <content>

      ## Assistant
      <content>

      ---
      (separator between turns)

    May also have a metadata header with key: value pairs.
    """
    messages: list[Message] = []

    # Strip optional metadata header
    header_end = 0
    for match in re.finditer(r"^(session_id|agent|model|timestamp)\s*[:=].*$", content, re.MULTILINE):
        header_end = max(header_end, match.end())

    body = content[header_end:].strip()

    # Split by ## markers
    section_pattern = re.compile(
        r"^##\s*(Human|Assistant|User|AI|System|Tool)\s*$",
        re.IGNORECASE | re.MULTILINE,
    )

    parts = section_pattern.split(body)

    # parts[0] = text before first ##, parts[1] = role, parts[2] = content, ...
    i = 1
    while i < len(parts) - 1:
        raw_role = parts[i].strip()
        msg_content = parts[i + 1].strip()
        # Remove trailing --- separators
        msg_content = re.sub(r"\n---\s*$", "", msg_content).strip()
        role = _normalize_role(raw_role)
        if msg_content:
            messages.append(Message(role=role, content=msg_content))
        i += 2

    # Fallback if no ## markers worked
    if not messages:
        return parse_text(content)

    return messages


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_session(content: str, source: str = "") -> Session:
    """Parse a session log from string content.

    Auto-detects format and delegates to the appropriate parser.

    Args:
        content: The raw session log content.
        source: Label for where this content came from (filename, "stdin", etc.).

    Returns:
        A parsed Session object.

    Raises:
        ParseError: If the content cannot be parsed.
    """
    if not content or not content.strip():
        raise ParseError("Empty session log")

    fmt = detect_format(content)

    parser_map = {
        "json": parse_json,
        "jsonl": parse_jsonl,
        "nanobot": parse_nanobot,
        "text": parse_text,
    }

    parser_fn = parser_map.get(fmt, parse_text)
    messages = parser_fn(content)

    if not messages:
        raise ParseError(f"No messages found in session log (detected format: {fmt})")

    return Session(
        messages=messages,
        source=source,
        format_detected=fmt,
    )


def parse_file(filepath: str) -> Session:
    """Parse a session log from a file path.

    Args:
        filepath: Path to the session log file.

    Returns:
        A parsed Session object.

    Raises:
        ParseError: If the file cannot be read or parsed.
        FileNotFoundError: If the file does not exist.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Session file not found: {filepath}")
    if not path.is_file():
        raise ParseError(f"Not a file: {filepath}")

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Try with latin-1 fallback
        content = path.read_text(encoding="latin-1")

    return parse_session(content, source=str(path))
