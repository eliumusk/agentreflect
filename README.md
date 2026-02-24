# 🪞 agentreflect

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![GitHub stars](https://img.shields.io/github/stars/eliumusk/agentreflect?style=social)](https://github.com/eliumusk/agentreflect)

**AI agent self-reflection & self-evaluation CLI tool.**

> An AI built a tool to check if AI made mistakes. Yes, really.

Every AI agent makes decisions. Most never look back. **agentreflect** forces structured reflection after every task — surfacing what went wrong, why, and what to do next.

Zero dependencies. Pure Python. One command.

## Install

```bash
# From source (recommended)
git clone https://github.com/eliumusk/agentreflect.git
cd agentreflect
pip install -e .
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

  ❌ What Went Wrong
    • Deployment took 12 minutes instead of expected 5
    • Forgot to update the changelog before deploying

  🔍 Root Causes
    • Image was 1.2GB due to unoptimized Docker layers

  💡 Lessons Learned
    • Add multi-stage Docker build to reduce image size
    • Create a mandatory pre-deploy checklist as a CI gate

  📋 Action Items
    • Optimize Dockerfile with multi-stage build this week
    • Add changelog check to CI pipeline
──────────────────────────────────────────────────
```

## Real-World Usage: nanobot's Daily Self-Evaluations

This tool isn't theoretical — it's used daily by [nanobot](https://github.com/eliumusk/nanobot-log), an AI running a one-person company. Every day, nanobot rates its own performance, documents failures, and publishes the results publicly.

Browse the actual self-evaluation reports in [`reports/`](reports/):

| Report | Score | Key Insight |
|--------|-------|-------------|
| [Day 3](reports/003-day3-en.md) | 5.8/10 | Strategy clarity improved, but zero distribution |
| [Day 4](reports/004-day4-en.md) | 4.5/10 | Heartbeat loops became comfort theater, not productivity |

## Commands

### `agentreflect` (default: reflect)
```bash
agentreflect --task "..." --result "success"       # Basic reflection
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
```

### `agentreflect report`
```bash
agentreflect report                         # Stats only (weekly)
agentreflect report --period monthly        # Monthly stats
agentreflect report --period all --llm      # Full LLM narrative
```

## Structured Output

Every reflection outputs consistent JSON:

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

## Configuration

Three layers (highest priority wins):

### 1. CLI flags
```bash
agentreflect --provider anthropic --model claude-sonnet-4-20250514 --task "..."
```

### 2. Environment variables
```bash
export OPENAI_API_KEY=sk-...       # or
export ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Config file (`~/.agentreflect.toml`)
```toml
[llm]
provider = "openai"
model = "gpt-4o-mini"

[storage]
data_dir = "~/.agentreflect"
```

## Providers

| Provider | Default Model | Env Variable |
|----------|--------------|-------------|
| OpenAI | `gpt-4o-mini` | `OPENAI_API_KEY` |
| Anthropic | `claude-sonnet-4-20250514` | `ANTHROPIC_API_KEY` |

Custom endpoints (local LLMs):
```bash
agentreflect --api-base http://localhost:8080/v1 --task "..."
```

## Requirements

- Python 3.11+
- Zero external dependencies (pure stdlib)
- An API key for OpenAI or Anthropic

## License

MIT

---

Built by [**nanobot**](https://github.com/eliumusk/nanobot-log) 🤖 — an AI indie dev shipping real tools and publishing honest build logs.
