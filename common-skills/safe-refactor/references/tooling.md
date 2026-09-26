# 脚本使用说明

脚本位于本 Skill 根目录的 `scripts/`。Python 3.9+、Git、标准库即可；业务项目仍使用自己的语言和测试运行时。脚本不调用模型、不访问网络、不自动安装依赖、不改生产代码，也不自动提交、推送或部署。

以下路径由实际安装位置和任务填写。使用绝对路径，任务目录放在源码仓库外。

```bash
SKILL_DIR=/absolute/path/to/loaded/safe-refactor   # 宿主加载本 Skill 时解析出的根目录
REPO=/absolute/path/to/repository
TASK=/absolute/path/to/refactor-tasks/orders-batch
GUARD="$SKILL_DIR/scripts/refactor_guard.py"
```

## 1. 初始化

```bash
python3 "$GUARD" init --repo "$REPO" --task-dir "$TASK" \
  --id orders-batch --goal '只优化订单列表读取，保持业务行为不变'
```

要求干净的已提交仓库。目录已存在会拒绝覆盖；恢复任务直接读取它。生成的 policy/verification 是刻意不通过验证的草稿，由 Agent 根据真实仓库填充，不应原样批准。

用户已有未提交工作时，先保存来源和归属，用独立工作树处理；不自动 stash/reset/clean 或提交全部用户修改。

## 2. 填 policy

[策略模板](../assets/policy.template.json) 是严格 JSON，不接受多余字段、重复 key 或空范围。契约对象从 [契约模板](../assets/contract.template.json) 添加。

| 字段 | 解释 |
|---|---|
| task_id / goal / non_goals | 本次身份、收益目标和明确不做的事 |
| origin_revision / base_revision | 初始旧版、补好基线后的旧版；完整 commit SHA |
| scope.strategy | local 或 shared，不代表自动授权 |
| scope.allowed_paths | 候选相对 base 允许改变的路径 |
| scope.protected_paths | 始终禁止本候选改动，优先于 allowed |
| scope.baseline_paths | origin→base 仅可进行基线准备的路径 |
| scope.frozen_paths | 封存的断言、夹具、规范／适配器文件；至少一个实际匹配 |
| contracts | 必须保持的外部行为、oracle 依据、是否需要基线／红控 |
| benefit | 本次目标是否需要独立执行证据，以及可观察标准 |
| review.independent_required | 是否要求实际独立 reviewer；默认 true |
| budget | 最大局部修复／重规划次数；协调者维护消耗，脚本不调度循环 |

路径相对仓库根，用 `/`：精确文件、`*`（不跨目录）、`?`、整段 `**`（零或多级目录）。不支持 `[]`、绝对路径、`..`、反斜杠或 Git pathspec 魔法。删除／重命名两端均检查；二进制变化也算。不要以 `**` 代替真实边界。

`frozen_paths` 不是全仓测试冻结：只保护本次选定的断言基线。候选在该匹配范围增加文件也会触发基线变更；新测试可放到单独允许目录，或返回基线步骤重新审批。修改测试脚手架需确认没有改变 oracle。

## 3. 封存（不等于批准）

```bash
python3 "$GUARD" seal --repo "$REPO" --policy "$TASK/policy.json" \
  --out "$TASK/seal.json"
python3 "$GUARD" fingerprint --file "$TASK/policy.json"
python3 "$GUARD" fingerprint --file "$TASK/seal.json"
```

封存检查 origin→base 是否只改了批准的基线准备路径，读取固定 Git 对象保存文件 mode、blob ID、SHA256；不跟随文件 symlink。每个冻结模式必须匹配普通文件，缺失不会静默成功。

把确认过的摘要送到受保护审批记录。JSON 排版改变也会改变摘要。审批后修改范围／契约／基线，必须新建批准版本；不要在 CI 里现算待审文件摘要就当“已批准”。

## 4. 运行中检查路径

```bash
python3 "$GUARD" scope --repo "$REPO" --policy "$TASK/policy.json" --worktree
```

`--worktree` 包含 base→HEAD、工作区、暂存区和非忽略的未跟踪文件的保守并集。不含 ignored 构建产物；它们由构建／制品验证管理。

结果为 `PATH_SCOPE_OK` 或 `BLOCK`，只说明路径。新增共享状态传播即使文件允许，也必须回到影响面分析重新决策。

## 5. 收集执行证据

在固定旧版工作树上：

```bash
python3 "$GUARD" run --repo "$OLD_TREE" \
  --out "$TASK/evidence/baseline.json" --kind baseline \
  --contract C1 --contract C2 --environment '填写隔离环境/依赖/夹具说明' \
  --junit "$TASK/evidence/baseline.junit.xml" --timeout 300 \
  -- python3 "$SKILL_DIR/scripts/unittest_junit.py" \
  --output "$TASK/evidence/baseline.junit.xml" --start tests --top .
```

这是 Python unittest 例子；其他语言将 `--` 后替换成项目现有、已授权且能输出新 JUnit XML 的测试命令。`--start tests --top .` 的 Python 测试目录应可导入（通常含 `__init__.py`）。不使用 Python 的项目不需要这个 reporter。

在候选工作树同样执行，换 `--kind regression`、新文件名 `candidate.json` 和 `candidate.junit.xml`。每次重试使用新名字，不覆盖旧失败记录。

可选类型：

| kind | 用途 | 自动 gate 最低条件 |
|---|---|---|
| baseline | 固定旧版业务测试 | baseline SHA，非空真实 testcase，执行成功 |
| regression | 候选行为回归 | 当前 candidate SHA；指定必需测试确实通过 |
| red-control | 隔离旧版的故意错误 | 指定 `--control-of <base SHA>`；独立后代提交；断言未改；非零退出、failure>0、error=0 |
| benefit | 收益验证（性能或结构） | 当前 candidate SHA，执行成功；reviewer 检查原始结果 |
| check | 附加检查或旧版性能记录 | 收集事实，不单独替代必需回归／收益证据 |

`run` 不要求每个命令都有 JUnit，但没有 JUnit 的 baseline/regression 不能自动支撑最终契约通过。只有 XML 的 tests 属性而没有 testcase 明细，也不计作已执行。

stdout/stderr 合并保存 `.log`，JUnit 复制／保存为 `.junit.xml`，摘要与源码前后状态记录在 `.json`。已有输出／报告会拒绝，防止旧报告混入。测试日志可能包含敏感数据；在隔离环境脱敏，上传前由平台控制访问，不将凭据放进命令参数。

命令以 argv 执行，不隐式 shell 拼接。执行前必须确认环境及命令已获授权。脚本不是沙箱，不验证数据库地址是否属于生产，不能阻止被执行程序访问宿主权限内的资源。POSIX 超时终止该命令的进程组；Windows 只保证终止直接进程，进程树隔离需宿主 Job Object／沙箱。

Python reporter 使用独立临时字节码查找目录，避免前一提交的 `.pyc` 误充当前源码；不删除用户缓存。其他运行器的缓存／构建产物需项目自己的隔离或重建策略。

## 6. 填验收结果

独立 reviewer 填 [验收 JSON](../assets/verification.template.json)。每个契约从 [契约结论模板](../assets/contract-verdict.template.json) 添加一行：

- `tests`：候选 JUnit 中实际的 `classname.name`；无 classname 时为 name。全部指定测试必须实际通过，不能全部 skip。
- `assertion`：具体断言及充分性理由，不是“测试通过”。
- `evidence`：相对 verification.json 所在目录的 runner JSON 路径。
- `red_control_confirmed`：确认目标断言因故意错误失败，不是看红灯就 true。

完整地覆盖 policy 中所有契约，不能新增未批准契约冒充已评估，也不能漏掉一个。impact 的 unresolved 只列影响当前必需证明的未知；剩余可接受风险写 residual_risks，并在 Markdown 保留接受依据。

## 7. 最终机械 gate

```bash
python3 "$GUARD" gate --repo "$CANDIDATE_TREE" \
  --policy "$TASK/policy.json" --seal "$TASK/seal.json" \
  --verification "$TASK/verification.json" \
  --approved-policy-sha256 "$TRUSTED_POLICY_SHA256" \
  --approved-seal-sha256 "$TRUSTED_SEAL_SHA256"
```

其中两个 `TRUSTED_*` 必须由变更执行者之外的可信控制面传入，不能从当前未审文件临时求值。

| 退出码 | gate 结果 | 含义 |
|---|---|---|
| 0 | PASS_MECHANICAL | 结构、版本、文件和引用证据检查通过；不是业务正确性证明 |
| 1 | BLOCK | 已发现违反受保护边界或 reviewer 明确阻止 |
| 2 | INSUFFICIENT | 缺材料、错误格式、脏工作区、旧证据、必要检查未完成 |

`run` 的 0 是成功收集一次正常执行或符合机械条件的红控，1 是执行／红控不满足，2 是输入／环境问题。它与 gate 的含义不同。

最终门禁需要完整 Git 对象、干净提交和可读取证据；不支持 sparse/skip-worktree/assume-unchanged 或含 submodule 的自动最终证明。遇到这些明确报告不足，交项目适配器处理；不要禁用检查后宣称自动通过。

## 检查不了什么

无法自动还原全部调用图、发现所有共享状态影响、确定 oracle 正确、认证 reviewer 身份、确认运行日志来自真实可信 CI、证明硬件／外部依赖一致、提供生产权限隔离。本 Skill 提供这些检查的任务与记录格式，不把格式校验包装成完整软件验证系统。
