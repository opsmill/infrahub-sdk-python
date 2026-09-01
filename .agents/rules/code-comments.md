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

## No incidental references to other code

Do not point at code that merely happens to be related: who calls this, what runs before or after it, which internal helper it resembles. Examples of what to avoid:

- "Used by `InfrahubClient` to ..." - a caller
- "Called from `execute_graphql` after authentication" - a call site
- "See also `_resolve_node_id`" - an internal helper
- "Kept in step with the object-spec loader" - an incidental neighbour

Why: code is renamed, moved, and deleted. These references rot silently and mislead readers. Well-named identifiers and grep make the relationships discoverable without the comment.

What stays is the opposite case: a reference that is part of a contract someone else depends on. None of these are incidental, so name them freely.

- Another *public* SDK symbol, named in a published docstring. That docstring is reference documentation, and pointing a user at the related public API is its job.
- A protocol or interface that implementations must satisfy - name the protocol, not its implementers or callers.
- The async or sync counterpart of the symbol being documented, since the pair is itself a documented contract.
- An upstream library symbol a workaround depends on - name the library function and the version constraint that makes it necessary.

## Do not reference ephemeral artifacts

Do not reference specs, tasks, plans, tickets, issue numbers, user stories, or the current spec-kit command/feature name in any file — including code, comments, docstrings, `AGENTS.md`, and `CLAUDE.md`. These artifacts are archived over time; every file must stand on its own.

## Type-ignore comments

Use the standard `# type: ignore[<code>]` form (for example `# type: ignore[arg-type]`), never `# ty: ignore`. Only `# type: ignore[...]` is honored by mypy, pyright, and pytype, so a `# ty:` comment suppresses nothing and is dead.
