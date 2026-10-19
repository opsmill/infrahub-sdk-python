# Testing a change against Infrahub's CI

Infrahub installs the SDK from its `python_sdk` git submodule, as an editable install, and uses it in its backend, in `infrahubctl` and in its pytest plugin. The CI of this repository does not run Infrahub's tests, so a change to code that Infrahub calls can pass here and still break Infrahub.

To find out before merging, open a draft pull request in `opsmill/infrahub` that changes nothing but the submodule commit, and read its CI results. A change to `python_sdk` starts Infrahub's backend jobs.

## Pick the Infrahub branch

Each Infrahub branch pins one SDK commit in `python_sdk`:

- For an SDK pull request into `stable`, use Infrahub `stable`, which receives the SDK releases.
- For an SDK pull request into `infrahub-develop`, use Infrahub `develop`.

For any other base branch, find the Infrahub branches whose pinned commit is on your SDK base branch, and use the one whose pinned commit is the most recent. The commit that Infrahub `stable` pins is on every SDK branch, because `stable` is merged into the other SDK branches, so use Infrahub `stable` only when no other Infrahub branch matches. `git ls-tree origin/<infrahub-branch> python_sdk` shows the pinned commit.

## Bring the SDK branch up to date

The SDK branch must contain the commit that the Infrahub branch pins. Otherwise, moving the submodule also removes SDK changes that Infrahub already depends on, and Infrahub's CI fails for reasons unrelated to your change.

From a checkout of `opsmill/infrahub` on the Infrahub branch, check out the pinned commit in the submodule, then compare it with the SDK branch:

```bash
git submodule update --init python_sdk
git -C python_sdk fetch origin <sdk-branch>
git -C python_sdk merge-base --is-ancestor HEAD FETCH_HEAD && echo "up to date"
```

If nothing is printed, merge the SDK base branch into your SDK branch, push it and check again.

## Open the pull request

From a checkout of `opsmill/infrahub`, here for Infrahub `develop`:

```bash
git fetch origin develop
git switch -c <branch> origin/develop
git submodule update --init python_sdk
git -C python_sdk fetch origin <sdk-branch>
git -C python_sdk checkout FETCH_HEAD
git add python_sdk
git commit -m "chore: point python_sdk at <sdk-branch> (do not merge)"
git push -u origin <branch>
gh pr create --draft --base develop --title "[DO NOT MERGE] Run Infrahub CI against <sdk-branch>" --body "Runs Infrahub CI against <sdk-pr-url>. Do not merge."
```

`git diff --cached --stat` before the commit must list `python_sdk` only. In the pull request description, link the SDK pull request and say that the pull request exists only to run CI.

## Read the results

- Compare a failing job with the latest run of the same job on the Infrahub branch. A job that also fails there is not caused by the SDK change.
- Link the Infrahub pull request from the SDK pull request, with the result.
- Close the Infrahub pull request and delete its branch when you are done. It is never merged: SDK releases reach Infrahub through Infrahub's submodule update workflow.
