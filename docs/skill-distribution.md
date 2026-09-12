# Skill 分发与清单

## Skill 清单维护

`config/skill-symlinks.yaml` 是本仓库推荐 user-scope 软链的单一事实源：记录哪些 skill 推荐软链到全局（`~/.agents/skills`）。外部项目（如 mattpocock-skills）经 `sources:` 按项目名登记，条目加 `source:` 指向项目；项目位置按 `$SKILL_SOURCE_<NAME>_DIR` > `$SKILL_SOURCES_DIR/<项目名>` > 本仓库同级目录解析，清单里绝不写机器绝对路径。其他电脑拉取本仓库后，依据它即可复现同一套 skill 配置，无需口口相传。

- 在 `common-skills/` 新增 skill 且用户要求软链到 user scope 时，必须同步登记清单：
  `python3 common-skills/skill-manifest-sync/scripts/sync_skill_symlinks.py --mode register --skill <name> [--note "..."]`
- 登记外部项目 skill 用 `--mode register --source <项目名> --skill <name>`；项目须已在 `sources:` 声明（缺省自动补一条）。
- 删除或重命名 skill 时用 `--mode remove --skill <name>` 同步清单，避免留下悬空条目。
- 交付涉及 skill 增删的改动前，跑一次 `--mode check` 确认清单与本机实际软链一致。
- 本机同步入口是 `$skill-manifest-sync`：`--mode check` 预览、`--mode apply` 执行。apply 对「指向本仓库或已声明来源项目但不在清单里」的软链逐个提示删除；用户明确说保留时写入本机白名单 `~/.agents/skill-sync-whitelist.yaml`。白名单属于本机环境偏好，不提交 Git，也不得加进仓库的 `.gitignore` 之外的任何清单文件。
- 脚本只管理直接指向本仓库或已声明来源项目的软链：真实目录和经其他工作区中转的链接一律不碰，冲突只报告。
