# Fork 维护

这个 fork 只服务于三件事：

1. 每个功能/修复保持为一个独立、聚焦、可以直接向上游提交的分支；
2. 能方便地聚合这些分支，通过 fork 的流水线发布可下载安装的包；
3. 能随时纳入上游的稳定版更新。

除此之外只保留一个可选的安全基线：`security/baseline` 汇总已验收的安全修复，并合入 `main`。没有领域分支、没有补丁登记表、没有冻结清单。分支本身就是状态，`.fork/branches` 是唯一的清单。

## 仓库角色

| 引用 | 作用 |
| --- | --- |
| `upstream` | 上游 <owner>/<repo>，只读 |
| `origin` | 个人 fork，所有推送都去这里 |
| `<release-tag-pattern>` tag | 上游稳定版，`main` 的基线 |
| `security/baseline` | 可选：已验收安全修复的集成分支，合入 `main` |
| `main` | 个人 fork 默认分支，等于基线 tag + 适用的 `security/baseline`；新分支默认起点 |
| `feature/*`、`fix/*` | 每个改动一个分支，基于 `main` |
| `fork-tooling` | 维护规则、`.fork/branches`、聚合脚本、适用的发布流程；和其他分支一样被 merge |
| `aggregate` | 已验证的聚合产物，供打包、部署和分享 |

当前基线是 `.fork/branches` 里 `base` 行的 tag。上游主干上还没进 tag 的提交不追，除非用户明确要求。

个人 fork 的 `main` 是安全默认入口，等于当前基线 tag，并包含适用的 `security/baseline`。GitHub 默认分支设为 `main`，`origin/HEAD` 指向 `origin/main`；普通 clone、从 main 拉分支都包含安全修复。本地 `main` 应与 `origin/main` 一致。`upstream/main` 是上游开发主干，不是日常新分支起点。

`aggregate` / `origin/aggregate` 保存已验证聚合，`aggregate-next` 只是本地临时候选。聚合只提升到 `aggregate`；根目录 `main` 保持基线，不 reset、不改成聚合产物。

## 1. 开发新功能或修复

从 `main` 拉分支。`main` 已包含基线 tag 和适用的 `security/baseline`，所以新分支带安全修复：

```bash
git worktree add .worktrees/<name> -b feature/<name> main   # 修复用 fix/<name>
```

- 不要从裸 tag、`aggregate` 或 `aggregate-next` 拉分支：裸 tag 会漏掉安全修复，聚合分支会带上全部聚合内容，无法单独提给上游。
- 只有真正依赖另一个 fork 分支时，才从那个分支拉出（叠放），并在清单说明里写"叠在 X 上"。
- 修改已有功能：直接在它的分支上继续提交。分支落后于基线也没关系，merge 会处理；只有冲突时才 rebase。
- 完成后：相关测试通过 → 提交 → `git push origin <branch>` 并核对远端 SHA。
- 在 `fork-tooling` 分支的 `.fork/branches` 加一行（分支、上游状态、说明），提交并推送 `fork-tooling`。

## 2. 聚合打包

```bash
scripts/fork-aggregate            # 从 main 生成 .worktrees/aggregate-next 中的本地临时验证候选
scripts/fork-aggregate --promote  # 成功后把结果提升到 aggregate 并推送到 origin
```

脚本从 `origin/main` 开始，先确认 `main` 已包含基线 tag 和适用的 `security/baseline`，再依次 `merge --no-ff` 清单中的分支。每次从头生成，没有中间状态需要维护。`--promote` 只把结果提升到 `aggregate` 并推送到 `origin/aggregate`，不 reset 根目录 `main`；根目录在哪个分支都不影响提升。
在 `.worktrees/aggregate-next` 里按本项目的构建/测试命令验证，通过后再 `--promote`：全量 typecheck/构建，加上本次冲突或新增分支涉及的包的测试；各分支自己的测试在分支上已经跑过。
提升与推送到 `origin` 不需要再询问。有明确安装包的项目，验证并提升聚合后按第 3 节推送 tag，由 CI 打包发布；聚合脚本本身只生成和提升分支，不自动打 tag。替换本机运行中的服务按本项目的部署授权与流程执行。

### 冲突怎么解决

脚本遇到冲突会停下，并判断是哪一类：

| 类型 | 判断 | 处理 |
| --- | --- | --- |
| 分支与上游冲突 | 该分支单独合入 `main` 就冲突 | 在该分支 worktree 里 `git rebase --no-autostash main`，修复、测试、`git push --force-with-lease origin <branch>`，重跑脚本。修好的分支同时也保持了对上游可合并。 |
| 安全基线与新 tag 冲突 | `security/baseline` 合入新 tag 冲突 | 在 `security/baseline` 上 `git merge <new-tag>`，解决并验证后 `git push origin security/baseline`，再更新 `main`。 |
| 分支之间冲突 | 单独都能合入，一起才冲突 | 在 `.worktrees/aggregate-next` 里只做两边合并、不加新行为，`git add` 后 `git commit --no-edit`，重跑脚本。`rerere` 会记住这次解决，下次自动复用。 |

- 产品修复永远回到对应分支，不写在聚合的 merge 提交里。
- 同一对分支反复出现非平凡冲突时，把后者 rebase 到前者上（叠放），更新清单顺序和说明。
- 叠放分支 rebase 时从栈底开始，用 `git rebase --update-refs` 让上层分支一起移动。

### 纳入上游新版本

1. 把 `.fork/branches` 的 `base` 改成新的稳定 tag。有安全基线时先在该分支合并新 tag、解决冲突并验证，推送 `security/baseline`。
2. 把 `main` 更新到新基线：有安全基线时合并 `security/baseline`，没有时合并新 tag；推送 `origin/main`，根目录保持干净的 `main`。
3. 运行聚合脚本，按上表逐个处理冲突。没有冲突的分支不用动；脚本发现 `main` 还没包含新 tag 或基线时会先停下。
4. 某个分支 rebase 后变空，说明上游已经包含它：从清单删除这一行，删除分支（`origin` 上的也删），在提交说明里写明被上游哪个版本吸收。
5. 验证、`--promote`，提交并推送 `fork-tooling` 上的新 `base`。

## 3. 打包与发布

项目有明确安装包和打包方式时，在 `fork-tooling` 中建立 tag 触发的 CI 发布流程，并随它合入聚合。将以下约定落实为本项目的 workflow、打包命令和下载安装步骤；平台、架构、包格式、运行时及原生依赖以实际使用目标为准。没有安装产物的项目说明本节不适用；产物或目标不明确时先澄清该选择，继续不依赖它的维护工作。

### 流水线

- 推送独立于上游版本 tag 的 `fork-v*` annotated tag，构建它指向的已验证聚合 commit。CI 直接检出该源码，不在 CI 或安装机器上重新聚合、rebase。
- 复用项目已有构建和打包工具，配置个人 fork 可用的 runner 和发布目标。默认发布到个人 fork 的 GitHub Releases；上游 runner、npm 身份、发布密钥和自动更新地址需按本 fork 的用途处理，其他发布渠道按用户授权配置。
- 按目标平台构建可下载安装的包，包含需要的编译产物和对应平台依赖。能随包提供的运行时一并提供；需由目标机器安装的系统库或外部工具写清前置条件。目标机器下载后不需要源码聚合、rebase 或本地构建。
- 在构建 job 中完成必要验证及实际安装包的解压/安装、启动或 CLI smoke。生成校验文件和包含 tag、源码 SHA、平台的发布信息，上传这组已验证资产；发布 job 使用同一组资产，不另行重建。
- 资产完整后再公开 Release。中断上传可从 draft 继续；已公开版本保留原资产，修订用新 tag。记录重跑方式和查询发布结果的命令。

首次接入以成功的 fork Release 和下载该包后的安装 smoke 为验收；workflow 写好或 tag 推送成功不能代替这一结果。记录 CI 已验证的平台和仍未验证的目标。

### 日常打包收尾

用户要求聚合打包或构建聚合部署包时，默认通过 tag 触发 CI 完成打包发布，无需再次确认；用户明确要求仅验证、不发布时跳过。本地打包用于调试或验证，不要求每次先线下打包。本地构建或必要验证失败时先修复；CI 构建失败时按下文报告未完成。

1. 记录通过本项目必要验证的待发布聚合 SHA，确认源码和发布 workflow 已推送到 `origin`；已有本地打包结果时使用它实际构建的 SHA。后续分支移动不改变本次发布的源码身份。
2. 查询个人 fork（`origin`）的发布 tag 和 Release。同一 SHA 已成功发布则复用其链接；已有 tag 的构建或上传未成功时，跟踪或重跑原任务。
3. 新发布使用 `fork-v<基线版本>-<UTC日期YYYYMMDD>.<序号>`，递增序号到本地及 `origin` 远端均未使用的名称；tag 指向第 1 步记录的 SHA，并只推送这个 tag 到 `origin`。
4. 核对远端 tag 解引用后的 SHA，跟踪 CI 到结束，确认 Release 已公开且本项目约定的安装包、校验文件齐全。
5. 交付 tag、聚合 SHA、Release 链接和对应平台的下载安装命令。CI 失败、缺少 runner/凭据或无法读取结果时，明确报告发布未完成，保留已完成的工作供继续。

其他机器升级时下载适配平台的已发布包，按本项目文档校验并安装。现有数据目录、启动参数和服务切换沿用本项目的部署规则，不把逐机重新构建作为默认安装方式。

## 4. 向上游反馈

分支本身就是上游 PR 的材料，这也是分支必须保持独立、基于 `main` 的原因。

1. 先在上游搜索是否已有相关 issue/PR，按本项目的 issue/PR 规范准备内容。
2. **向上游提 issue、评论或 PR 之前，必须把拟提交的内容给用户逐项确认。** 用户可以决定把它标为 `fork-only` 保留在本地。
3. 提 PR 时：把分支自己的提交 rebase 到上游主干，去掉安全基线和聚合层：

   ```bash
   git rebase --onto upstream/main "$(git merge-base main <branch>)" <branch>
   ```

   推送到 `origin` 的 `upstream/<name>` 后开 PR；叠放分支要先把依赖部分一并处理或拆开。
4. 在 `.fork/branches` 更新该行的状态和链接（`reported` / `pr-open` / `fork-only`）。
5. 上游合并后，等它进入一个稳定 tag 再从清单移除（见上一节第 4 步）。issue 关闭本身不是移除理由。
