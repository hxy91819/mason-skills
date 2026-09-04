# 能力档映射

先读当前宿主的 subagent / model 目录，在**此刻可用**的选项里做相对排序，再映射档位。目录会变；
下面的宿主名称只是对照，不是协议。

## 在可用选项里分档

1. **economy**：能使用实现或探查所需工具、上下文够用的最低成本型号。
2. **standard**：宿主默认编码模型，或中档 reasoning。
3. **strong**：目录里最强的实现或审查型号。

没有三档可选时，把可用选项压到最接近的两档或一档，并在 history `--model` 记下实际值。省略 model
等于 inherit 父会话；编排会话通常已是高档，只有用户要求或目录只剩 inherit 时才用。

## 角色

- **Worker**：实现型 subagent（general-purpose / coding worker）。只读 explore 不写代码。
- **Reviewer**：能跑验证命令、并遵守本 Skill 双轴报告契约的独立 subagent。输出契约不同的专用
  审查器不能代替 Reviewer。
- **只读探查**：可用宿主的快速 explore / investigate 类型，档位 economy。

## 对照（以派发时目录为准）

- Cursor Task：`composer-*-fast` / `cursor-grok-*-fast` → economy；`claude-sonnet-*` /
  `gpt-*-terra-*` → standard；`claude-opus-*` / `gpt-*-sol-*` → strong。
- Codex `spawn_agent`：按当前 model 列表的价格与能力分档；保持 fresh context（如
  `fork_turns: none`）。
- Claude Code Task：同样按目录相对分档；未暴露模型选择时 `--model default`。

## 升级证据

升档只依据可观察失败：越界、漏验收、测试假绿、Reviewer 指出的能力性缺陷。配额、路由或 session
失败换同等档的 replacement，不升档。
