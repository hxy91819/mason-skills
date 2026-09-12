# Authorized Git history cleanup

## Git History Cleanup

Use only with explicit user approval.

For a new repository, prefer squashing to a clean single root commit:

```bash
git switch --orphan sanitized-main
git rm -r --cached . >/dev/null 2>&1 || true
git add -A
GIT_AUTHOR_NAME='public-name' \
GIT_AUTHOR_EMAIL='public-name@users.noreply.github.com' \
GIT_COMMITTER_NAME='public-name' \
GIT_COMMITTER_EMAIL='public-name@users.noreply.github.com' \
  git commit -m 'Initial open source release'
git branch -D main
git branch -m main
git push --force-with-lease origin main
```

Before force-push:

- Confirm `git status --short --ignored` does not show important untracked
  source files.
- Confirm ignored build outputs, such as `bin/` or `dist/`, are not tracked.
- Run `git ls-files` and inspect the file list.

After force-push:

```bash
git ls-remote --heads origin main
git log --format='%h %an <%ae> | %cn <%ce>' --all
git reflog expire --expire=now --all
git gc --prune=now
```

Then verify old sensitive commits are no longer present locally when their SHAs
are known:

```bash
git cat-file -e OLD_SHA^{commit} 2>/dev/null && echo "old commit still exists"
```

GitHub retains pull-request head refs (`refs/pull/N/head`) after force-push and
branch deletion; old SHAs stay fetchable there and cannot be removed through
git or the API. Report them as residual exposure.
