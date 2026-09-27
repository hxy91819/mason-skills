# Harness 大全

这里的 harness 指让人和 Agent 改代码时能快速拿到确定反馈的工程设施：提交前守卫、测试分层、容器化依赖、迁移工具、覆盖率门禁、冒烟脚本和 Agent 工作面。本文按主题收录在真实项目里验证过的做法，供新项目挑选吸收。

## 使用方式

- 新项目先看[接入清单](#10-新项目接入清单)，按优先级挑选；具体做法到对应主题章节查。
- 每条做法标注来源项目代号，来源在下表登记。只记录可迁移的模式，不写来源项目的内网地址、账号或内部系统名。
- 新增来源时：在来源表登记代号和技术栈，把做法并入已有主题；已有条目相同的做法只补来源代号，不重复写。观察到的坑写进[反模式](#9-反模式与漂移)。

| 代号 | 技术栈 | 特点 |
| --- | --- | --- |
| A | Python 3.12、FastAPI、SQLAlchemy async、Alembic、PostgreSQL、Redis Cluster，DDD 四层结构 | 约 3000 个单元测试，testcontainers 集成测试，Agent 协作开发 |

## 1. 提交前守卫（pre-commit）

### 1.1 分阶段编排 `[A]`

按「能自动修的先修，再报错」排序，越靠后的失败越需要人处理：

1. `ruff check --fix` → `ruff format`：自动修复与格式化。
2. `pyright`：类型检查，hook 上 `files: ^src/` 只查业务代码，并在 `pyrightconfig.json` 排除 ORM/infrastructure 目录和迁移目录，控制耗时和噪音。
3. `pre-commit-hooks`：`trailing-whitespace`、`end-of-file-fixer`、`check-yaml`、`check-added-large-files --maxkb=500`、`check-merge-conflict`、`debug-statements`。
4. `detect-secrets --baseline .secrets.baseline`：存量误报进 baseline；测试用的固定密码在行尾加 `# pragma: allowlist secret`；排除锁文件和迁移目录（Alembic revision ID 会被识别成密钥）。
5. 项目自定义检查（见 1.3）。

配置文件头部写明安装、启用、全量运行命令和执行顺序，新人和 Agent 读一遍就能用。

### 1.2 Linter 规则选择 `[A]`

- 除常规集合（`E W F I B C4 SIM RUF`）外，值得默认开启的：`DTZ`（禁止无时区 datetime）、`T20`（禁止 `print`）、`S101`（禁止运行时 `assert`）、`D`（docstring，按团队语言放宽 D415/D403 等）、`PLR0911/0912/0915`（复杂度上限）。
- 存量问题暂时 `ignore` 时，注释写明**当前存量数量**和 TODO，例如 `PLR0913 存量 62 处`。这个数量是后续收紧的基线。
- `per-file-ignores` 按目录放宽：`tests/` 允许 assert、魔法数字、长函数；`scripts/` 允许 print；`migrations/` 不要求 docstring。
- `isort force-single-line = true`：每行一个 import，合并冲突更少。

### 1.3 把反复出现的评审意见写成 AST 检查脚本 `[A]`

评审中重复指出的问题，写成 50～100 行的 Python AST 脚本，挂到 pre-commit 的 `repo: local`。来源 A 的例子：

| 检查 | 规则 | 防的问题 |
| --- | --- | --- |
| 日志格式 | 导入项目 logger（loguru）的文件里，`logger.info('... %s', x)` 报错 | loguru 不做 `%s` 插值，日志丢参数 |
| 时区 | ORM 中出现 `DateTime(timezone=False)` 报错，行尾 `# utc-ignore` 豁免 | 数据库存无时区时间 |
| 返回值个数 | `return` 返回超过 5 个元素的元组报错 | 散装元组，应封装为 dataclass |
| 嵌套装饰器 | 函数体内定义带装饰器的嵌套函数报错 | 不可测试、不可复用 |
| gather 异常 | `await asyncio.gather(..., return_exceptions=True)` 的结果没有赋值报错 | 异常被静默吞掉 |

脚本约定：

- 参数是 pre-commit 传入的文件列表，只检查这些文件。
- 输出 `path:line: message`，有违规返回非零。
- 支持行内豁免标记（如 `# utc-ignore`），豁免必须写在违规行上，便于检索。
- 解析失败（语法错误）直接跳过，交给 ruff/pyright 报。
- 规则只针对业务代码时，在 hook 上用 `exclude: '^(tests/|scripts/)'`。

```python
#!/usr/bin/env python3
"""检查 <规则说明>。用法: check_xxx.py <file1.py> [file2.py ...]"""
import ast
import sys


def check_file(path: str) -> list[str]:
    try:
        with open(path, encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=path)
    except (SyntaxError, UnicodeDecodeError):
        return []
    errors = []
    for node in ast.walk(tree):
        if _violates(node):
            errors.append(f'{path}:{node.lineno}: <违规说明与修复建议>')
    return errors


def main() -> int:
    errors = [e for f in sys.argv[1:] for e in check_file(f)]
    for e in errors:
        print(e, file=sys.stderr)
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
```

### 1.4 让 Agent 负责修 pre-commit `[A]`

定义一个 `pre-commit-checker` 子 Agent：输入变更 ID 和文件列表，循环执行 `pre-commit run --files ...` 直到通过；需要重构的问题（参数过多、分支过多、大元组）先读变更提案理解意图再改；最后按固定模板输出「检查的文件 / 结果 / 已自动修复 / 需注意」。

## 2. 测试分层与设计

### 2.1 四层金字塔 `[A]`

| 层 | 对象 | 依赖 | Mock 范围 |
| --- | --- | --- | --- |
| 单元测试 | 领域对象、纯计算函数 | 无 | 不 Mock |
| 模块端到端 | 单个模块的 service 和 repository | testcontainers（PG/Redis） | 只 Mock 其他模块的公开 API |
| 集成测试 | 多模块协作的核心流程 | 真实 DB | 只 Mock 外部服务（沙箱、对象存储） |
| E2E | 完整用户场景 | 真实环境 | 不 Mock，按日或按周执行 |

### 2.2 分离计算与 IO `[A]`

这是单元测试不需要 Mock 的前提：

- 领域逻辑写成纯函数或不可变领域对象（输入 → 输出，无副作用），由单元测试覆盖。
- Service 编排层只做「读 → 调领域逻辑 → 写」，保持直线；没有分支的胶水代码不写单测，由模块端到端测试覆盖。
- 编排层出现条件分支时，把分支下沉到领域对象，返回结果对象（如 `DeductResult.insufficient()` / `DeductResult.success(account, need_warning)`），编排层只根据结果执行 IO。
- Repository 只由 testcontainers 测试覆盖。

### 2.3 Mock 边界 `[A]`

- 只 Mock 其他模块对外暴露的 API，它们设计上稳定；模块内部组件不单独 Mock。
- 先有 API 契约，再按契约写 Mock；API 升级时 Mock 跟着版本化。
- 共享假对象集中放 `tests/fixtures/fakes.py`；复杂外部依赖的 Mock 记录调用历史（创建了什么、执行了哪些命令），供断言使用。

### 2.4 测试方案文档格式 `[A]`

每个模块两张表，再加每个迭代的集成通过标准：

- 单元测试表：`测试用例 | 输入 | 预期输出 | 说明`，边界值单独成行（如 `exp = now` 视为过期）。
- 模块端到端表：`测试场景 | 步骤 | 预期结果 | Mock`，Mock 列写清楚哪些用 testcontainers、哪些 Mock 其他模块 API。
- 迭代集成：列出涉及模块和 checklist 形式的通过标准（如「此阶段不应出现跨模块依赖」）。

### 2.5 Marker 与默认运行范围 `[A]`

- Marker：`unit`、`integration`（需要 DB/Redis）、`cluster`（Redis Cluster）、`external`（需要真实凭证）、`performance`、`slow`（>5s）、`metrics`（需要本地服务）、`known_failure`。
- `testpaths = tests/unit`：裸跑 `pytest` 只跑单元测试，秒级反馈；集成测试显式指定目录或 marker。

### 2.6 存量失败隔离 `[A]`

默认套件必须保持全绿。存量失败显式登记，而不是删掉或到处加 skip：

```python
KNOWN_FAILURE_PREFIXES = ['tests/unit/xxx/test_yyy.py']  # 存量待修复


def pytest_addoption(parser):
    parser.addoption('--run-known-failures', action='store_true', default=False)


def pytest_collection_modifyitems(config, items):
    if config.getoption('--run-known-failures'):
        return
    skip = pytest.mark.skip(reason='known failure')
    for item in items:
        if item.get_closest_marker('known_failure') or any(
            item.nodeid.startswith(p) for p in KNOWN_FAILURE_PREFIXES
        ):
            item.add_marker(pytest.mark.known_failure)
            item.add_marker(skip)
```

这份清单就是测试债务列表，`--run-known-failures` 用来确认是否已经修好。

### 2.7 全局状态隔离 `[A]`

- 第三方库的类级缓存会跨用例污染：用 `autouse` fixture 在每个用例前重置。来源 A 重置了 redis-py `Lock` 的 Lua 脚本缓存，否则 FakeRedis 注册的脚本会影响后续真实 Redis 测试。
- 依赖注入容器提供 `clear_all_beans()`，fixture 进入和退出时都清一次。
- 修改全局 settings 时用 contextmanager 同时保存和恢复 settings 对象字段与对应环境变量。

### 2.8 值得复用的测试类型 `[A]`

- **日志断言测试**（`test_*_logging.py`）：patch 模块级 logger，断言关键运维日志（读取数量、重试、补偿）仍在输出，防止重构时被误删。
- **故障注入 walkthrough**：用「首次失败、第二次成功」的 handler 走通 outbox 投递 → 失败 → 重试 → 成功的全链路。
- **多进程分布式测试**：测试里启动两个真实服务进程，验证跨节点任务取消经 Redis Stream 生效。
- **部署模式参数化**：`@pytest.mark.parametrize('redis_mode', [standalone, pytest.param('cluster', marks=pytest.mark.cluster)], indirect=True)`，同一用例覆盖单机和集群。

### 2.9 Agent 写测试的规则 `[A]`

写进 `AGENTS.md`，约束 Agent 补测试时的行为：

1. 未经明确要求不修改生产代码。
2. 先列测试矩阵：成功、失败、边界、异常、状态迁移，再写测试。
3. 只有能提升稳定性或消除重复 setup 时才抽 harness。
4. 测试暴露了源码缺陷时写 findings，不顺手修。
5. 长任务在 `tmp/unit-test-session.md` 维护进度，便于跨会话接手。
6. 要求稳定性报告时同时产出 `tmp/unit-test-stability.md` 和 `.json`。

另配一个 `test-runner` 子 Agent：按 `src/a/b.py → tests/a/test_b.py` 的规则和引用搜索找出相关测试，只跑这些测试，输出固定格式报告。

## 3. Testcontainers

### 3.1 Fixture 结构 `[A]`

- 容器用 `scope='session'`，一次测试会话只起一次；engine 和建表用 `scope='function'`，每个用例拿到干净的库。
- 连接 URL 在 fixture 里转换驱动（`postgresql+psycopg2://` → `postgresql+asyncpg://`）。
- 镜像版本与生产和本地 compose 保持一致（如 `postgres:17.4-alpine`、`redis:5.0.14-alpine`）。
- 子目录的 `conftest.py` 通过 import 复用上层 fixture，不重复定义容器。

### 3.2 Docker 不可用时自动跳过 `[A]`

```python
_DOCKER_AVAILABLE = None


def pytest_collection_modifyitems(config, items):
    global _DOCKER_AVAILABLE
    if _DOCKER_AVAILABLE is None:
        try:
            import docker
            docker.from_env().ping()
            _DOCKER_AVAILABLE = True
        except Exception:
            _DOCKER_AVAILABLE = False
    if _DOCKER_AVAILABLE:
        return
    skip = pytest.mark.skip(reason='Docker unavailable, skip integration tests')
    for item in items:
        if 'integration' in item.keywords:
            item.add_marker(skip)
```

没有 Docker 的本地环境和受限 CI 都能跑通其余测试。需要强制执行集成测试的 CI 阶段应把跳过数计为失败，避免静默漏测。

### 3.3 Redis Cluster 容器 `[A]`

testcontainers 没有现成的集群模块时：起 3 个 `DockerContainer('redis:...')`，`network_mode='host'`，每个节点带 `--cluster-enabled yes --cluster-announce-ip 127.0.0.1`；等端口 ping 通后，在第一个容器里执行 `redis-cli --cluster create ... --cluster-replicas 0 --cluster-yes`，再轮询 `CLUSTER INFO` 直到 `cluster_state:ok`。

## 4. 数据库迁移

### 4.1 用临时容器生成迁移 `[A]`

规则写进 `AGENTS.md`：ORM 是 schema 的唯一来源；生成迁移只能用脚本；禁止直接 `alembic revision`、手写迁移内容或改 `revision`/`down_revision`。

脚本流程：起临时 PostgreSQL 容器（固定的非默认端口）→ 在空库执行 `alembic upgrade head` → `alembic revision --autogenerate` → `trap cleanup EXIT` 删除容器。所有人都基于同一个「空库加现有迁移」生成，结果不受本地库脏数据影响。脚本结束时打印人工复查清单（如删掉 autogenerate 带出的 `autoincrement=True`）。

### 4.2 生成给 DBA 审核的净变更 SQL `[A]`

一个分支上可能有多个过程性迁移，DBA 需要的是最终 DDL 差异：

- 用临时 git worktree 检出基线分支，两个临时库分别升级到基线 head 和当前分支 head，用 `migra` 对比生成净变更 SQL。
- 两种产物：`delta`（相对主干，用于评审）和 `release`（相对生产当前 revision，用于发布）；也支持手动指定起点 revision。
- 注释差异单独输出一份 patch。
- 生成后默认回放验证：把 SQL 应用到起点库，再和目标库对比，确认没有残差。
- 存在多个 Alembic head 时直接报错，要求先人工整理迁移链。

### 4.3 SQL 评审 skill `[A]`

项目级 `sql-spec` skill 规定 DDL 评审流程：定位执行 SQL 与回滚 SQL，逐项检查命名、字段类型、索引和禁止项，并验证回滚 SQL 能完整撤销结构变更；报告按「总体评估 → 严重问题 → 优化建议 → 问题清单 → 修复 SQL」输出。

## 5. 本地依赖环境 `[A]`

`docker-compose.deps.yml` 配合 `dev_up_deps.sh` / `dev_down_deps.sh`：

- 每个服务都配 `healthcheck`，脚本等服务健康后再继续。
- 数据放具名卷，重复执行不丢数据。
- 密码幂等：env 文件里已有密码就复用，没有才用 `secrets.token_hex` 生成。
- 用 `# BEGIN AUTO-GENERATED LOCAL DEPS` / `# END ...` 标记块回写 env 文件，只替换块内内容，不碰用户手写的配置。
- 依赖起来后自动跑一次迁移。
- 本地拓扑与生产一致：生产用 Redis Cluster，本地也起集群模式。

## 6. CI 覆盖率门禁

### 6.1 增量覆盖率 `[A]`

只要求本次改动的行被覆盖，存量低覆盖不阻塞新代码：

1. 解析基线：依次读 `COVERAGE_BASE_REF`、`BASE_REF` 和 CI 提供的 push-before SHA 等变量，都没有就用 `origin/master`；本地不存在时自动 fetch。
2. `git diff --unified=0 --diff-filter=ACMR base...HEAD -- src` 解析 hunk，得到每个文件的变更行号集合。
3. 选测试：按命名约定映射（`src/a/b.py → tests/unit/a/test_b{,_unit,_additional,...}.py`）；匹配不到就退到同目录的全部测试；仍然没有就跑全部单元测试，以捕获间接覆盖。
4. 跑测试生成 coverage JSON 和 junit XML；变更行 ∩ 可执行行 ∩ 已执行行得到增量覆盖率，默认阈值 85%。
5. 输出 JSON 报告（含每个文件的缺失行号）；没有业务代码改动时直接判通过。
6. `--list-tests-only` 只打印选中的测试，便于本地排查。

`.coveragerc` 排除 `tests/`、`scripts/`、`config/`、`conftest.py`。

### 6.2 依赖安装要用锁文件 `[A 的教训]`

来源 A 为了让 CI 在缺依赖的镜像上跑通，给约 86 个测试文件加了 `pytest.importorskip('sqlalchemy')`，并在脚本里做了多级依赖回退。结果是依赖缺失时测试静默跳过，覆盖率数字看不出问题。新项目应在 CI 用锁文件安装完整依赖（如 `uv sync --frozen`），装不上就直接失败。

## 7. 冒烟与故障验证脚本 `[A]`

单元测试和容器测试覆盖不到的真实依赖行为（对象存储策略、SSE 流、请求 ID 跨服务链路、白名单），用 `scripts/verify_*.py` 对运行中的服务验证：

- 统一参数 `--base-url` 和业务身份参数，docstring 里给出每个场景的完整命令。
- 支持故障场景：`--scenario redis-outage`（脚本里停 Redis，观察 API 错误，再恢复）、`--batch-count 20`（制造积压，观察日志和指标）。
- 正向和反向成对出现，如对象存储策略验证同时有允许和拒绝两个脚本。
- 手动接口调试用的 `.http` 文件和测试放在一起。

## 8. Agent 工作面 `[A]`

- `AGENTS.md` 写成导航索引：快速定位表（设计总览、测试方案、API/SQL 规范）和模块索引表（模块 → 设计文档 → 代码目录）；规则部分只写高频踩坑点（迁移命令、DI 例外、测试命令、分支命名）。
- 项目级 skill（API 规范、SQL 规范）放在 `.agents/skills/`，镜像到各宿主目录。镜像要用软链或同步脚本维护，避免多份副本漂移。
- 需求走 OpenSpec 提案（proposal / design / tasks / specs，完成后归档）；引入 pre-commit 这类工程设施本身也走提案，留下设计记录。
- 子 Agent 分工：`pre-commit-checker` 修检查，`test-runner` 跑相关测试，两者都以「变更 ID + 文件列表」为输入、固定模板为输出，方便主 Agent 汇总。

## 9. 反模式与漂移

来源项目里观察到的问题，新项目直接避开：

| 问题 | 表现 | 做法 |
| --- | --- | --- |
| 配置多处定义 | markers 同时写在 `pytest.ini`、`pyproject.toml` 和 `conftest.py`；存在 `pytest.ini` 时 pyproject 里的 pytest 配置不生效，改了也没用 | pytest 配置只放一处 |
| 测试入口多套且漂移 | Makefile 的模块目标指向 `tests/quota/`，实际目录已迁到 `tests/unit/quota/`；另一个 shell 入口用 pip 装依赖，而项目主流程用 uv | 只保留一个入口（`make test` 或 `uv run pytest`），其他入口调用它 |
| harness 脚本本身没被运行过 | shell 入口里 `"$PYTEST_CMD" $ARGS` 把 `python3 -m pytest` 当成一个命令名，必然失败；`set -e` 下后面的 `EXIT_CODE=$?` 也执行不到 | harness 脚本至少在 CI 里冒烟执行一次 |
| 集成测试用 `create_all` 建表 | 迁移脚本从未被测试执行，ORM 与迁移不一致时测试照样通过 | 加一个测试：空库 `upgrade head` 后与 ORM metadata 对比无差异 |
| 子目录重复定义容器 fixture | 两个 conftest 各起一个 PostgreSQL 容器 | 容器 fixture 只定义一次，子目录 import 复用 |
| 远端测试硬编码地址 | 稳定性测试里写死 `BASE_URL = 'http://XXX:8000'` | 从环境变量读，打 `external` marker，未配置时跳过 |
| 静默跳过掩盖漏测 | `importorskip` 和 Docker 自动跳过，让缺依赖时也显示通过 | 强制阶段把 skip 数纳入门禁 |
| 存量豁免只增不减 | ruff `ignore` 里的存量规则没有棘轮 | CI 统计违规数，只允许持平或下降 |

## 10. 新项目接入清单

按投入产出排序，前一级稳定后再加下一级。

**P0：第一天就建**

- [ ] pre-commit：formatter、linter、类型检查、secrets 扫描、基础卫生检查；CI 执行同一条 `pre-commit run --all-files`。
- [ ] 单一测试入口；裸跑只跑单元测试；定好 marker 体系。
- [ ] 把领域逻辑与 IO 分离的分层约定写进 `AGENTS.md`，单元测试不 Mock。
- [ ] testcontainers fixture（session 级容器、function 级建表）和 Docker 不可用时自动跳过。
- [ ] CI 用锁文件安装依赖。

**P1：有数据库和多人协作后**

- [ ] 临时容器生成迁移的脚本，以及迁移一致性测试。
- [ ] compose 本地依赖和幂等启动脚本。
- [ ] 增量覆盖率门禁。
- [ ] 测试方案文档模板（单元用例表加模块端到端场景表）。

**P2：随项目演进逐步加**

- [ ] 把重复的评审意见写成 AST 检查脚本。
- [ ] `known_failure` 隔离机制。
- [ ] 日志断言测试、故障注入 walkthrough、多进程测试。
- [ ] `verify_*` 冒烟和故障脚本。
- [ ] 给 DBA 的净变更 SQL 生成。
- [ ] Agent 子角色（pre-commit 修复、相关测试运行）和写测试规则。
