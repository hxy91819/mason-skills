---
name: submit-pr-mr
description: 提交 MR/PR（创建 merge request 或 pull request）时使用。先遵循目标仓库自身的 PR/MR 规则，再按四要素组织描述：问题、问题证据、修复方案、修复后证据或本地验证。
disable-model-invocation: true
---

# Submit PR/MR

这是流程类 Skill，默认仅在用户显式调用 `$submit-pr-mr` 时运行。

MR/PR 描述要让 reviewer 不看代码也能回答：问题是什么、凭什么说它存在、为什么这样修、修完怎么确认。本 skill 只约束描述与提交规范，不扩大改动本身。

## 1. 仓库规则优先

写描述前，先查目标仓库自己的规则：

- CONTRIBUTING.md、README 的贡献章节
- PR/MR 模板：`.github/PULL_REQUEST_TEMPLATE.md`、`.gitlab/merge_request_templates/`
- 仓库内 AGENTS.md / CLAUDE.md 的提交约定

仓库有规则的按规则填，包括标题、标签、关联 issue 等格式要求；本 skill 只补它没覆盖的部分，两者冲突时以仓库为准。

## 2. 描述四要素

MR/PR 描述按四个要素组织：

1. **问题**：一句话说清这次改动解决什么问题。
2. **问题证据**：证明问题存在的材料——报错或日志片段、复现步骤、issue 链接、可疑代码位置。写观察到的事实，推断要标明是推断。
3. **修复方案**：通常概要设计即可——关键思路、为什么可行、主要取舍。不逐文件、逐行罗列改动。
4. **修复后证据**：合并后仍能确认的（CI 通过、接口行为可观测）可以省略这一项；一旦省略，必须写清本地做了哪些验证：跑过的测试或命令、手动验证的场景、结果。

完成标准：描述四要素齐全（或第 4 项按规则省略并附本地验证），且 reviewer 不看代码就能回答上面四个问题。
