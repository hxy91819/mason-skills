---
name: preflight
description: "Verify before implementation starts that a spec or task instruction can actually be completed in this environment: credentials, permissions, tools, and external dependencies are checked and dispositioned."
disable-model-invocation: true
---

开工前核查：spec 或当前指令所依赖的凭据、权限、工具和外部环境是否真正可用。目标：让后续执行任务的 worker 能长时间无人值守运行——凡是会让它跑到一半停下来等用户确认的障碍（缺权限、缺工具、缺 token）都在开工前移除或预先授权，而不是开工后撞上。在 to-spec 之后、implement 之前跑最合适。上下文已有 spec 就核查 spec，否则以当前指令为目标；两者都构不成完整目标时，先请用户补充，不做臆测。

## 流程

1. **列依赖清单。** 扫描 spec/指令中每个将被使用的外部系统、CLI、环境和安装包，逐项写明用途（如"触发 zhiyan 测试流水线"），不臆造 spec 没提的东西。典型类别：凭据与权限（token、账号、云 API profile，内部系统如 zhiyan/stream ci 的权限）、工具与 CLI/安装包、环境访问（连通性、目标环境是否存在）、领域技能（仓库已有对应 skill 就用它的查询命令做验证）。

2. **逐项实测，只读操作。** 能查就查：CLI 只读查询、凭据自检（如 `gh auth status`）、探活请求。记录证据：命令 + 关键输出。读得通不等于写得通——目标动作需要写权限而核查无法安全验证时，标"未验证（写权限需真实操作确认）"。跑不了的项如实标"未验证"，不得当作已通过。

3. **逐项归态。** 每项依赖必须落到三态之一，不允许"以后再说"：
   - **verified**：实测通过，附证据。
   - **resolved-now**：缺的工具或配置现在补齐；涉及安装、写配置等环境改动时，先向用户说明并获同意。
   - **spec'd**：现在解决不了（需要申请权限、token），写进 spec 的"前置条件与授权"章节：缺什么、找谁申请、拿到后 worker 怎么用。spec 没有该章节就追加一节；spec 发布在 issue tracker 就写到 issue 里。
   - 需要用户决策才能归态的项，停下来问；拿到答复再归态，不跳过。

4. **落盘报告。** 产出三态清单表：依赖 / 用途 / 状态 / 证据或处置。spec 可编辑就直接修订，否则作为 issue 评论或独立文件持久化——报告只留在聊天里等于没做，后续 worker 看不到。

## 完成标准

每项依赖都处于三态之一，且报告已持久化。仍有无法归态的项时明确列出交用户决定，不静默通过。