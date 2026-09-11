<!-- open-source-fork-maintenance:start -->
## Local aggregate fork maintenance

This checkout is maintained as a non-maintainer fork. Its root workspace is the `local/aggregate` integration branch. It is based on the configured upstream ref and is the only checkout used for local integration, packaging, and experience. After verification, publish it to the personal fork as a reusable source snapshot; never use it for an upstream pull request.

Every product change starts on an independent `feature/*` or `fix/*` branch in its own worktree. That worktree owns implementation, tests, commits, `$autoreview` closeout, and fork publication. Invoke `$autoreview` there after development is complete; the branch is verified for aggregation only after that review reports no accepted/actionable findings. Publish every completed, verified source branch and the completed aggregate to the personal fork with normal non-forced pushes. The aggregate receives only verified commits through `git cherry-pick -x`; repair aggregate conflicts in the source worktree and reintroduce a new source commit instead of creating product-only aggregate fixes.

`config/local-aggregate-features.json` is the authoritative registry for each included branch's last packaged source commit, aggregate commit, and upstream feedback issue. Keep this overview synchronized with that registry. Every local `feature/*` and `fix/*` worktree is a default aggregation candidate once it is committed, verified, and registered.

Use `$open-source-fork-maintenance` before upstream synchronization, aggregate rebuilding, or local packaging. It checks new worktrees, source commit changes, upstream changes, and upstream feedback before asking for a rebase or packaging decision. Rebase affected source branches in their own worktrees before rebuilding the aggregate. When the user explicitly declines a rebase, incremental packaging on the existing local baseline remains allowed, but the registry must retain the previous upstream baseline and the result must report the outstanding upstream debt.
<!-- open-source-fork-maintenance:end -->
