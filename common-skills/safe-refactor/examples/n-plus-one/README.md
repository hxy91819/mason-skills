# N+1 演示

这是构造的本地教学项目，不是真实服务。数据库是 Python 标准库的内存 SQLite，ID 在本例全局唯一。

## 运行

在 Skill 根目录执行：

```bash
python3 examples/n-plus-one/run_demo.py --output /tmp/refactor-n-plus-one-example
```

输出目录必须不存在。脚本只在这个新建目录中创建 Git 仓库、独立红控工作树和任务证据，不访问网络、不更改已有仓库、不执行生产动作。

## 展示了什么

原版接口 A 调用共享 `load_one` 逐条查询；B 继续依赖同一旧函数。候选给 A 增加独立 batch 策略，复用未修改的 `visible` 和 `present`，不修改其他调用者、数据表或存储接口。

8 个行为测试保护租户隔离、顺序／重复、缺失、空输入、其他入口、返回对象所有权、跨批边界与数据库错误。

红控从固定旧版创建独立工作树，刻意移除租户检查：必须出现权限相关断言 failure，而不是环境 error。该提交不进入候选。

查询量用 SQLite 实际 trace 计数，批次上限为 100。205 条记录的预期查询次数为旧版 205、新版 3；具体运行结果在 `task/evidence/*queries.log` 和 `benefit.log`。这只证明查询数量变化，不证明线上延迟或连接池风险。

门禁依次演示：

1. 当前证据与候选匹配 → `PASS_MECHANICAL`。
2. 新增提交后继续拿旧候选证据 → `INSUFFICIENT`。
3. 修改受保护的共享模块 → `BLOCK`。

最后一个例子追加一个公共缓存版本常量，仅用于验证路径约束；没有模拟真实缓存消费者。脚本不会自动分析常量是否有语义影响，真实任务仍需影响面分析和 reviewer。

## 诚实的边界

演示的 verdict 是预先写定的 fixture 预期，不是实际启动独立 Agent 后得到的结果。因此演示 policy 特意设置 `independent_required=false`，并如实记录相同执行者；**生产模板默认 true，不要把演示的这个值照搬。**

脚本结尾的仓库故意停在负向案例提交，便于查看失败；合法候选 SHA 在 `task/verification.json` 和 `task/gate-valid.json`。不要将结尾 HEAD 当成已经通过验收的版本。

完整跨模型 workflow 测试仍需运行 `tests/agent-evals.jsonl` 中的情景（可交给 `$skill-test`）。本演示只验证文件、脚本、执行证据链和固定的小型业务契约。
