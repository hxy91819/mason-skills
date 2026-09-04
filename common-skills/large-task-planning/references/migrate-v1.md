# 从 v1 迁移

v1 的识别特征是 `epics/EPIC-*.md`、`stories/`、`agent/STORY-*.json` 与生成式
`项目进展.md`。v2 不继续双写这些格式。

先把旧计划转换到一个空的新目录：

```bash
python3 <skill-dir>/scripts/epic_story.py migrate-v1 \
  --epic <old>/epics/EPIC-ID.md \
  --stories-dir <old>/stories \
  --output-dir <new>
```

转换器会：

- 从 v1 Epic 与黄金验收生成 `<new>/agent/plan.json`；
- 把执行卡状态、验收、技术输入和 handoff 合并进 `<new>/agent/stories/*.json`；
- 从 JSON 生成面向人的 `<new>/SPEC.md` 与 `<new>/STATUS.md`；
- 让最后一张 Story 成为 `final_story`，并显式依赖所有前置 Story；
- 校验完整 v2 结果后才写入；
- 保留全部 v1 源文件，不接受原地迁移，也不覆盖非空目录。

迁移要求 v1 存在恰好一份 `kind=golden-acceptance` 的 JSON。缺少稳定 oracle 时先补齐，因为机械
转换不能发明正确答案。

转换后运行 `check`，再人工复核五件事：问题与最终体验是否准确；黄金 oracle 是否仍有效；边界与
范围外事项是否完整；每个 Context 的测试 seam 和代码锚点是否仍存在；SPEC/STATUS 是否能让未参与
实现的人迅速理解与采取行动。确认后，用普通 Git 变更替换旧计划目录；不要长期同时维护 v1 与 v2。
