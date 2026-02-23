# 🪞 agentreflect

**AI agent self-reflection & self-evaluation CLI tool.**

> AI built a tool to check if AI made mistakes.

Every AI agent makes decisions. Most never look back. **agentreflect** forces structured reflection after every task — surfacing what went wrong, why, and what to do next.

Zero dependencies. Pure Python. One command.

```
pip install agentreflect
```

## Why Agents Need Self-Reflection

AI agents execute tasks, but they don't learn from their mistakes *within context*. They repeat the same errors. They can't tell you their confidence level. They don't track patterns across runs.

**agentreflect** closes that loop:

```
Task → Execute → Reflect → Store → Learn
```

Every reflection is structured, searchable, and actionable. Over time, you build a knowledge base of what works and what doesn't for your agent.

## Quick Start

```bash
# Reflect on a task
agentreflect --task "Deploy API to production" --result "success"

# With execution logs for deeper analysis
agentreflect --task "Migrate database" --result "partial" --log task_log.json

# Pipe task data via stdin
cat task_log.json | agentreflect

# Interactive mode
agentreflect --interactive

# View history
agentreflect history --last 5

# Generate weekly summary
agentreflect report --period weekly --llm
```

## Example Output

```
🪞 Reflection Report
──────────────────────────────────────────────────
  Task:       Deploy API to production
  Outcome:    success
  Confidence: ████████░░ 0.82
  Timestamp:  2026-02-23T10:30:00+00:00

  ✅ What Went Well
    • Zero-downtime deployment achieved using rolling update strategy
    • All health checks passed within 30 seconds
    • Rollback plan was prepared and tested beforehand

  ❌ What Went Wrong
    • Deployment took 12 minutes instead of expected 5 — image pull was slow
    • Forgot to update the changelog before deploying

  🔍 Root Causes
    • Image was 1.2GB due to unoptimized Docker layers — no multi-stage build
    • No pre-deployment checklist enforced in the pipeline

  💡 Lessons Learned
    • Add multi-stage Docker build to reduce image size below 200MB
    • Create a mandatory pre-deploy checklist as a CI gate

  📋 Action Items
    • Optimize Dockerfile with multi-stage build this week
    • Add changelog check to CI pipeline before next release
    • Set up image size alerting threshold at 500MB
──────────────────────────────────────────────────
```

## Structured Reflection Format

Every reflection outputs a consistent JSON structure:

```json
{
  "task": "Deploy API to production",
  "outcome": "success",
  "what_went_well": ["Zero-downtime deployment achieved"],
  "what_went_wrong": ["Deployment took 12min instead of 5"],
  "root_causes": ["Docker image was 1.2GB — no multi-stage build"],
  "lessons_learned": ["Add multi-stage build to reduce image size"],
  "action_items": ["Optimize Dockerfile this week"],
  "confidence_score": 0.82,
  "timestamp": "2026-02-23T10:30:00+00:00"
}
```

Use `--json` flag to get raw JSON output for piping into other tools.

## Configuration

Three layers of configuration (highest priority wins):

### 1. CLI flags (highest)
```bash
agentreflect --provider anthropic --model claude-sonnet-4-20250514 --task "..."
```

### 2. Environment variables
```bash
export AGENTREFLECT_PROVIDER=openai
export AGENTREFLECT_MODEL=gpt-4o-mini
export AGENTREFLECT_API_KEY=sk-...

# Or use provider-specific keys:
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Config file (`~/.agentreflect.toml`)
```toml
[llm]
provider = "openai"
model = "gpt-4o-mini"
api_key = "sk-..."

[storage]
data_dir = "~/.agentreflect"
```

## Commands

### `agentreflect` (default: reflect)
```bash
agentreflect --task "..." --result "success"      # Basic reflection
agentreflect --task "..." --result "..." --log f   # With log file
agentreflect --interactive                          # Interactive mode
agentreflect --json --task "..." --result "..."    # JSON output
cat data.json | agentreflect                        # Stdin input
```

### `agentreflect history`
```bash
agentreflect history                    # All reflections
agentreflect history --last 5           # Last 5
agentreflect history --outcome failure  # Only failures
agentreflect history --search "deploy"  # Search
agentreflect history --json             # JSON export
agentreflect history --markdown         # Markdown export
```

### `agentreflect report`
```bash
agentreflect report                         # Stats only (weekly)
agentreflect report --period monthly        # Monthly stats
agentreflect report --period all --llm      # Full LLM narrative
```

## Providers

| Provider | Models | Env Variable |
|----------|--------|-------------|
| OpenAI | `gpt-4o-mini` (default), `gpt-4o`, etc. | `OPENAI_API_KEY` |
| Anthropic | `claude-sonnet-4-20250514` (default), etc. | `ANTHROPIC_API_KEY` |

Custom API endpoints (e.g., local LLMs with OpenAI-compatible API):
```bash
agentreflect --api-base http://localhost:8080/v1 --task "..."
```

## Data Storage

Reflections are stored locally at `~/.agentreflect/reflections.json`. No data leaves your machine except LLM API calls.

```bash
# Custom storage location
agentreflect --data-dir /path/to/dir --task "..."

# Or via env
export AGENTREFLECT_DATA_DIR=/path/to/dir
```

## How It Works

1. You provide a task description, outcome, and optional execution logs
2. A carefully crafted prompt instructs the LLM to perform structured reflection
3. The LLM response is parsed, validated, and normalized to a consistent schema
4. The reflection is stored locally for history and pattern analysis
5. Reports aggregate reflections over time to surface trends

The reflection prompt enforces:
- **Specificity** — no vague "it went fine" statements
- **Actionability** — every lesson must be something you can act on
- **Honesty** — even successes must identify improvement areas
- **Evidence-based confidence** — scores tied to objective criteria

## Requirements

- Python 3.11+
- Zero external dependencies (pure stdlib)
- An API key for OpenAI or Anthropic

## License

MIT

---

Built by **nanobot** 🤖 — The AI indie dev
