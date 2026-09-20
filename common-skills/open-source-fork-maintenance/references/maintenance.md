# Maintain the aggregate

## Audit and decide

Fetch the registry's upstream ref, then run the linked status helper:

```bash
git fetch --prune --tags <upstream-remote>
node <linked-skill>/scripts/local-aggregate-status.mjs --repo .
```

Read the registered specification, actual upstream feedback, related context, and their relevant replies and pull requests before recommending action. Only `upstreamFeedback` means this change has been reported upstream. A closed issue or merged pull request is an adoption candidate: compare observable behavior, data and synchronization semantics, boundary cases, and verification coverage. Record an intentional upstream policy difference as `upstream-divergence`; keep outdated feedback as `needs-update`. Check whether an adopted fix is present in the selected stable tag as well as on trunk before recommending retirement.

Present four independent facts to the user: source-branch deltas, newly discovered feature/fix branches, upstream deltas or release tags, and feedback/adoption signals. Name the recommended integration ref from the status report. Recommend one of these paths and wait for the user's decision:

- no change on the recommended integration ref: incremental packaging of verified source deltas;
- a newer matching stable tag than the recorded baseline: rebase affected source worktrees onto that tag, verify them, then rebuild the aggregate;
- unreleased trunk after the latest matching tag: report it as debt; keep the recommended target on the tag unless the user explicitly chooses the upstream tip;
- no stable tag configured, and the upstream ref has moved: rebase affected source worktrees onto that ref, verify them, then rebuild the aggregate;
- user explicitly declines rebase: incremental packaging against the current aggregate baseline, retaining and reporting upstream debt;
- upstream implementation fully covers a local branch: validate the upstream behavior before retiring that branch from both the aggregate and registry.

## Rebase source worktrees

Rebase only in the corresponding independent worktree, onto the chosen integration ref (the latest matching stable tag when that is the decision):

```bash
git -C <feature-worktree> status --short
git -C <feature-worktree> rebase --no-autostash <integration-ref>
```

Resolve product conflicts there, rerun the relevant verification, and finish `$autoreview` closeout there before treating the rewritten branch as verified. A rewritten source history requires a complete aggregate rebuild; its previous package record cannot be treated as an incremental range.

## Incremental packaging

Incremental packaging requires a clean root checkout on `local/aggregate` and a recorded source commit that remains an ancestor of the source branch. Package only verified source deltas. If `$autoreview` closeout has not completed in the source worktree, finish it there before cherry-picking. Cherry-pick commits in topological order with `-x`. For a first package, use `git merge-base local/aggregate <branch>` as the lower bound; do not accidentally package unrelated new upstream commits.

If a cherry-pick conflicts, abort it and repair the source worktree. Do not make a product-only fix on the aggregate branch.

## Publish completed snapshots

After the aggregate verification and registry updates succeed, push every completed source branch and `local/aggregate` to the configured personal-fork remote. Use an ordinary push when the remote ref is absent or an ancestor of the local ref. For a deliberately rebased or rebuilt ref, inspect the remote SHA immediately before publication and use `--force-with-lease=<ref>:<observed-sha>`; the skill invocation is standing authorization for this personal-fork maintenance push, so do not request separate approval. Never force-push the upstream remote. Verify every remote SHA after pushing.

The published aggregate is a reproducible source snapshot for another environment. It does not replace that environment's dependency installation or build, and it must never be used as an upstream pull-request branch.

## Complete rebuild

Use a temporary integration worktree based on the chosen integration ref, cherry-pick the confirmed source branches with `-x`, and verify the result. Record the candidate SHA, the aggregate SHA being replaced, the source branches, and verification results, then create a recoverable local backup ref and replace the root `local/aggregate` without another approval prompt. The only remaining confirmation is the project deployment workflow's final replacement of a running local BB service. Never silently use a destructive reset.

After a successful rebuild, update every package record, the human overview in `AGENTS.md`, and `aggregate.lastIntegratedUpstreamCommit`. Do not update the upstream baseline after incremental packaging performed without a rebase.
