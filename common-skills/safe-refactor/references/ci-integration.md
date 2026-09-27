# 接入已有 CI／Agent Harness

这是接入合同和可运行命令，不是已经部署好的 CI 服务。不同公司审批、runner 和制品系统不同，本 Skill 不凭空生成这些账户或权限。

## 三层分开

**Skill 层**：定义责任、影响分析、oracle、证据审查和失败回路。
**机械层**：本 Skill 的 Python 脚本检查范围、固定基线、SHA、日志／JUnit、必需测试名与 verdict。
**可信控制层**：用户／团队的受保护配置、审批者、受限 runner、制品库和部署平台。

第三层缺失时，前两层可以辅助日常开发，但不能宣称执行者无法篡改自己的成绩。

## 平台一次性要做的事

1. 将这套 guard 从受保护版本加载，或在 CI 中检查它的包摘要；不能执行 PR 中随意修改后的 gate。
2. 存储每任务批准的 `policy.json` 和 `seal.json` 的 SHA256，并绑定任务、仓库和相应版本；同一编码主体不能改这些批准值。
3. 从候选精确提交启动隔离 runner；测试命令无部署凭据、无生产写入权限，日志／报告放只追加制品库。
4. reviewer 从原始源码和原始 runner 证据评估，记录真实执行主体。将 review 与制品／版本绑定，不能只相信 JSON 自报的 `independent=true`。
5. 把 gate 和 reviewer 结论作为发布前必要输入；新提交、基线变化及合并结果变化重新触发。
6. 发布平台另管灰度、业务指标、数据兼容、恢复、审批和审计。没有这些能力就标“待平台接入”。

## 任意 CI 的命令步骤

```bash
# 这些变量由受保护 CI 设置，不由待审 PR 自行填写。
python3 "$TRUSTED_SAFE_REFACTOR/scripts/refactor_guard.py" gate \
  --repo "$EXACT_CANDIDATE_CHECKOUT" \
  --policy "$TRUSTED_TASK_ARTIFACTS/policy.json" \
  --seal "$TRUSTED_TASK_ARTIFACTS/seal.json" \
  --verification "$TRUSTED_TASK_ARTIFACTS/verification.json" \
  --approved-policy-sha256 "$APPROVED_POLICY_SHA256" \
  --approved-seal-sha256 "$APPROVED_SEAL_SHA256"
```

任意非零退出阻止自动放行。完整 JSON 输出作为制品保存，不能 `|| true`、只检查命令有没有跑或只找日志中的 PASS 字符串。

## Agent Harness 的最小接口

无需另外写一套 LLM SDK。现有 Harness 应提供：只读研究会话、受限写工作树、项目测试命令、独立验收会话、任务目录和明确审批入口。

协调者发起步骤时传递：`task_directory`、`origin_revision`、`base_revision`、`candidate_revision`（适用时）、`mode`、当前授权。工具按真实 schema 调用，不在 Skill 内硬编码某厂商不存在的 `spawnAgent()`。

没有 spawn 能力时保留需要独立审查的阻塞，或由真人在新会话以 verify 模式调用 `$safe-refactor`。不要给同一上下文换一个角色名就标为独立。

## 避免这四种假门禁

- **自批摘要**：CI 对 PR 中的 policy 现算摘要，再当 approved 值输入，等于没有审批边界。
- **自报证据**：同一写权限可以一起改日志、XML、JSON，哈希只能检测意外漂移，不能识别协同伪造。
- **旧分支通过**：实现分支测试绿，但实际合并树又改变依赖或公共代码，不能沿用旧 SHA。
- **小流量等于隔离**：共享表、缓存、队列或锁仍可能波及其他用户，放量百分比不能代替资源／状态边界。

## 安全说明

`run` 会执行指定项目命令，这些命令本身是不受本脚本沙箱限制的程序。先使用公司的容器／虚机／权限控制。不要在拥有生产密钥的高权限步骤里运行不受信任分支的测试。

审批摘要不需保密，但须不可由编码执行者伪造或替换。不同 session ID 是审计信息，不是数字签名。远端制品的签名／证明和日志保留由已有平台完成，本 Skill 不假装已实现。
