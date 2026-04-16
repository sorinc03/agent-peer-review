# Claude Package

This directory contains a Claude Code-friendly package built around Anthropic's documented subagent format.

## Why this exists

Anthropic officially supports subagents stored as Markdown files with YAML frontmatter in:

- `~/.claude/agents/` for user-level agents
- `.claude/agents/` for project-level agents

This repo ships the peer-review orchestrator in that format so users can install it directly today, without waiting on a separate plugin marketplace packaging step.

## Included file

- `.claude/agents/peer-review-orchestrator.md`

## Install globally

```bash
mkdir -p ~/.claude/agents
cp claude-package/.claude/agents/peer-review-orchestrator.md ~/.claude/agents/
```

## Install into a target repo

```bash
mkdir -p /path/to/target-repo/.claude/agents
cp claude-package/.claude/agents/peer-review-orchestrator.md /path/to/target-repo/.claude/agents/
```

## Notes

- Set `AGENT_PEER_REVIEW_TOOLKIT_HOME` on your machine before using the subagent.
- The human-facing entry point is still conversational: start `claude`, then ask it to use the peer-review process.
- This package is intentionally simple and aligned with Anthropic's documented subagent format. If Anthropic stabilizes a richer public plugin packaging standard or marketplace manifest flow, this repo can wrap the same orchestrator with that packaging later.
