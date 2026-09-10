# BB 阶段复盘

仅当用户明确要求基于 BB 对一个阶段或一组会话复盘时读取本页。这是 `distill` Review mode 的 BB adapter，不是第二个 Skill，也不改变 Phase 3 的用户确认门禁。

## 接口与边界

推荐从同一阶段的主会话显式调用：

```text
$distill review --bb --scope repo-harness --since "2026-09-09T15:00:00+08:00"
```

当前 BB profile 只支持 `repo-harness`：审计未来 Agent 在当前仓库会用到的 Skills、`AGENTS.md`、文档、脚本和本地验证入口。外部产品问题、个人偏好、凭据轮换和一次性临时文件要分类为仓外、任务内或废弃，不扩张为仓内候选。

先用脚本发现，再由复盘负责人选择精确会话；`bb thread list` 的结果是候选列表，不是完整证据边界。不要把日期筛选出的所有会话自动当作 material，也不要让脚本根据标题猜测任务语义。
下列 `scripts/` 路径均相对本 Skill 目录；从项目工作目录调用时，先由已加载的
`SKILL.md` 定位该目录，再使用对应的绝对路径。

```bash
python3 scripts/bb-stage-retro.py discover \
  --since 2026-09-09T15:00:00+08:00

python3 scripts/bb-stage-retro.py plan \
  --scope repo-harness \
  --since 2026-09-09T15:00:00+08:00 \
  --threads thr_a,thr_b,thr_c \
  --continuation thr_interrupted=thr_successor
```

`plan` 会检查目标会话为空闲状态，并通过 `$bb-model-routing` 的 `bb-dispatch --dry-run` 校验聚合路由；它只读。确认计划后，才明确执行：

```bash
python3 scripts/bb-stage-retro.py apply \
  --scope repo-harness \
  --since 2026-09-09T15:00:00+08:00 \
  --threads thr_a,thr_b,thr_c \
  --continuation thr_interrupted=thr_successor
```

`apply` 向每个最终会话发送显式的 `$distill` Session-mode 请求，等待它们空闲后才用 `$bb-model-routing` 派发一个 Review-mode 聚合会话。它不启动部署、构建、数据库或外部系统操作；如果任一会话未能完成、消息排队或路由校验失败，它停止且不派发聚合者。
聚合会话固定使用 BB 的 `accept-edits` 权限；在用户确认前，它的提示词和 `distill` Phase 3 都要求只读。

## 覆盖和会话调度

冻结开始和结束时间，再选出 material 会话。一个错误会话由后续会话完成同一工作时，必须显式传入 `--continuation 原会话=续接会话`；可以形成链，脚本会把它折叠到最后一个续接会话，只蒸馏该最终会话。原会话在聚合表中保留为 `covered_by`，但不算独立复发。

脚本只向预检为 `idle` 且没有待交互的最终会话发送请求，使用 BB 的 `auto` 消息模式。它绝不向运行中的会话 `steer`，避免改变正在执行的任务。聚合者只在全部会话的蒸馏完成后启动；启动后不要再向它发送会改变审计边界的 follow-up。需要扩大范围时，终止本轮并以新的固定边界重新启动。

每个 Session-mode 请求必须显式以 `$distill` 开头，不能以一段“等价格式”的普通文本替代 Skill 调用。聚合者只读取最终会话的 `bb thread output --json`，不复制原始会话日志、截图、凭据或大附件。

## 聚合输出

聚合者在第一次 Phase 3 决策简报处停止，不修改任何文件。它先给出一张固定去重表，然后按 `distill` 的正常决策简报格式呈现真正需要用户选择的候选。

| 模式键 | 证据与覆盖会话 | 权威与范围 | 权威落点 | 处置 |
|---|---|---|---|---|
| 语义归一化后的结论 | 会话 ID；错误会话的 `covered_by` | 用户确认、批准来源或待确认；并标明范围 | 一个唯一的文件、Skill、脚本、测试或仓外归属 | 采纳、已覆盖、仓外转交、废弃、待验证 |

同一模式的多次命令、重试和续接不得增加 recurrence。表中只有处置为“采纳”的项目可以进入 Phase 3；用户确认后才修改对应的权威来源，并按 `distill` Phase 4 验证。

## 可观测性和保留

BB 线程记录是本 adapter 的运行事实源：可用 `bb thread show <id> --json`、`bb thread output <id> --json` 和 `bb thread log <id> --all` 回看。脚本不建立第二份会话账本，不保存 prompt、会话正文、截图、日志或密钥；它只把本轮计划和操作结果打印到 stdout。`distill` 既有的用户本地 review checkpoint 仍只保存检索游标。

剩余缺口是 BB 的线程列表可能分页，故 `discover` 只能辅助选择，无法独立证明“已覆盖所有会话”。复盘负责人必须在证据来源句中说明会话选择方式和任何缺口。
