---
kind: story
id: STORY-01
epic: EPIC-FORWARD
title: 创建并验证问候文件
gate: COMPONENT
depends_on: []
updated: 2026-08-30
intent_version: 1
language: zh-Hans
---

# 创建并验证问候文件

<!-- large-task-planning:vision -->
## 愿景

仓库根目录出现一个内容确定的问候文件，任何执行者都能通过现有脚本复核结果。

<!-- large-task-planning:scope -->
## 范围

创建 `greeting.txt`，内容为单行 `hello from orchestrated worker`；运行 `./check.sh`。不修改检查脚本、依赖或其他产品文件。

<!-- large-task-planning:key-decisions -->
## 关键决策

<!-- large-task-planning:decision owner=user -->
1. **问候内容和文件路径固定，不由执行者选择。**
   - 决定者：用户。
   - Agent 建议：使用单文件确定性夹具，使 worker 与 validator 的职责可独立观察。
   - 结果与影响：实现没有产品取舍，只需满足逐字行为判据。

<!-- large-task-planning:acceptance-criteria -->
## 验收标准

- 根目录 `greeting.txt` 恰好包含 `hello from orchestrated worker` 和结尾换行。
- `./check.sh` 输出 `greeting check passed` 且退出码为 0。
- 除 `greeting.txt`、执行卡、仪表盘和证据外没有任务改动。
