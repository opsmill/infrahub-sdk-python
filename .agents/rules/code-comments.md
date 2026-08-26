---
paths:
  - "**/*"
---

# Comment and reference rules

Applies to docstrings, comments, and any inline documentation in source files.

## Comment sparingly

- Prefer clear code over explanation. Add a comment only when it conveys intent the code cannot — a non-obvious tradeoff, gotcha, or "why".
- Keep comments as short as possible — one line where you can.
- Do not restate what the code plainly does.
- Never narrate what a change is doing ("# fetch the user", "# loop over the results"). Reviewers repeatedly have to ask for these to be removed.

## What good documentation looks like

- Comment the *why*, never the *what*: a constraint, an invariant, a workaround, a deliberate deviation from the obvious approach. Never paraphrase the line below it or restate the type signature.
- If code needs a comment to explain *what* it does, rename or extract until it doesn't. A comment that restates the code is worse than none - noise that rots the moment the code changes.
- When a why-comment is warranted, one sentence. If the why needs a paragraph, it belongs in the function's docstring or a `dev/knowledge/` page, not inline.
- Public docstrings are different: `uv run invoke docs-generate` publishes them to the SDK reference docs, so they are user-facing API documentation. Document the contract - what it does, its arguments, what it returns, what it raises - in the google convention the `D`/`DOC` ruff rules enforce. Regenerate the docs after changing one.

## No references to other code

Do not name other classes, functions, methods, callers, or call sites in docstrings or comments. Examples of what to avoid:

- "Used by `InfrahubClient` to ..."
- "Called from `execute_graphql` after authentication"
- "See also `NodeParser.transform`"
- "Mirrors the behavior of the sync branch manager"

Why: code is renamed, moved, and deleted. These references rot silently and mislead readers. Well-named identifiers and grep make the relationships discoverable without the comment.

Acceptable exceptions:

- A published docstring may cross-reference another *public* SDK symbol, since that is part of the reference documentation a user reads. Name the public API, never an internal caller.
- Stable public contracts (a protocol or interface that other implementations must satisfy) - name the protocol, not its callers.
- A workaround that depends on a specific upstream library symbol - name the library function and version constraint.
- The async/sync counterpart of the symbol being documented, since the pair is a documented contract.

## Do not reference ephemeral artifacts

Do not reference specs, tasks, plans, tickets, issue numbers, user stories, or the current spec-kit command/feature name in any file — including code, comments, docstrings, `AGENTS.md`, and `CLAUDE.md`. These artifacts are archived over time; every file must stand on its own.

## Type-ignore comments

Use the standard `# type: ignore[<code>]` form (for example `# type: ignore[arg-type]`), never `# ty: ignore`. Only `# type: ignore[...]` is honored by mypy, pyright, and pytype, so a `# ty:` comment suppresses nothing and is dead.
