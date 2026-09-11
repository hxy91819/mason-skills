# Maintain the aggregate

## Audit and decide

Fetch the registry's upstream ref, then run the linked status helper:

```bash
git fetch --prune --tags <upstream-remote>
node <linked-skill>/scripts/local-aggregate-status.mjs --repo .
```

Read the full registered issue, replies after the recorded feedback, and any linked pull request before recommending action. A closed issue or merged pull request is only an adoption candidate. Compare the upstream result with the local branch's observable behavior, data and synchronization semantics, boundary cases, and verification coverage before suggesting that a branch be retired.

Present four independent facts to the user: source-branch deltas, newly discovered feature/fix branches, upstream deltas or release tags, and feedback/adoption signals. Recommend one of these paths and wait for the user's decision:

- no upstream change: incremental packaging of verified source deltas;
- upstream change: rebase affected source worktrees, verify them, then rebuild the aggregate;
- user explicitly declines rebase: incremental packaging against the current aggregate baseline, retaining and reporting upstream debt;
- upstream implementation fully covers a local branch: validate the upstream behavior before retiring that branch from both the aggregate and registry.

## Rebase source worktrees

Rebase only in the corresponding independent worktree:

```bash
git -C <feature-worktree> status --short
git -C <feature-worktree> rebase --no-autostash <upstream-ref>
```

Resolve product conflicts there, rerun the relevant verification, and finish `$autoreview` closeout there before treating the rewritten branch as verified. Rebase rewrites history, so get separate approval before `git push --force-with-lease` to a published fork branch. A rewritten source history requires a complete aggregate rebuild; its previous package record cannot be treated as an incremental range.

## Incremental packaging

Incremental packaging requires a clean root checkout on `local/aggregate` and a recorded source commit that remains an ancestor of the source branch. Package only verified source deltas. If `$autoreview` closeout has not completed in the source worktree, finish it there before cherry-picking. Cherry-pick commits in topological order with `-x`. For a first package, use `git merge-base local/aggregate <branch>` as the lower bound; do not accidentally package unrelated new upstream commits.

If a cherry-pick conflicts, abort it and repair the source worktree. Do not make a product-only fix on the aggregate branch.

## Publish completed snapshots

After the aggregate verification and registry updates succeed, push every completed source branch and `local/aggregate` to the configured personal-fork remote with ordinary, non-forced pushes. First verify that each remote ref is absent or an ancestor of its local ref; a divergent published ref requires a user decision rather than a force-push. Verify the remote SHA after pushing.

The published aggregate is a reproducible source snapshot for another environment. It does not replace that environment's dependency installation or build, and it must never be used as an upstream pull-request branch.

## Complete rebuild

Use a temporary integration worktree based on the selected upstream, cherry-pick the confirmed source branches with `-x`, and verify the result. Before replacing the root `local/aggregate`, show the user the candidate SHA, the aggregate SHA being replaced, the source branches, and verification results. Obtain a second explicit confirmation for that replacement. Create a recoverable local backup ref; never silently use a destructive reset.

After a successful rebuild, update every package record, the human overview in `AGENTS.md`, and `aggregate.lastIntegratedUpstreamCommit`. Do not update the upstream baseline after incremental packaging performed without a rebase.
