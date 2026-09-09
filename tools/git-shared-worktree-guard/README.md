# 共享工作区 Git stash 防护器

这个 wrapper 只执行一项用户偏好：不允许有副作用的 stash 与 autostash。

## 规则

- `git stash list` 和 `git stash show` 正常放行；其他 `git stash` 子命令返回 77。
- `rebase`、`merge`、`pull` 的 `--autostash` 返回 77。
- `rebase.autoStash=true` 和 `merge.autoStash=true` 触发的 autostash 返回 77。`pull` 根据实际选用的 rebase 或 merge 策略检查对应配置。
- `--no-autostash` 显式关闭配置中的 autostash。
- 其余 Git 命令直接交给原生 Git。

普通 Git alias 会被静态展开，以便相同规则覆盖 `alias.hide='stash push'` 和 `-c alias.hide=...`。无法静态展开的 shell alias 保持原生 Git 行为。

需要保全现场时，创建本地 commit；需要运行 rebase、merge 或 pull 时，使用 `--no-autostash`。

## 使用与验证

```bash
./install.sh --dry-run
./install.sh
git --wrapper-help
python3 -m unittest -v test_git_shared_worktree_guard.py
```

安装脚本默认把当前目录中的 `git` 软链到 `~/.local/bin/git`。被拒绝的命令返回 77。
