Run the peer-review loop for this task using Codex as builder and Claude as reviewer.

- repo: /path/to/some-project
- task: /path/to/task.md
- builder permission: workspace_write
- reviewer permission: plan
- create worktree: yes

Assume `AGENT_PEER_REVIEW_TOOLKIT_HOME` is already set on this machine.

If permissions are omitted, use the configured defaults from `config/agents.example.json` for this run.

Use the peer-review process yourself. Do not ask me to run a Python command manually.

After it completes, summarize the final markdown handoff and tell me whether you would merge it.
