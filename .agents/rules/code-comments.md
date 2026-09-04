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

Use the standard `# type: ignore[<code>]` form (for example `# type: ignore[arg-type]`), never `# ty: ignore`.
Inline comments carry mypy codes only.

`ty` does not read a bare mypy code as a suppression; it wants either `# ty: ignore[<code>]` or a
`ty:`-prefixed code inside the standard brackets (`# type: ignore[arg-type, ty:invalid-argument-type]`).
Do not use either form. Remaining `ty` violations belong in `[[tool.ty.overrides]]` in `pyproject.toml`,
scoped to the narrowest file or glob that covers them and annotated with the violation count so they can be
retired incrementally.
