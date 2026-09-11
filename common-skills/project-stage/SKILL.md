---
name: project-stage
description: Declare a repository's lifecycle stage (experimental or production) in its agent instruction file so agents stop adding compatibility layers that no consumer needs. Use only when the user explicitly invokes $project-stage, typically once when starting a project, once more when it graduates to production, or when adding the declaration to an existing project.
disable-model-invocation: true
triggers:
  - user
---

# Project Stage

Agents default to treating every repository as a live system with unknown callers, old
deployed versions, and persisted data to migrate. That default is right for production and
wrong for experiments, where it silently piles up fallbacks, shims, optional parameters,
and "v2" paths that nobody consumes. The fix is not a global "be simple" instruction; it is
a short, factual declaration in the repository itself of **who consumes this code**.

## Procedure

This skill runs only on explicit `$project-stage` invocation. It edits the repository's
instruction file, so a passing mention of "this is experimental" must not trigger it.

1. Locate the repository's agent instruction file: `AGENTS.md`, `CLAUDE.md`, or whatever
   the project already uses. Create `AGENTS.md` at the repo root if none exists.
2. If the file already has a `## 项目阶段` section, update it instead of adding a second.
3. Decide the stage. The user usually knows; if the prompt already says "experimental",
   "prototype", "线上", "已发布" or similar, do not ask. Ask a single question only when the
   stage is genuinely unstated and cannot be inferred from the repo (no deploy config, no
   migrations, no published package usually means experimental).
4. Insert the matching template below near the top of the file. Fill in the bracketed
   facts for production; leave the experimental template as is unless a fact is wrong.
5. Tell the user which file was edited and which stage was declared. Do not touch any
   other file.

The declaration lists **facts**, not attitudes. "No deployed old version exists" removes the
reason for a compatibility branch; "keep it simple" only discounts it.

## Template: 实验期

```markdown
## 项目阶段：实验期

- 唯一消费者是本仓库内的代码。没有外部调用方，没有已部署的旧版本，没有需要迁移的持久化数据。
- 破坏性修改是免费的：直接改签名、改数据格式、删代码、重建 schema。不写 deprecate 路径、不留 fallback、不加 v2 并存。
- 不为"未来可能"预留：不加没人传的可选参数、没人读的配置项、只有一个实现的抽象层。需要时再加。
- 审查时对每个 fallback 分支、兼容 shim、可选参数问同一个问题：它服务于哪个真实存在的消费者？答不出就删。
- 项目上线时把本节改为「线上期」并列出真实消费者。
```

## Template: 线上期

```markdown
## 项目阶段：线上期

- 消费者：[外部调用方 / 已发布包的用户 / 其他服务]，当前已部署版本 [x.y]。
- 持久化数据：[数据库 / 文件格式 / 缓存]，改动 schema 需要迁移。
- 发布节奏：[每周 / 按需]，破坏性修改需要 [deprecate 周期 / 版本号升级 / 公告]。
- 兼容代码仍需指向真实消费者：找不到消费者的 fallback 和 shim 应删除，而不是保留"以防万一"。
```

## Graduation

When an experimental project goes live, replace the experimental section with the
production template and fill in the real consumers. Compatibility cost is paid once at that
moment instead of a little on every iteration. Existing production repositories without any
declaration keep the conservative default; this skill never loosens behavior implicitly.
