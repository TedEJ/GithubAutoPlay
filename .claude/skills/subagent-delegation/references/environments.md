# Setting the model per subagent

Model IDs, confirmed by the owner on 2026-11-20 (they change over time, so recheck against the Anthropic docs when a new model appears):
- Small: `claude-haiku-5-5`
- Mid: `claude-sonnet-5-5`
- Top: `claude-opus-5-5`

In the Agent tool the `model` parameter takes the aliases `sonnet`, `opus`, `haiku` (and `fable` where offered), and `effort` takes `low` to `max`.

## Claude Code
Subagents are defined as markdown files with frontmatter (project: `.claude/agents/`, user: `~/.claude/agents/`). The `model` field in that frontmatter selects the model for that subagent; it accepts aliases such as `haiku`, `sonnet`, `opus`, or `inherit`. A sensible setup is one agent per tier, for example `scout` (haiku, read-only tools), `engineer` (sonnet) and `architect` (opus), and the delegation brief decides which one gets the task. Verify the exact fields against the current Claude Code docs for your version.

## GithubAutoPlay
`.claude/agents/designer-developer.md` and `reviewer.md` pin `model: sonnet` and carry the hooks. They load in Claude Code in a terminal clone (`/agents`), not in app or Cowork tasks, where the manager starts a general-purpose subagent with the role text in the brief. To run a security review on the top tier, start that general-purpose subagent with `model: opus`; the hook then does not apply, so the brief must say read-only.

## Claude API
Set the `model` parameter on each call. For an orchestrator-worker setup, the main agent runs on its model and issues worker calls with the tier from the rubric, and `effort` or thinking budget settings follow the table where your model supports them.

## Claude.ai chat
There are no subagents here, and the person picks the model in the app. The skill still helps as a way to explain which model suits a task.
