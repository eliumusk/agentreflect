"""CLI entry point — argparse-based command interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentreflect import __version__
from agentreflect.config import load_config
from agentreflect.reflect import reflect, reflect_interactive
from agentreflect.report import generate_report
from agentreflect.storage import export_markdown, load_reflections

# ---------------------------------------------------------------------------
# Colours (ANSI, auto-disabled when not a tty)
# ---------------------------------------------------------------------------

_IS_TTY = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    if not _IS_TTY:
        return text
    return f"\033[{code}m{text}\033[0m"


def _green(t: str) -> str:
    return _c("32", t)

def _yellow(t: str) -> str:
    return _c("33", t)

def _red(t: str) -> str:
    return _c("31", t)

def _bold(t: str) -> str:
    return _c("1", t)

def _dim(t: str) -> str:
    return _c("2", t)

def _cyan(t: str) -> str:
    return _c("36", t)


# ---------------------------------------------------------------------------
# Pretty-print a reflection
# ---------------------------------------------------------------------------

_OUTCOME_STYLE = {
    "success": _green,
    "partial": _yellow,
    "failure": _red,
}


def _print_reflection(r: dict) -> None:
    """Pretty-print a single reflection to stdout."""
    outcome_fn = _OUTCOME_STYLE.get(r.get("outcome", ""), _dim)
    print()
    print(_bold("🪞 Reflection Report"))
    print(_dim("─" * 50))
    print(f"  {_bold('Task:')}       {r.get('task', 'N/A')}")
    print(f"  {_bold('Outcome:')}    {outcome_fn(r.get('outcome', 'N/A'))}")
    print(f"  {_bold('Confidence:')} {_confidence_bar(r.get('confidence_score', 0))}")
    print(f"  {_bold('Timestamp:')}  {r.get('timestamp', 'N/A')}")
    print()

    _print_list("✅ What Went Well", r.get("what_went_well", []), _green)
    _print_list("❌ What Went Wrong", r.get("what_went_wrong", []), _red)
    _print_list("🔍 Root Causes", r.get("root_causes", []), _yellow)
    _print_list("💡 Lessons Learned", r.get("lessons_learned", []), _cyan)
    _print_list("📋 Action Items", r.get("action_items", []), _bold)
    print(_dim("─" * 50))


def _confidence_bar(score: float) -> str:
    """Render a visual confidence bar."""
    try:
        score = float(score)
    except (TypeError, ValueError):
        return "N/A"
    filled = int(score * 10)
    bar = "█" * filled + "░" * (10 - filled)
    color_fn = _green if score >= 0.7 else (_yellow if score >= 0.4 else _red)
    return f"{color_fn(bar)} {score:.2f}"


def _print_list(header: str, items: list, color_fn) -> None:
    if not items:
        return
    print(f"  {_bold(header)}")
    for item in items:
        print(f"    {color_fn('•')} {item}")
    print()


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def _cmd_reflect(args: argparse.Namespace) -> int:
    """Handle the default reflect command."""
    cfg = load_config(
        cli_provider=args.provider,
        cli_model=args.model,
        cli_api_key=args.api_key,
        cli_api_base=args.api_base,
        cli_max_tokens=args.max_tokens,
        cli_data_dir=args.data_dir,
    )

    errors = cfg.validate()
    if errors:
        for e in errors:
            print(_red(f"Error: {e}"), file=sys.stderr)
        return 1

    if args.interactive:
        result = reflect_interactive(cfg)
        _print_reflection(result)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    # Determine task / result / log
    task = args.task or ""
    result_text = args.result or ""
    log_text = ""

    # Read log from file
    if args.log:
        log_path = Path(args.log)
        if not log_path.is_file():
            print(_red(f"Error: log file not found: {args.log}"), file=sys.stderr)
            return 1
        log_text = log_path.read_text(encoding="utf-8")

    # Read from stdin if no task provided and stdin has data
    if not task and not sys.stdin.isatty():
        stdin_data = sys.stdin.read().strip()
        if stdin_data:
            # Try to parse as JSON to extract task/result
            try:
                parsed = json.loads(stdin_data)
                if isinstance(parsed, dict):
                    task = parsed.get("task", parsed.get("description", ""))
                    result_text = result_text or parsed.get("result", parsed.get("outcome", ""))
                    log_text = log_text or parsed.get("log", json.dumps(parsed, indent=2))
                else:
                    log_text = stdin_data
                    task = task or "Review task from stdin"
            except json.JSONDecodeError:
                log_text = stdin_data
                task = task or "Review task from stdin"

    if not task:
        print(_red("Error: --task is required (or pipe data via stdin, or use --interactive)"), file=sys.stderr)
        return 1

    if not result_text:
        result_text = "unknown"

    data = reflect(cfg, task=task, result=result_text, log=log_text)

    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        _print_reflection(data)

    return 0


def _cmd_history(args: argparse.Namespace) -> int:
    """Handle the history subcommand."""
    cfg = load_config(cli_data_dir=args.data_dir)
    records = load_reflections(
        cfg.resolved_data_dir,
        last=args.last,
        outcome=args.outcome,
        search=args.search,
    )

    if not records:
        print(_dim("No reflections found."))
        return 0

    if args.json:
        print(json.dumps(records, indent=2, ensure_ascii=False))
        return 0

    if args.markdown:
        print(export_markdown(records))
        return 0

    # Default: compact list
    for i, r in enumerate(records, 1):
        outcome = r.get("outcome", "?")
        outcome_fn = _OUTCOME_STYLE.get(outcome, _dim)
        conf = r.get("confidence_score", "?")
        task = r.get("task", "Untitled")
        ts = r.get("timestamp", "")[:10]
        print(f"  {_dim(f'[{ts}]')} {outcome_fn(f'[{outcome:>7s}]')} {task}  {_dim(f'conf={conf}')}")

    print(_dim(f"\n  Total: {len(records)} reflection(s)"))
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    """Handle the report subcommand."""
    cfg = load_config(
        cli_provider=args.provider,
        cli_model=args.model,
        cli_api_key=args.api_key,
        cli_api_base=args.api_base,
        cli_data_dir=args.data_dir,
    )

    use_llm = args.llm
    if use_llm:
        errors = cfg.validate()
        if errors:
            for e in errors:
                print(_red(f"Error: {e}"), file=sys.stderr)
            return 1

    output = generate_report(cfg, period=args.period, use_llm=use_llm)
    print(output)
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentreflect",
        description="🪞 AI agent self-reflection & self-evaluation CLI tool",
        epilog="Built by nanobot 🤖 — The AI indie dev",
    )
    parser.add_argument("-V", "--version", action="version", version=f"agentreflect {__version__}")

    # Global options
    parser.add_argument("--provider", choices=["openai", "anthropic"], help="LLM provider")
    parser.add_argument("--model", help="Model name")
    parser.add_argument("--api-key", help="API key")
    parser.add_argument("--api-base", help="Custom API base URL")
    parser.add_argument("--max-tokens", type=int, help="Max tokens for LLM response")
    parser.add_argument("--data-dir", help="Data directory (default: ~/.agentreflect)")
    parser.add_argument("--json", action="store_true", help="Output as raw JSON")

    subparsers = parser.add_subparsers(dest="command")

    # --- Default reflect (no subcommand needed) ---
    parser.add_argument("--task", "-t", help="Task description")
    parser.add_argument("--result", "-r", help="Task outcome (success/partial/failure)")
    parser.add_argument("--log", "-l", help="Path to execution log file")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive reflection mode")

    # --- history ---
    hist = subparsers.add_parser("history", help="View reflection history")
    hist.add_argument("--last", type=int, help="Show last N reflections")
    hist.add_argument("--outcome", choices=["success", "partial", "failure"], help="Filter by outcome")
    hist.add_argument("--search", "-s", help="Search reflections")
    hist.add_argument("--json", action="store_true", help="Output as JSON")
    hist.add_argument("--markdown", "--md", action="store_true", help="Output as Markdown")
    hist.add_argument("--data-dir", help="Data directory")

    # --- report ---
    rep = subparsers.add_parser("report", help="Generate summary report")
    rep.add_argument("--period", choices=["daily", "weekly", "monthly", "all"], default="weekly", help="Report period (default: weekly)")
    rep.add_argument("--llm", action="store_true", help="Use LLM to generate narrative summary")
    rep.add_argument("--provider", choices=["openai", "anthropic"], help="LLM provider")
    rep.add_argument("--model", help="Model name")
    rep.add_argument("--api-key", help="API key")
    rep.add_argument("--api-base", help="Custom API base URL")
    rep.add_argument("--data-dir", help="Data directory")

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "history":
        code = _cmd_history(args)
    elif args.command == "report":
        code = _cmd_report(args)
    else:
        # Default: reflect
        # If no args at all, show help
        if not args.task and not args.interactive and sys.stdin.isatty():
            parser.print_help()
            sys.exit(0)
        code = _cmd_reflect(args)

    sys.exit(code)
