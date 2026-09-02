# Pi effort investigation

This is the adapter-specific evidence for routing Pi work. Recheck the commands when the Pi or `pi-acp` version changes; the ACP adapter may expose a smaller set of levels than native Pi.

## Observed on 2026-09-02

- `pi --version` reported `0.84.4`.
- `pi --help` exposes `--thinking off, minimal, low, medium, high, xhigh, max`; `--effort` is not a Pi CLI flag.
- The upstream CLI argument definition lists the same seven thinking levels and the `:<thinking>` model syntax: [Pi CLI args](https://raw.githubusercontent.com/earendil-works/pi/main/packages/coding-agent/src/cli/args.ts).
- Native RPC started with `pi --mode rpc --no-themes` reported provider `zai` with model id `glm-5.3-flash` (the ACPX display is `zai/glm-5.3-flash`), `thinkingLevel=max`, a `thinkingLevelMap` containing `max`, and `compat.supportsReasoningEffort=true`.
- That fresh native session reported `thinkingLevel=max` before any level-setting command, so this installation can omit `--thinking` and use its default.
- Native RPC accepted `set_thinking_level` with both `xhigh` and `max`.
- The current ACPX Pi adapter resolved as `npx pi-acp@^0.0.31` (installed `pi-acp@0.0.33`). Its `session/new` response advertised the ACP config option `thought_level` with `off`, `minimal`, `low`, `medium`, `high`, and `xhigh` only.
- `acpx pi set thought_level xhigh -s <session>` returned `config set: thought_level=xhigh`; `acpx pi set reasoning_effort max -s <session>` and `thought_level max` were rejected as unsupported config/value combinations.

`compat.supportsReasoningEffort` is native model metadata; it does not define the ACPX
configuration key. The adapter's independently advertised key is `thought_level`.

## Dispatch rule

Treat the large-task profile value as an abstract effort. If the profile intentionally
accepts the adapter default, do not issue a setting command; record
`effort=default` and the observed default. For a Pi worker or validator that needs an
explicit override through ACPX, set the advertised ACP option with:

```bash
acpx --cwd <repo> pi set thought_level <resolved-effort> -s <role-session>
```

Require the `config set: thought_level=<resolved-effort>` confirmation before prompting. Use `xhigh` for the highest Pi level currently reachable through `pi-acp`; do not silently translate `max` to `xhigh`. If a profile requests a value the adapter does not advertise, record `effort=default` plus the rejection and continue with the adapter default. Native `pi --thinking max` is evidence that Pi supports `max`, but it does not make `max` available through the current ACP adapter. The native default observed here is local configuration evidence, not a promise about every Pi or ACPX installation.
