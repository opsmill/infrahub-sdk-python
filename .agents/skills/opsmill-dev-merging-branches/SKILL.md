---
name: opsmill-dev-merging-branches
description: >-
  Merges one long-lived branch into another (e.g. a release branch into the main development
  branch) on a fresh integration branch, or takes over a stalled merge-conflict PR. TRIGGER when:
  phrasings like "merge <release> into <dev>", "take over this merge-conflict PR", or a GitHub PR
  link for a branch sync. DO NOT TRIGGER when: replaying local work onto the latest base → opsmill-dev-rebase;
  opening a pull request → opsmill-dev-pr.
argument-hint: Two branch names (`<source>` into `<destination>`) or a GitHub merge-PR link/number to take over
compatibility: Requires a Git working tree. Opening the draft PR requires GitHub access (gh CLI authenticated, GitHub MCP server, or equivalent). Driving the PR's CI to green uses the `opsmill-dev-monitoring-pull-requests` skill (and the `opsmill-dev-pr` skill to mark it ready-for-review).
metadata:
  version: 0.1.0
  author: OpsMill
---

# Merge Branches

Merge a source branch into a destination branch on a fresh integration branch, resolve conflicts, and open a draft PR that documents what conflicted. Used for periodic release→development syncs (e.g. `stable` → `develop`, `main` → `next`) and for taking over stalled merge-conflict PRs.

This skill is repo-agnostic. The **core workflow** below applies to any OpsMill repo. The **Per-Project Specifics** section near the end is where a given repo's concrete conflict playbook lives — read your project's `AGENTS.md` and `dev/` docs to fill it in, using the template there as a starting shape, not a literal instruction set.

## Inputs

The skill accepts **one** of two input forms:

1. **Two branch names** — `<source>` and `<destination>`. The source is merged *into* the destination.
2. **A GitHub PR reference** — a URL or number of an existing merge PR that is blocked on conflicts. Extract its base (destination) and head (source) branches; the new branch will *take over* that PR.

If the input is ambiguous (e.g. only one branch named, or direction unclear), ask the user which is the source and which is the destination before proceeding.

## Steps to Follow

1. **Resolve inputs**:
   - **If a PR reference was given**: fetch its metadata to determine source/destination and to reference it later:

     ```bash
     gh pr view <pr-number-or-url> --json number,title,url,headRefName,baseRefName,body
     ```

     - `baseRefName` is the destination, `headRefName` is the source.
     - Keep the PR number — the new PR description must mention it ("Supersedes #<n>").
   - **If two branches were given**: assign source and destination per the user's phrasing ("merge X into Y" → source `X`, destination `Y`).

2. **Check working tree is clean**:

   ```bash
   git status
   ```

   - If there are uncommitted changes, stash them (`git stash --include-untracked`) and restore at the end, or ask the user to handle them first.

3. **Fetch latest refs** for both branches:

   ```bash
   git fetch origin <source> <destination>
   ```

4. **Create the integration branch** off the **destination**, named per the project's branch-naming guideline (often `dev/guidelines/git-workflow.md`). If the project states no convention, make the name self-describing — include the source, destination, and merge intent.

   ```bash
   git checkout -b <branch-name> origin/<destination>
   ```

   - **If the branch already exists** (e.g. a worktree was pre-created with this name), verify its base before merging — it may be sitting on the wrong tip. Run `git merge-base --is-ancestor HEAD origin/<destination>` — exit **0** means `HEAD` is an ancestor of `origin/<destination>` (not diverged); **non-zero** means it sits on a different tip. If it exits non-zero and the branch is unpushed (`git ls-remote --heads origin <branch>` is empty), reset it: `git reset --hard origin/<destination>`. **For a PR takeover**, the integration branch must be a *fresh branch off the destination* — do not reuse the stuck PR's source branch.

5. **Merge the source branch** (no fast-forward, so the merge is reviewable):

   ```bash
   git merge --no-ff origin/<source>
   ```

   - If the merge completes cleanly, skip to step 9.

6. **Commit the unresolved conflicts as the merge commit**, so each resolution lands as its own reviewable diff. The merge already staged what it could auto-merge, so stage only the still-conflicted paths and commit with markers intact:

   ```bash
   git diff --name-only --diff-filter=U                 # the conflicted files
   git add $(git diff --name-only --diff-filter=U)       # stage only the conflicted paths
   git commit --no-edit --no-verify                      # merge commit, conflict markers intact
   ```

   Use `--no-verify`: this commit intentionally carries conflict markers, and pre-commit hooks (lint, markers check) would otherwise reject it. The resolution commits in step 8 are verified normally. Do not resolve anything before this commit.

7. **Categorise** each conflicted file: **mechanical** (resolve automatically — see below) vs **non-obvious** (raise to the user — see "When to Raise Conflicts"). Track a running list of what conflicted and how you resolve it — this becomes the PR description.

8. **Resolve conflicts in follow-up commit(s)** on top of the merge commit, so each resolution is independently auditable:
   - For each mechanical conflict, read the file, resolve it, then `git add <file>`.
   - For **non-obvious conflicts**, STOP and present them to the user before resolving (see "When to Raise Conflicts"). Do not guess at semantic merges.
   - A clean auto-merge is not proof of a correct merge. When one side did a sweeping rename/refactor and the other added new call sites, grep the merged tree for both the old and new symbols to confirm consistency.
   - Commit in logical units — one commit per conflict type or file, with a message naming what was resolved — rather than one squashed commit. Reference these resolution commit hashes in the PR's "Conflicts resolved" list so a reviewer can jump straight to each.

9. **Validate** before opening the PR. Run the project's locally-executable CI checks (see "Per-Project Specifics" for the concrete command) and regenerate any generated files touched by the merge (see "Generated Files"). A merge that leaves generated files stale will fail CI. Scope validation to what the merge actually changed — type-check, lint, and run the unit tests for the conflicted modules rather than the whole suite when the substantive change is confined to a few files; **state in the report what was not run** (e.g. functional/integration tests needing a running stack).

> **Gate (T2-verify · P1):** paste the build/test run showing the merged tree is sound after resolving mechanical conflicts. See `../quality-gates/gates/primitives/evidence-before-done.md`.

10. **Push the branch** (confirm with the user first — see Important Rules):

    ```bash
    git push -u origin <branch-name>
    ```

11. **Open the draft PR** (see "PR Description"):

    > **Ship gate (T2 · P2 + P3) — before opening the draft PR.** Run the ship gate per `../quality-gates/gates/primitives/independent-judge.md` (judge → on-FAIL STOP → R2 degrade → write receipt on PASS, all defined there). R1 criteria: the two branches' diffs / the conflicting hunks verbatim (NOT your summary). Artifact: your conflict resolution (the merge diff). Forbidden evasions: the merge/rebase-gate evasions from `../quality-gates/gates/primitives/anti-gaming.md`. The judge confirms refactors and non-obvious (semantic) conflicts were SURFACED for review, not silently resolved.

    ```bash
    gh pr create --draft --base <destination> --head <branch-name> \
      --title "Merge <source> into <destination>" \
      --body "$(cat <<'EOF'
    <body — see PR Description section>
    EOF
    )"
    ```

12. **Drive the PR's CI to green** by invoking the `/opsmill-dev-monitoring-pull-requests` skill on the new PR.

13. **Report** the new PR URL, the final CI status from `/opsmill-dev-monitoring-pull-requests`, and a summary of conflicts resolved / raised. Surface the conflicts and behavioral decisions only — omit task-tracking scaffolding. When the PR is green and ready, the `/opsmill-dev-pr` skill can promote it from draft to ready-for-review.

14. **Restore any stashed changes** from step 2 (`git stash pop`), resolving conflicts if they arise.

## When to Raise Conflicts

Resolve **mechanical** conflicts silently; **raise** anything that requires a judgement call. Raise (do not auto-resolve) when:

- Both sides changed the **same logic** in incompatible ways (not just adjacent lines).
- A conflict spans a **refactor** — code was moved, renamed, or restructured on one side and edited on the other. If the refactor was a pure move/rename/encapsulation and the incoming edit still makes sense in its new home, port it across and resolve — but **note it in the report** so a reviewer can sanity-check the placement. Raise it only when the surrounding logic itself changed, so the incoming edit no longer applies cleanly.
- Resolving requires **understanding intent** — e.g. two different bug fixes to the same function, conflicting API signatures, diverging business logic.
- A conflict touches **migrations**, **auth/authorization**, **API/GraphQL schema**, or **database** code where a wrong merge has outsized consequences (these are typically "Ask First" areas per the project's `AGENTS.md`).
- You are **not confident** the resolution preserves both sides' intent.

When raising, show the conflicting hunks, explain what each side did, and propose options. Wait for direction before committing the merge. When a resolution combines both sides, adapt and run the matching test as part of it.

## Mechanical Conflict Types

> **`--ours` vs `--theirs` during a merge.** The integration branch is the **destination** and is checked out as `HEAD`, so during `git merge origin/<source>`, `--ours` = the destination and `--theirs` = the source. To "accept the destination version", use `--ours`.

### Generated Files (regenerate, never hand-merge)

Never resolve a generated file by hand. Accept the destination version, then run the project's generate task and re-stage:

```bash
git checkout --ours <generated-paths...>
<project generate command>
git add <generated-paths...>
```

After regenerating, `git status` over the generated trees — an **empty result confirms the merge left nothing stale**. If a generator pulls from a submodule (or any external input), make sure that input is at the commit the merge records *before* trusting the diff.

Lockfiles, generated client types, vendored submodules, and numbered migrations are common mechanical conflicts too, but how to resolve them is project-specific (which package manager and version, which generate command, which submodule, how migrations are numbered). Read the target repo's `AGENTS.md` / `dev/` docs and follow its **Per-Project Specifics** block — see the template below for the shape.

### Changelog Fragments

Fragment-based changelogs (e.g. towncrier under `changelog/`) use independent per-change files; conflicts are rare. If both sides added fragments, keep both.

## PR Description

The draft PR body must describe **what conflicted and how it was resolved**, so a reviewer can verify the merge without re-doing it:

```markdown
## Summary

Merges `<source>` into `<destination>`.

## Conflicts resolved

- `<file>` — <one line: what each side changed and how it was reconciled> (`<resolution commit hash>`)

(If there were no conflicts: "Clean merge, no conflicts.")

## Conflicts raised for review

- `<file>` — <what required a judgement call and the decision taken> (omit section if none)

## Generated files regenerated

- <list of generate commands run> (omit if none)
```

If the input was a **PR takeover**, add at the top of the body:

```markdown
Supersedes #<original-pr-number>, which was blocked on merge conflicts.
```

Use the bare `#<number>` form only (not the full PR URL).

## Important Rules

Recap of the guardrails enforced in the steps above:

- The integration branch is created off the **destination**; the source is merged into it. Never the reverse.
- Always open the PR as a **draft** (`--draft`).
- Never auto-resolve conflicts in migrations, auth, API/GraphQL schema, or DB code without raising them first.
- Never edit generated files by hand — accept one side and regenerate.
- Confirm with the user before pushing. The skill's only outputs are the integration branch and a draft PR — it never pushes to the source, destination, or any long-lived branch.
- Run the project's local CI checks and ensure generated files are committed before marking the PR ready — CI validates this.

## Quality gates

Gates for this skill follow `../quality-gates/gates/gate-model.md`. `merging-branches` is **Tier 2 — it merges a source branch and opens a draft PR**.

| Gate | Step / trigger | Tier | Primitives | Pass criteria | On-fail |
|---|---|---|---|---|---|
| Mechanical-conflicts | during resolution | T2-verify | P1 | Mechanical conflicts resolved; build/tests pass. Paste output. | STOP |
| Semantic-surfaced | before opening the draft PR | T2-ship | P2 + P3 | A fresh judge confirms refactors / non-obvious (semantic) conflicts were SURFACED for review, not silently resolved. | STOP; surface the conflicts; do not open the PR |

## Per-Project Specifics

The core above is deliberately generic. Before resolving, read the target repo's `AGENTS.md`, `dev/guidelines/`, and `dev/commands/` to learn its concrete paths and commands, then apply the matching conflict-type sections. Fill in (or append) a block like the template below for the repo you're in.

### Template

A per-project block is short — the conflict-type *what* lives in the core above; this records the repo's concrete *how*. Fill in the bullets that apply:

- **Validation**: the repo's local CI checks to run before pushing (lint, type-check, generated-doc gates, the test scope).
- **Generated files**: which paths are generated, and the command that regenerates them (accept the destination version, regenerate, then stage).
- **Lockfiles / generated types**: the package manager and pinned version, and the regenerate command.
- **Submodules**: which submodules exist and how to sync them to the recorded commit.
- **Migrations**: how they're numbered and what to renumber/bump on conflict.
- **Canonical sync**: the usual direction, e.g. `<release-branch>` → `<development-branch>`.

Keep exact paths, tool-version pins, and known generator gotchas in the target repo's own `AGENTS.md` / `dev/` docs — reference them rather than duplicating (and stale-ing) them here.
