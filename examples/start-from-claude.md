Run the local peer-review loop for this task using Claude as builder and Codex as reviewer.

- repo: /path/to/some-project
- task: /path/to/task.md
- builder permission: accept_edits
- reviewer permission: read_only
- create worktree: yes

Assume `AGENT_PEER_REVIEW_TOOLKIT_HOME` is already set on this machine.

If permissions are omitted, use the configured defaults from `config/agents.example.json` for this run.

Use the configured peer-review process yourself. Do not ask me to run a Python command manually.

Return the final markdown summary plus your merge recommendation.
