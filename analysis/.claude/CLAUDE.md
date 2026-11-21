# graphify
- **graphify** (`.claude/skills/graphify/SKILL.md`) - any input to knowledge graph. Trigger: `/graphify`
When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

## Knowledge graph (graphify)

- The whole repository is mapped in `../graphify-out/` at the repo root (`GRAPH_REPORT.md`, `graph.json`).
- Before searching for files or symbols with Grep/Glob or reading many files, check the graph first: read `../graphify-out/GRAPH_REPORT.md` for the overview, or query `../graphify-out/graph.json` (use `graphify query` or the graphify skill). Fall back to Grep/Read only when the graph does not answer the question.
- Keep the graph current: `graphify watch .` run from the repo root rebuilds it on file changes. A git `post-commit` hook rebuilds it after each commit.
- Do not edit files under `graphify-out/`; they are generated.
