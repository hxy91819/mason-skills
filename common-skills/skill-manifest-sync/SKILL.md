---
name: skill-manifest-sync
description: 按 config/skill-symlinks.yaml 清单把本机 user-scope skill 软链收敛到仓库推荐状态；需要用户显式调用 $skill-manifest-sync。
disable-model-invocation: true
---

# Skill Manifest Sync

这是流程类 Skill，默认仅在用户显式调用 `$skill-manifest-sync` 时运行。

把仓库 `config/skill-symlinks.yaml`（推荐 user-scope 软链清单）落到当前电脑：创建缺失的软链、修复指向错误的软链、把指向本仓库但不在清单里的软链作为删除候选提示用户，并用本机白名单记录用户确认保留的例外。其他电脑 clone 本仓库后，执行一次即可获得与其他电脑一致的 skill 配置。

与 `harness-config-sync` 的边界：那个 skill 管多宿主之间的 prompt/skills 收敛（事实源 ↔ 各宿主入口）；本 skill 只管「本仓库清单 → user-scope（`~/.agents/skills`）」这一层软链，两者互补不重叠。

## Skill Path（set once）

```bash
export AUTOREVIEW_SYNC="$PWD/common-skills/skill-manifest-sync/scripts/sync_skill_symlinks.py"
# 全局安装时：
export AUTOREVIEW_SYNC="$HOME/.agents/skills/skill-manifest-sync/scripts/sync_skill_symlinks.py"
```

`$AGENTS_HOME` 环境变量可以整体替换 user-scope 根目录（默认 `~/.agents`）。

## 用法

```bash
# 预览本机与清单的差异，不改任何东西；有漂移时退出码 1
python3 "$AUTOREVIEW_SYNC" --mode check

# 执行同步；删除候选逐个交互提示（d 删除 / k 保留并加白名单 / n 跳过）
python3 "$AUTOREVIEW_SYNC" --mode apply

# 非交互（CI、脚本）：删除候选直接删除
python3 "$AUTOREVIEW_SYNC" --mode apply --yes

# 新增 skill 后登记清单（要求 skill 目录已存在于 common-skills/）
python3 "$AUTOREVIEW_SYNC" --mode register --skill my-skill --note "一句话用途"

# 删除/重命名 skill 后清理清单
python3 "$AUTOREVIEW_SYNC" --mode remove --skill my-skill
```

依赖 PyYAML（`pip install pyyaml`）；缺失时脚本以退出码 2 给出安装提示。

## 报告类型

| 类型     | 含义                                                     | apply 行为                     |
| -------- | -------------------------------------------------------- | ------------------------------ |
| `ok`     | 软链与清单一致                                           | 无                             |
| `create` | 清单要求但本机缺失                                       | 创建软链                       |
| `fix`    | 软链指向本仓库内的错误位置（或死链）                     | 修复为清单目标                 |
| `extra`  | 指向本仓库但不在清单里的软链                             | 交互提示删除；`k` 写入白名单   |
| `conflict` | 目标位置被真实目录或指向其他仓库的同名链接占用         | 不动，报告后由用户手动裁决     |
| `stale`  | 清单条目指向不存在的 skill 目录                          | 不动，报告后用 `--mode remove` 或补目录 |

退出码：`0` 已收敛；`1` 存在漂移或未解决的 conflict/stale；`2` 用法或环境错误。

## 白名单与保守边界

- 白名单默认在 `~/.agents/skill-sync-whitelist.yaml`，属于本机环境偏好，**不提交 Git**；条目含 name、reason、recorded_at。
- 脚本只管理「指向本仓库 checkout」的软链：绝不删除真实目录，绝不覆盖指向其他仓库的同名链接（例如 user-scope 的 `article-polish` 指向另一个工作区时，本 skill 不碰它）。
- 删除候选被用户选择保留（k）后写入白名单，后续 check/apply 不再提示；要撤销时直接编辑白名单文件。

## 维护约定

新增、删除或重命名 `common-skills/` 下的 skill 时，按仓库 `AGENTS.md` 的「Skill 清单维护」规则同步更新 `config/skill-symlinks.yaml`（优先用本 skill 的 register/remove 模式），并在提交前跑一次 `--mode check`。