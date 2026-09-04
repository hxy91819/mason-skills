# 共享工作区 Git 防护器

这个 wrapper 面向多个用户或 Agent 直接共享同一个 working tree、index 和 Git 元数据的场景。它的目标不是把所有写命令都变成审批流程，而是守住一条边界：一个参与者的 Git 动作不能隐藏、丢弃或覆盖另一个参与者尚未安全持久化的工作。

## 核心原则

1. 严格禁止产生副作用的 stash，包括 `push`、`save`、`create`、`store`、`pop`、`apply`、`drop`、`clear` 和 `branch`。`stash list` 与 `stash show` 只是读取，允许执行。显式或配置启用的 autostash 同样禁止。这条规则没有 `--user-approved` 例外：需要 stash 时，应把现场提交为本地 commit，或者停止操作。
2. 任何 Git 动作都不能丢弃并行参与者的文件内容、暂存状态或恢复锚点。一次预检看到工作区干净并不能证明随后仍然干净；如果命令可以在预检与执行之间捕获并发写入，就按其破坏性语义拦截。
3. 本地 commit 是允许的保全手段。为保存未知归属的现场而创建的 commit 不应推送；它可以在本地 rebase 或改写。普通 rebase 在未启用 autostash 时依赖 Git 自身的脏工作区检查，不隐藏修改，因此不应仅因命令名被拦截。

这三条是防护器的设计依据。未来新增规则时，应先证明动作如何违反其中一条；不能只因为命令“看起来危险”就加入黑名单。若实践证明原则本身有缺口，应先更新这里的风险模型，再同步实现与行为测试。

## 判定模型

防护器按动作的可观察语义分三类：

| 类别 | 处理 | 例子 |
| --- | --- | --- |
| 只读或保留现场 | 透明转发给 Git | `status`、`stash list/show`、`clean -n`、`reset --soft` |
| 由 Git 原生冲突检查保护的正常工作流 | 透明转发给 Git，由 Git 成功或报错 | `commit`、无 autostash 的 `rebase/merge/pull`、普通 `revert`、普通 `apply`、非强制 `rm` |
| 会隐藏、重置、覆盖或删除共享现场 | 返回 77；除 stash 外可在目标已获明确授权时使用单次 `--user-approved` | `restore`、mixed/hard reset、实际 clean、切换分支、force push |

stash 与 autostash 单独采用不可绕过的硬拦截，因为它们的目的就是把当前现场移出 working tree。即使预检时没有 diff，另一个 Agent 也可能在真实 Git 命令开始前保存文件；因此“当前无影响”不是可靠的放行条件。

### 应放行的安全动作

- `git add` 和 `git commit`：把内容变得更耐久，不清除 working tree 中的文件内容。即使 commit 包含了另一个 Agent 的改动，也优先保证内容不丢失；这类临时保全 commit 不得推送。
- `git rebase`、`git merge`、`git pull`：没有 autostash 时允许。Git 会拒绝无法安全处理的本地修改；已经 commit 的内容可随本地历史重写，不应被 wrapper 误杀。
- `git revert`：产生一个新的反向 commit，不隐藏 working tree 内容、不改写已有提交，与 commit 同属创建类动作。序列进行中的 `--abort`、`--skip`、`--quit` 同样放行，这是用户的明确决策：revert 序列只会由本 worktree 内主动发起的 revert 创建，通常由同一参与者立即收尾；若中止了另一个参与者的冲突处理，按共享工作区规则先重新读取现场、恢复兼容内容。
- `git reset --soft`：只移动本地 HEAD，保留 working tree 与 index，符合“本地历史可改写”的约束。
- `git apply`：普通补丁应用属于有上下文校验的编辑动作，现有内容不匹配时由 Git 拒绝或产生显式冲突。整体封禁会阻止正常工作，却不能解决所有编辑器和 shell 写入之间的协作问题；会越出 worktree 的 `--unsafe-paths` 写入仍需拦截，只读 `--check` 不受影响。
- 本地分支创建和查询、所有帮助与 dry-run 命令：不会移除现有内容或引用，允许执行。
- 普通 Git alias：先安全展开，再按真实子命令应用同一套规则。无法静态判断副作用的 `!shell` alias 默认拦截，但在准确命令已经人工审查后可使用单次授权。

### 应拦截的破坏性动作

- 所有产生副作用的 stash，以及 `--autostash`、`rebase.autoStash=true`、`merge.autoStash=true`。`pull` 根据实际选择的 merge/rebase 策略读取相应配置。
- `restore`、path checkout、mixed/hard/merge/keep/patch reset、真实执行的 clean。这些动作会恢复或删除 working tree/index，且基于 diff 的预检存在竞态。
- rebase、merge、cherry-pick 和 am 的 `--abort`、`--skip`、`--quit`。它们会丢弃冲突处理结果或改变另一个参与者可能正在推进的序列状态；`--continue` 和只读查看仍放行。`revert` 不在此列：经用户决定全程放行，理由见放行清单。
- 强制 `rm`、强制 `mv`、分支删除/改名/强制重置、会改变当前 worktree 的 checkout/switch，以及 worktree 管理写操作。
- force/force-with-lease push、远端 ref 删除、mirror 和 prune push，包括配置在 `remote.<name>.push` 或 `remote.<name>.mirror` 中的等价行为。临时保全 commit 不得借这些路径改写或删除远端共享历史；对应 dry-run 仍放行。
- `git prune`、显式 `git gc --prune...` 和 reflog 删除/过期。commit 对象并非永久备份：一旦失去 ref/reflog 可达性并被清理，仍可能物理消失。

## 关于“先 commit，再 rebase”

这个流程不违背“不影响其他 Agent”的原则，前提是 commit 成功包含了需要保留的文件内容，并且不把临时保全 commit 推送到远端。rebase 会改写 commit id 和本地分支历史，但不会把已提交内容重新变成不可恢复的工作区碎片；原提交通常还会在 reflog 中保留一段时间。

commit 不是无限期备份。需要长期保留的节点应保持被分支或 tag 引用；不要随后运行 reflog expire、prune 或立即 GC。发生 rebase 冲突时也不要用 `--skip`、`--abort` 或 reset 来“清场”，应先确认每一份并行工作已经保留。

## 边界

防护器只约束经此 wrapper 发起的 Git 命令，不能保护编辑器中尚未保存的缓冲区，也不能协调 `rm`、文本替换工具或直接调用 `/usr/bin/git` 的绕过行为。普通编辑和补丁应用仍需遵守共享工作区规则：修改前重新读取文件，发现并发变化时合并兼容内容，无法判断同一处语义冲突时停止并询问用户。

`--user-approved=<reason>` 只用于用户已经明确授权了准确目标和影响范围的单次写操作。它不是通用的“我知道有风险”开关，也永远不能放行 stash/autostash。

## 使用与验证

```bash
./install.sh --dry-run
./install.sh
git --wrapper-help
python3 -m unittest -v test_git_shared_worktree_guard.py
```

安装脚本默认把当前目录中的 `git` 软链到 `~/.local/bin/git`。wrapper 透明保留原生 Git 的 stdout、stderr 和退出码；防护器拒绝时返回 77。
