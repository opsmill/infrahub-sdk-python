---
name: opsmill-dev-backporting-fixes
description: >-
  Ports an existing fix from one long-lived branch to another (e.g. a stable fix landed on the
  development branch), adapting it to the target branch's current code rather than cherry-picking
  blindly. TRIGGER when: phrasings like "backport <fix/PR/commit> to <branch>", "port this stable
  fix to develop", "land <ticket> on <branch> too", or a fix that already exists on one branch has
  to land on another. DO NOT TRIGGER when: syncing one whole branch into another wholesale →
  opsmill-dev-merging-branches; replaying local work onto its base → opsmill-dev-rebase; fixing a
  brand-new bug that has no existing fix → opsmill-dev-analyzing-bugs / opsmill-dev-fixing-bugs.
argument-hint: A fix reference on the source branch (commit SHA, merged PR, or ticket) and the target branch to land it on
compatibility: Requires a Git working tree. Locating the source fix and opening the PR need GitHub access (gh CLI authenticated, GitHub MCP server, or equivalent). Composes the `opsmill-dev-commit`, `opsmill-dev-pr`, `opsmill-dev-monitoring-pull-requests`, and `opsmill-dev-creating-issues` skills.
metadata:
  version: 0.1.0
  author: OpsMill
---

# Backport a Fix

Port a single fix that already exists on one branch onto another long-lived branch, **adapting it to the target branch's current code** instead of copying it verbatim. Used when a fix merged on a release/stable line has to also land on the development line (or the reverse), and a plain cherry-pick is wrong because the branches have diverged.

This is **selective and adaptive**: one fix, reshaped to fit the target. That is the opposite of `merging-branches`, which carries a whole branch across wholesale. If the request is "sync all of `<branch>` into `<branch>`", use `merging-branches`; if it is "make *this fix* also work on `<branch>`", use this skill.

This skill is repo-agnostic. The **core workflow** below applies to any OpsMill repo; the **Per-Project Specifics** block near the end is where a repo's concrete base-branch, changelog, and validation conventions live — read the target repo's `AGENTS.md` and `dev/` docs to fill it in.

## The core insight

**A clean cherry-pick is not proof of a correct backport.** The source fix encodes assumptions about the code as it was on the source branch. If the target branch has since diverged in the area the fix touches — a refactor, a new abstraction, a different event or scoping model — copying the fix can compile, merge cleanly, and still be wrong (a no-op, a double-apply, or a violation of an invariant the target added). The work is to understand *what the fix achieves*, then re-express that on the target's terms.

## Inputs

1. **A fix reference on the source branch** — a commit SHA (or range), a merged PR, or a ticket that names the fix. Resolve it to the actual commits and, critically, **the tests that came with it** (the reproduction test and any test the fix changed).
2. **The target branch** the fix must land on.

If either is ambiguous (direction unclear, or only a ticket given), confirm the source commits and the target branch with the user before proceeding.

## Steps to Follow

1. **Locate the source fix and its tests.** From the commit/PR/ticket, identify every commit that makes up the fix, and read them in full:

   ```bash
   git log --oneline <source-branch> | grep -i <keyword>     # find the commit(s)
   git show <sha>                                            # read the change AND its tests
   ```

   Note separately: the **behavior change** (the product code), the **reproduction test**, and any **existing test the fix modified** (often a test that asserted the now-fixed-wrong behavior). You will need all three on the target.

2. **Determine the target base branch.** This is frequently **not** the repo's default branch. A stable→develop backport targets `develop`; the repo default may be `stable`. Confirm against the project's branch model (`AGENTS.md`, `dev/guidelines/git-workflow.md`) rather than assuming `origin/HEAD`.

3. **Set up an isolated worktree off the target base** — the same fresh-worktree-off-`<base>` flow that `merging-branches` (its integration-branch step) and `rebase` already perform, so the backport never disturbs the current checkout. Reuse that canonical flow rather than re-deriving it here; in particular it covers the case this worktree-based workflow actually hits — a branch or worktree pre-created on the *wrong* base — by verifying with `git merge-base --is-ancestor HEAD origin/<target-base>` and resetting an unpushed branch with `git reset --hard origin/<target-base>`. Initialise submodules and install dependencies in the new worktree before running anything.

   > This "fresh worktree off `<base>`" setup is shared with `merging-branches` and `rebase`. Extracting it into one canonical reference the three skills share, so they cannot drift, is worth a follow-up.

4. **Divergence check — the heart of this skill.** Read the target branch's *current* version of the subsystem the fix touches and compare it against what the source fix assumed:

   ```dot
   digraph backport_decision {
     rankdir=LR;
     "Does the target's code in this area\nmatch the source's assumptions?" [shape=diamond];
     "Cherry-pick / apply as-is\n(then still re-validate on target)" [shape=box];
     "ADAPT: re-express the fix on the\ntarget's mechanism, re-derive via tests" [shape=box];
     "Does the target's code in this area\nmatch the source's assumptions?" -> "Cherry-pick / apply as-is\n(then still re-validate on target)" [label="identical"];
     "Does the target's code in this area\nmatch the source's assumptions?" -> "ADAPT: re-express the fix on the\ntarget's mechanism, re-derive via tests" [label="diverged"];
   }
   ```

   - **Identical:** a cherry-pick may apply, but you still re-validate on the target (step 7) — do not assume.
   - **Diverged:** do **not** force the source diff in. Understand what the fix achieves, then implement that against the target's actual structures. Drive it with the reproduction test (port it first, watch it fail on the target, make it pass) — the same discipline as `fixing-bugs`.

5. **Port the tests, and reconcile any test that asserted the old behavior.**
   - Bring the reproduction test across; adapt fixtures/imports to the target.
   - If the target has a test asserting the *pre-fix* behavior (e.g. "X does not happen"), the fix likely inverts it — update or replace that test to assert the corrected behavior. Find these before CI does.

6. **Descope what the target's architecture blocks — never ship a no-op.** Part of the source fix may be unreachable on the target because the target enforces an invariant or lacks a mechanism the source relied on. When a sub-case cannot be made to work without a larger change:
   - Do **not** ship code that emits the right signal but is silently ignored downstream — that *looks* fixed and is worse than an honest gap.
   - Land the part that works, and capture the rest as a linked follow-up (use `creating-issues`), recording the root cause and the architectural constraint.

7. **Validate the ported fix on the target.** Re-run the reproduction test and the reconciled tests **on the target worktree** — passing on the source branch proves nothing here. For runtime-behavioral fixes, exercise it for real (build/run) the way the source fix was validated, not just unit tests.

   > **Gate (T2-verify · P1):** paste the test/run output from the target worktree showing the ported fix actually works there. See `../quality-gates/gates/primitives/evidence-before-done.md`.

8. **Changelog: don't duplicate an entry that will sync over.** If the project uses fragment-based changelogs and the source fix already carries a fragment, that fragment usually arrives on the target through the normal release→development sync. Adding your own duplicates it (and can collide on the next sync). Check whether the fragment already exists on the source branch; if so, omit it here. Add a fragment only when the target genuinely needs one the source won't provide. (Confirm against the project's changelog convention.)

9. **Commit and open the PR** against the **target base** (not the repo default). Delegate branch/commit discipline to `/opsmill-dev-commit` and PR creation to `/opsmill-dev-pr`, then drive CI with `/opsmill-dev-monitoring-pull-requests`.

   > **Ship gate (T2 · P2 + P3) — before `gh pr create`.** Run the ship gate per `../quality-gates/gates/primitives/independent-judge.md` (judge → on-FAIL STOP → R2 degrade → write receipt on PASS). R1 criteria: the source fix's diff and its tests verbatim, plus the target's current code in the touched area (NOT your summary). Artifact: `git diff origin/<target-base>...HEAD`. Forbidden evasions: the merge/rebase-gate evasions in `../quality-gates/gates/primitives/anti-gaming.md`. The judge confirms the fix was **adapted to the target's actual code** (not blindly cherry-picked), is **re-validated on the target**, and any **target-blocked sub-case was descoped into a follow-up**, not shipped as a silent no-op.

10. **Report**: the PR URL and base branch, the final CI status from `/opsmill-dev-monitoring-pull-requests`, what was adapted vs applied as-is, what (if anything) was descoped and the follow-up issue link, and the changelog decision.

## Important Rules

- **Selective and adaptive, not wholesale.** One fix, reshaped for the target. Wholesale branch sync is `merging-branches`.
- **Adapt to the target's code.** A clean cherry-pick that compiles is not proof; when the target diverged, re-express the fix on its terms and re-derive with the reproduction test.
- **Re-validate on the target.** "It passed on the source branch" is not evidence for the target.
- **Never ship a no-op.** If part of the fix is architecturally blocked on the target, descope it into a linked follow-up — do not ship code that looks like a fix but is ignored downstream.
- **Target the right base branch** — usually not the repo default for a backport.
- **Don't duplicate a changelog fragment** that the normal branch sync will carry over.
- The skill's only outputs are the backport branch and its PR; it never pushes to the source, target, or any long-lived branch directly (that is `/opsmill-dev-commit`'s discipline).

## Quality gates

Gates for this skill follow `../quality-gates/gates/gate-model.md`. `backporting-fixes` is **Tier 2 — it lands an adapted fix and opens a PR**.

| Gate | Step / trigger | Tier | Primitives | Pass criteria | On-fail |
|---|---|---|---|---|---|
| Validated-on-target | before opening the PR | T2-verify | P1 | Reproduction + reconciled tests pass **on the target worktree** (paste output); runtime fixes exercised for real. | STOP |
| Adapted-not-copied | before `gh pr create` | T2-ship | P2 + P3 | A fresh judge confirms the fix was adapted to the target's current code (not blindly cherry-picked), re-validated on the target, and any target-blocked sub-case was descoped into a follow-up rather than shipped as a silent no-op. | STOP; adapt/descope; do not open the PR |

## Per-Project Specifics

The core above is generic. Before backporting, read the target repo's `AGENTS.md`, `dev/guidelines/`, and branch-model docs, then record (or append) a block like the template below.

### Template

- **Branch model**: which branch is the backport target for which source (e.g. `stable` → `develop`), and whether the target differs from the repo default.
- **Changelog**: the fragment system and directory, and the rule for backports (usually: omit, the source fragment syncs over).
- **Worktree + setup**: where worktrees live, and the submodule-init / dependency-install commands needed before tests run.
- **Validation**: the local checks and the targeted test command for the touched area (and what is left for CI, e.g. a heavy integration/e2e job).
- **Divergence hot-spots**: subsystems known to differ between the branches, where adaptation (not cherry-pick) is the norm.

Keep exact paths, tool-version pins, and known gotchas in the target repo's own `AGENTS.md` / `dev/` docs — reference them rather than duplicating (and stale-ing) them here.
