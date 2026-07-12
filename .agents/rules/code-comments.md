---
paths:
  - "**/*"
---

# Comment and reference rules

## Comment sparingly

- Prefer clear code over explanation. Add a comment only when it conveys intent the code cannot — a non-obvious tradeoff, gotcha, or "why".
- Keep comments as short as possible — one line where you can.
- Do not restate what the code plainly does.

## Do not reference ephemeral artifacts

Do not reference specs, tasks, plans, tickets, issue numbers, user stories, or the current spec-kit command/feature name in any file — including code, comments, docstrings, `AGENTS.md`, and `CLAUDE.md`. These artifacts are archived over time; every file must stand on its own.

## Type-ignore comments

Use the standard `# type: ignore[<code>]` form (for example `# type: ignore[arg-type]`), never `# ty: ignore`. Only `# type: ignore[...]` is honored by mypy, pyright, and pytype, so a `# ty:` comment suppresses nothing and is dead.
