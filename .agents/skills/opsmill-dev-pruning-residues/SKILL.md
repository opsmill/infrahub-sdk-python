---
name: opsmill-dev-pruning-residues
description: Use when an artifact has been argued, iterated, or debugged into its current shape and now carries rationale that only made sense in the process that produced it. Applies to docs, code comments, commit and PR/issue text, and config-file comments. Sweeps the artifact so it states what it does, not why it was argued into that shape. Triggers on "tidy this", "strip the residue", "make this read standalone".
argument-hint: A file path, code range, commit/PR, or the current diff to sweep; defaults to the artifact under discussion
---

# Prune Residue

An artifact that was shaped through a process — a review thread, an iterative coding
session, a debugging back-and-forth — accumulates sentences and comments whose job was
to win or track that process. They are load-bearing *while the work is happening*. In the
finished artifact they are noise: whoever reads it next never saw the process and does not
need to relitigate it.

The principle: **the artifact does the work, so it states what to do — not why it ended up
in this shape.** This skill sweeps an artifact for residue and cuts it, while protecting the
rationale that genuinely changes what the reader or maintainer does.

It applies to:

- **Any artifact** — reference docs, code comments, commit messages, PR/issue descriptions,
  config-file comments. Anything carrying prose that a process left behind.
- **Any process** — human review, an AI pairing/coding session, a debugging loop, plain
  iteration over time. The residue looks the same regardless of who or what produced it.

## The Test

This is the whole skill in one question. For every sentence, clause, or comment that
explains, justifies, compares, or narrates rather than instructs or documents:

> Would a first-time reader or maintainer who never saw the process act differently without it?

- **No** → it's residue. Cut it.
- **Yes — it prevents a mistake the reader would otherwise make, or it's needed to choose
  between options the artifact actually presents** → keep it, but compress to the shortest
  form that still carries the load.

Word count is not the goal. The goal is an artifact where every remaining sentence or comment
either tells the reader what to do, documents what something is, or stops them doing the
wrong thing.

## Residue Patterns to Flag

These appear in prose and in code comments alike:

- **Sequencing justification** — "we do X before Y so that…" when the steps or statements are
  already ordered. The ordering enforces it; just state the step.
- **Defensive comparison** — "rather than Z, which would…", "instead of the obvious approach…",
  "// using a map here instead of a list because…" — defending against an alternative that was
  raised in the process but isn't present. The reader can't see Z, so the defense reads as noise.
- **Process artifacts** — "as discussed", "per feedback", "note that reviewers raised…",
  "this addresses the concern that…", "// per PR review", "// changed to fix the failing test".
- **Meta-hedging** — "you might wonder why…", "it may seem odd, but…", "for clarity…".
- **Restated rationale** — a *why*-clause that only repeats what the instruction or code already
  makes obvious.
- **Provenance narration** — "this previously used X; we switched to Y", "// was a loop, now a
  comprehension", "// refactored per request". That belongs in version-control history, not in
  the artifact.
- **Session narration in commit/PR text** — recounting the back-and-forth ("first tried A, then
  B failed, so C") instead of stating what the change does and why it's correct now.

## What to Keep (load-bearing rationale)

Not all *why* is residue. Keep — but tighten — rationale that:

- **Prevents a real mistake**: "use `--no-verify` because the commit carries conflict markers";
  "// must run before `init()` or the cache is cold" — an ordering constraint the code does not
  enforce on its own.
- **Warns of a non-obvious consequence** the reader can't infer from the action or code itself:
  "// O(n²), but n is bounded < 10 by the schema".
- **Records an external constraint** the artifact can't show: "// HACK: workaround for upstream
  bug opsmill/infrahub#123, remove when fixed"; "// API returns dates as strings, not epochs".
- **Disambiguates a real fork** the artifact presents, where the reader must choose a branch.
- **Actionable `TODO`/`FIXME`** with a concrete next step (as opposed to a stale "// fix later").

When unsure whether a *why* is load-bearing, **keep it and flag it for the user** rather than
cut silently.

## Where Not to Apply This

Some artifacts exist *to record a decision and its alternatives* — there the rationale is the
payload, not residue. Do not sweep:

- **Decision records** — ADRs (MADR "Considered Options" / "Consequences"), `DECISION.md`,
  RFCs, design docs. "X instead of Y because Z" and what was rejected are the whole point.
- **Changelogs / release notes** — provenance ("changed from X to Y") is the content.
- **Post-mortems / retros** — the narrative of what happened is the value.

The test still discriminates: this skill strips rationale that a *process deposited into a doc
whose job is to instruct*. When the doc's job is to record *why a choice was made*, leave its
rationale intact.

## Steps to Follow

1. **Identify the target** — the file, code range, commit, or PR the user named, or the artifact
   under discussion. If it's a diff or PR, sweep only the changed prose and comments, not the
   whole file.
2. **Read it whole.** Residue is usually only visible in context — a sentence or comment reads
   fine in isolation but is redundant given the step, statement, or comment above it.
3. **Classify** each rationale-bearing sentence or comment with the Test above: cut, keep, or
   tighten.
4. **Present the proposed cuts before editing** — a list of `quote → verdict → one-line reason`,
   grouped cut / tighten / kept-but-flagged. Let the user veto any line. Do not edit first and
   explain after.
5. **Apply** the approved cuts — touch prose and comments only (see Important Rules).
6. **Re-lint** with the repo's linters if present, and confirm clean. For code, confirm the
   change is comment-only (e.g. the diff touches no executable lines).
7. **Re-read top-to-bottom as a first-time reader.** Does every step, comment, and statement
   still stand alone without the cut text? If a cut left a gap, the rationale was load-bearing —
   restore it in compressed form.

## Important Rules

- Preserve the artifact's voice and house style; this is a sweep, not a rewrite.
- **Never change executable code.** Edit comments and prose only; leave statements, logic,
  commands, config values, and examples byte-for-byte intact. A comment is fair game; the line
  it describes is not.
