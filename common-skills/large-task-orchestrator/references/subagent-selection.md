# 能力档映射

先读当前宿主的 subagent / model 目录，在**此刻可用**的选项里做相对排序，再映射档位。目录会变；
下面的宿主名称只是对照，不是协议。

## 在可用选项里分档

1. **economy**：能使用实现或探查所需工具、上下文够用的最低成本型号。
2. **standard**：宿主默认编码模型，或中档 reasoning。
3. **strong**：目录里最强的实现型号。

没有三档可选时，把可用选项压到最接近的两档或一档，并在 history `--model` 记下实际值。省略 model
等于 inherit 父会话；编排会话通常已是高档，只有用户要求或目录只剩 inherit 时才用。

## 角色

- **Worker**：实现型 subagent（general-purpose / coding worker）。只读 explore 不写代码。按 Story
  难度取最低够用档。
- **Validator**：固定最低校验档，不套 Worker 的能力档。任务必须显式要求 `$story-direction-review`，
  只确认 Story 是否真正完成。不要派 code review、bugbot、security-review 或其他专用审查器。
- **只读探查**：可用宿主的快速 explore / investigate 类型，档位 economy。

## 对照（以派发时目录为准）

- Cursor Task：从目录中剔除所有 `claude-*` 型号，也不要通过 inherit 落到 Claude。剩余选项：
  `composer-*-fast` / `cursor-grok-*-fast` → economy；`gpt-*-terra-*` → standard；`gpt-*-sol-*` →
  strong。Validator 只从 economy 里选。
- Codex `spawn_agent`：模型用当前目录里的 terra（如 `gpt-5.6-terra`），保持 fresh context（如
  `fork_turns: none`）。Worker 按能力档设 effort：economy → `high`，standard → `xhigh`，strong →
  `max`。Validator 固定 terra `medium`，不升档。
- Claude Code Task：同样按目录相对分档；未暴露模型选择时 `--model default`。Validator 仍选最低
  成本可用型号。

## 升级证据

只升级 Worker，且只依据可观察实现失败：越界、漏验收、测试假绿。配额、路由或 session 失败换同等档
的 replacement。Validator 不升档：Codex 固定 terra `medium`，其他宿主固定 economy。
