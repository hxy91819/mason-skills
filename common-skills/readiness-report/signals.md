# Readiness 信号目录

本目录是 Phase 3 逐信号评估的依据。每个信号带：ID、名称、类别、scope（repository / application）、
评估口径。标注 **[Skippable]** 的信号在前提不满足时允许 numerator = null 并注明原因；其余信号必须给出 0/1（repository）或 0..N（application）。

- **scope = repository**：整个仓库一个判定，分母恒 1。
- **scope = application**：对 Phase 2 盘点的每个 application 各判一次，分母 = N。

## Style & Validation

### lint_config — Linter Configuration
scope: application。项目配置了 linter 或静态分析器：TS/JS 的 ESLint（`.eslintrc.*`、`eslint.config.*`）；
Python 的 ruff/flake8（`pyproject.toml`、`.flake8`、`ruff.toml`）；Java 的 Checkstyle/PMD/SpotBugs；
Ruby 的 RuboCop；Go 的 `golangci-lint` 配置。存在配置文件即算。

### type_check — Type Checker
scope: application。使用静态类型检查：TypeScript 的 `tsconfig.json`；Python 的 mypy
（`mypy.ini` 或 `pyproject.toml` 的 `[tool.mypy]`）；Java 自带强类型但要求启用注解处理器或
`-Werror` 类严格编译选项才算。

### strict_typing — Strict Typing
scope: application。TypeScript `tsconfig.json` 含 `"strict": true`；Python mypy strict 模式；
或 SonarQube/SonarCloud 的类型相关规则且未显式禁用。

### formatter — Code Formatter
scope: application。使用自动化格式化工具：TS/JS 的 Prettier（`.prettierrc*`）或 Oxfmt；
Python 的 Black（`[tool.black]`）；Java 的 Spotless；Go 的 gofmt 挂接 CI。

### naming_consistency — Naming Consistency
scope: repository。命名约定被强制执行：ESLint `@typescript-eslint/naming-convention`、
pylint naming-style、Checkstyle naming 模块，或 AGENTS.md/CONTRIBUTING.md 明文写出命名约定。

### cyclomatic_complexity — Cyclomatic Complexity
scope: repository。复杂度被分析或监控：ESLint complexity 规则、Python 的 radon/lizard、
Go 的 gocyclo/go-critic、Java 的 PMD CyclomaticComplexity、SonarQube 复杂度质量门。

### pre_commit_hooks — Pre-commit Hooks
scope: repository。通过 Git hooks 强制质量检查：Husky/lint-staged（TS/JS）、
`.pre-commit-config.yaml`（Python）、Gradle 的 check task 挂 pre-commit。

## Build System

### build_cmd_doc — Build Command Documentation
scope: repository。README/AGENTS.md 写明构建或打包命令（如 `npm run build`、`mvn package`）。

### deps_pinned — Dependencies Pinned
scope: application。依赖锁定：lockfile 已提交（`package-lock.json`、`yarn.lock`、`pnpm-lock.yaml`、
`poetry.lock`）；Python `requirements.txt` 用 `==` 钉版本；Java 用固定版本号，无 `LATEST`/版本区间。

### vcs_cli_tools — VCS CLI Tools [Skippable]
scope: repository。`gh`/`glab` 等 VCS CLI 已安装并认证（`gh auth status` 通过）。这是多个
远端检查信号的前提；CLI 不可用或未认证时 skip，并连带触发相关远端信号的 skip。

### single_command_setup — Single Command Setup
scope: repository。README、AGENTS.md 或 SKILLS 记录了一条（或极短的）从 fresh clone 到运行
开发环境的命令序列（如 `bin/dev`、`make dev`、`docker compose up`）。

### monorepo_tooling — Monorepo Tooling [Skippable]
scope: repository。仅对 monorepo 适用：存在 workspace/多包配置定义组件边界（npm/pnpm/yarn
workspaces、Turborepo、Nx、Lerna、pants、poetry multi-package、`go.work`、Cargo workspaces）。
单仓库 repo 不适用，skip。

### heavy_dependency_detection — Heavy Dependency Detection
scope: application。包体积/重依赖分析工具：`bundle-analyzer`、`webpack-bundle-analyzer`、
source-map-explorer、`cargo-bloat`、Maven Enforcer 依赖规则。

### unused_dependencies_detection — Unused Dependencies Detection
scope: application。检测未用依赖：depcheck、`knip`、`pip-autoremove`、Maven Enforcer 的
`dependencyConvergence`/unused 依赖规则。

### version_drift_detection — Version Drift Detection
scope: repository。跨包依赖版本漂移被检测：syncpack、manypkg、Renovate grouping、
Maven BOM 统一版本、`go.work` 的 workspace 统一。

## Testing

### unit_tests_exist — Unit Tests Exist
scope: application。存在单元测试：TS/JS 的 `*.test.ts` 或 `__tests__/`；Python 的
`tests/test_*.py`；Java 的 `src/test/java`；Ruby 的 `test/` 或 `spec/`。

### unit_tests_runnable — Unit Tests Runnable [Skippable]
scope: application。单测可用一条有界命令本地运行。**命令契约**：单条直接 Execute 命令、
显式设 timeout；命令行里不得出现 `2>&1`、`|`、`head`、`tail`、`tee`、shell `timeout`（会掩盖
runner 退出码）。TS/JS 只验证"可列出测试"：Jest 用 `npm test -- --listTests`，Vitest 用
`npx --no-install vitest list`，先看 `package.json`；给 package script 传测试文件参数不算数
（script 仍可能跑完整套件）。**不执行 TS/JS 测试**。Python 选一个现有测试文件跑
`python -m pytest --collect-only <file>`，收集成功即可，不执行。缺本地运行时按 skip 规则处理。

### integration_tests_exist — Integration Tests Exist
scope: application。存在集成或 e2e 测试：cypress/、`playwright.config.ts`、
`tests/integration/`、Behave `.feature`、Java 的 `*IT.java`。

### test_coverage_thresholds — Test Coverage Thresholds
scope: repository。CI 强制最低覆盖率：`--coverage` 阈值（Jest/vitest 配置）、`fail_under`
（coverage.py）、JaCoCo `minimum`、Codecov status checks。

### test_performance_tracking — Test Performance Tracking
scope: repository。测试时长被度量跟踪：CI 输出 timing（`pytest --durations`、`vitest --verbose`）、
测试报告产物、BuildPulse/Datadog CI 等分析平台。

### flaky_test_detection — Flaky Test Detection [Skippable]
scope: repository。主动管理不稳定测试：`gh pr list --state all --limit 10 --json statusCheckRollup`
查重复 check 名（重试痕迹）；或重试配置（pytest-rerunfailures、vitest-retry、Gradle retry）、
quarantine 机制。无 `gh` 权限时只查仓库内证据。

### test_naming_conventions — Test File Naming Conventions
scope: repository。测试文件命名一致且被强制：lint 规则、CI 检查或文档明文约定
（`*.test.ts` vs `*.spec.ts` 混用不受罚则 fail）。

### test_isolation — Test Isolation
scope: application。测试相互隔离：mock 外部依赖、测试数据库事务回滚、`jest.resetModules`、
pytest fixtures 隔离；明显依赖执行顺序或共享全局状态的记 fail。

## Documentation

### readme — README File
scope: repository。根目录存在带 setup/usage 说明的 `README.md`。

### agents_md — AGENTS.md File
scope: repository。根目录存在 `AGENTS.md`，含面向自治 agent 的设置、构建、测试、工作流与
项目约定。

### documentation_freshness — Documentation Freshness
scope: repository。`git log --since="180 days ago" --name-only -- README.md AGENTS.md CONTRIBUTING.md`
在 180 天内有文档更新。

### automated_doc_generation — Automated Documentation Generation
scope: repository。工具自动生成/更新技术文档：Swagger/OpenAPI、JSDoc、Sphinx、Javadoc/Dokka、
docusaurus 自动 API 文档。

### agents_md_validation — AGENTS.md Freshness Validation
scope: repository。有自动化校验 AGENTS.md 与代码一致：CI 脚本检查文档命令存在、AGENTS.md
lint、文档链接检查器。

### skills — Skills Configuration
scope: repository。存在符合 Claude skills 标准的技能目录（`.factory/skills/`、`.skills/`、
`.claude/skills/`，向上走到 git root）：每个技能 `{skill-name}/SKILL.md` 带 YAML frontmatter。

### api_schema_docs — API Schema Docs [Skippable]
scope: application。提供机器可读 API schema：OpenAPI/Swagger、GraphQL schema、gRPC proto。
纯库/CLI 无对外 API 时 skip。

## Development Environment

### devcontainer — Dev Container
scope: repository。`.devcontainer/devcontainer.json` 存在且有效。

### devcontainer_runnable — Devcontainer Runnable [Skippable]
scope: repository。devcontainer 能构建并运行；本地无容器运行时按 skip 规则处理，不臆断。

### env_template — Environment Template
scope: application。`.env.example` 或文档列全必需环境变量。

### local_services_setup — Local Services Setup
scope: repository。本地依赖可一键拉起：`docker-compose.yml` 或文档写明本地数据库/缓存/队列的
启动方式。

### database_schema — Database Schema [Skippable]
scope: application。schema 定义文件随仓库走：migrations 目录、`schema.rb`、Prisma schema、
Flyway/Liquibase 脚本。无数据库的 repo skip。

## Debugging & Observability

### structured_logging — Structured Logging
scope: application。使用结构化日志库：winston/pino/bunyan（TS/JS）、structlog/loguru
（Python）、logstash-logback-encoder（Java）。

### distributed_tracing — Distributed Tracing
scope: application。请求链路追踪：OpenTelemetry、X-Request-ID 传播、Micrometer Tracing。

### metrics_collection — Metrics Collection
scope: application。性能遥测：Datadog、Prometheus、New Relic、CloudWatch、Spring Actuator
metrics。

### error_tracking_contextualized — Error Tracking Contextualized
scope: application。Sentry/Bugsnag 集成带 source map 和 breadcrumbs，而非裸上报。

### alerting_configured — Alerting Configured
scope: repository。PagerDuty/OpsGenie 集成或告警规则（alertmanager 规则、CloudWatch alarms）。

### runbooks_documented — Runbooks Documented
scope: repository。事故响应手册存在：`runbooks/`、`docs/incident/`、值班 playbook。

### health_checks — Health Checks
scope: application。健康检查端点或存活探针：`/healthz`、Kubernetes liveness/readiness probe、
Rails `up` 路由。

### profiling_instrumentation — Profiling Instrumentation
scope: application。性能剖析基础设施：py-spy、pprof、continuous profiler (Pyroscope/Parca)。

### circuit_breakers — Circuit Breakers
scope: application。熔断/韧性模式：resilience4j、Polly、circuit breaker 库、超时重试策略。

## Security

### branch_protection — Branch Protection [Skippable]
scope: repository。需管理员权限。`gh api repos/{owner}/{repo}/rulesets` 查活跃 rulesets 要求
PR review 且禁直推；空则查 legacy `gh api repos/{owner}/{repo}/branches/main/protection`。
无权限或 CLI 不可用 skip。

### secret_scanning — Secret Scanning [Skippable]
scope: repository。secret 扫描：GitHub 原生 `gh api /repos/{owner}/{repo}/secret-scanning/alerts`
（403/disabled = fail，200 = pass），或 gitleaks/trufflehog/detect-secrets 的 CI job、pre-commit。
无权限时只查仓库内证据。

### codeowners — CODEOWNERS File
scope: repository。`CODEOWNERS` 存在于 `.github/`、根目录或 `docs/`。

### automated_security_review — Automated Security Review Generation [Skippable]
scope: repository。自动生成安全审查报告（不是只有 pass/fail）：CodeQL/Semgrep/Snyk 扫描结果、
依赖审计 PR 评论、容器扫描摘要。`gh api /repos/{owner}/{repo}/code-scanning/alerts` 可查。
需要生成可读报告；无证据且 CLI 不可用 skip。

### dast_scanning — DAST Scanning [Skippable]
scope: application。动态安全测试对运行中应用执行：OWASP ZAP CI job、Burp 扫描流水线。无
web 应用 skip。

### pii_handling — PII Handling
scope: repository。PII 检测/处理工具：PII 扫描器、数据脱敏中间件、`pii-anonymizer`。

### privacy_compliance — Privacy Compliance
scope: repository。GDPR/CCPA 合规基建：数据删除工作流、cookie 同意、数据驻留配置。

### secrets_management — Secrets Management
scope: repository。安全密钥管理：Vault、AWS Secrets Manager、SOPS、doppler；`.env` 不进 Git
且有替代方案。

### log_scrubbing — Sensitive Data Log Scrubbing
scope: application。日志脱敏机制：redaction filter、Rails parameter filter、自定义 scrubber。

### gitignore_comprehensive — Gitignore Comprehensive
scope: repository。`.gitignore` 覆盖 secrets 与构建产物；`git status` 无应忽略而未忽略的产物。

### min_release_age — Minimum Dependency Release Age
scope: repository。依赖发布后不立即采用（缓解供应链攻击）：Renovate minimumReleaseAge、
dependabot 版本延迟策略、锁定 + 定期批量升级。

## Delivery & Deployment

### fast_ci_feedback — Fast CI Feedback [Skippable]
scope: repository。CI 反馈 < 10 分钟：`gh pr list --state merged --limit 20 --json statusCheckRollup`
计算 check 时长。无 `gh` 权限时从 workflow 配置合理推断（无耗时证据则 fail）。

### build_performance_tracking — Build Performance Tracking [Skippable]
scope: repository。构建时长被度量优化：turbo/nx/Gradle/Maven 构建缓存、`gh run view --log`
构建计时、Develocity。无 `gh` 时查构建缓存配置。

### deployment_frequency — Deployment Frequency [Skippable]
scope: repository。每周多次自动化部署：`gh release list --limit 30` 加部署 workflow 的
`gh run list --workflow=*.yml --limit 30`（注意 gh CLI 不支持通配符，需先 `ls .github/workflows/`
找出确切文件名）。

### automated_pr_review — Automated PR Review Generation
scope: repository。自动 PR review：CodeRabbit、Codium、Factory Droid review、GitHub CODEOWNERS
机器人评论。`gh pr list` 查 review 机器人痕迹。

### agentic_development — Agentic Development
scope: repository。AI agent 已进入开发工作流：`git log` 作者含 `factory-droid[bot]`、
`Claude Code`、`Co-authored-by` agent 头；AGENTS.md/CLAUDE.md 存在；dependabot 等依赖
机器人不算。

### release_notes_automation — Release Notes Automation
scope: repository。自动生成 release notes/changelog：GitHub 自动 release notes 配置、
changesets、conventional-changelog。

### release_automation — Release Automation
scope: repository。发布/部署流水线自动化：GitHub Actions release workflow、semantic-release。

### progressive_rollout — Progressive Rollout
scope: repository。金丝雀/百分比发布：feature flag 百分比放量、ring deployment、canary
部署配置（Kubernetes canary、AWS CodeDeploy）。

### rollback_automation — Rollback Automation
scope: repository。一键或自动回滚且文档化：`kamal app rollback`、`gh release edit`、
部署脚本的 rollback 子命令、Kubernetes `rollout undo`。

### dependency_update_automation — Dependency Update Automation
scope: repository。Dependabot 或 Renovate 配置存在（`.github/dependabot.yml`、`renovate.json`）。

## Code Health

### dead_code_detection — Dead Code Detection
scope: application。死代码检测：knip、ts-prune、vulture、PMD unused rules、JDeprecation 分析。

### tech_debt_tracking — Technical Debt Tracking
scope: repository。技术债被跟踪：TODO/FIXME 扫描工具、SonarQube technical debt 比率、
专门的 debt tracking 文档。

### duplicate_code_detection — Duplicate Code Detection
scope: repository。DRY 检测：jscpd、PMD CPD、simian 配置。

### n_plus_one_detection — N+1 Query Detection [Skippable]
scope: application。N+1 检测：bullet/django-silk（Rails 的 bullet、Django nplusone）、
`includes` lint 规则。无 ORM 的 repo skip。

### large_file_detection — Large File Detection
scope: repository。超大文件被检测/阻止：pre-commit 检查、`.gitattributes` 大小限制、CI
文件大小 guard（一般 > 1MB 的源文件视为 fail 迹象，除非有工具豁免）。

### code_modularization — Code Modularization Enforcement
scope: repository。模块边界被工具强制：Nx module boundaries、eslint-plugin-boundaries、
ArchUnit、import-linter。

## Task Discovery

### issue_templates — Issue Templates
scope: repository。`.github/ISSUE_TEMPLATE/` 结构化模板存在。

### pr_templates — PR Templates
scope: repository。`.github/pull_request_template.md` 存在。

### issue_labeling_system — Issue Labeling System
scope: repository。一致的 priority/type/area 标签体系（`.github/labels.yml` 或仓库标签约定
文档）。

### backlog_health — Backlog Health [Skippable]
scope: repository。issue 标题清晰且有近期活跃。无远端访问权限时 skip。

### task_discovery — Task Discovery
scope: repository。基础设施让 agent 能自主发现和圈定工作：`good first issue` 标签体系、
roadmap 文档、`docs/next-steps.md` 之类的明确工作队列。

### error_to_insight_pipeline — Error to Insight Pipeline
scope: repository。错误从跟踪系统流向可执行 issue：Sentry→GitHub issue 集成、自动工单创建。

## Product & Experimentation

### product_analytics_instrumentation — Product Analytics Instrumentation [Skippable]
scope: application。Mixpanel/Amplitude/PostHog 埋点接入。非面向用户的产品（纯库、CLI 工具集）
skip。

### feature_flag_infrastructure — Feature Flag Infrastructure
scope: application。LaunchDarkly、Statsig、Unleash、GrowthBook 或自建 flag 系统配置。

### dead_feature_flag_detection — Dead Feature Flag Detection [Skippable]
scope: repository。工具检测过期 flag：LaunchDarkly flag 清理报告、`fflip` 清扫脚本、
SonarQube feature flag 规则。无 flag 系统时 skip。

---

## Level 语义（人读报告用）

| Level | 语义 |
|---|---|
| 1 Basic | 及格线，抓住明显错误的底线工具 |
| 2 Infrastructure | 已投入基础设施、CI/CD 与流程建设 |
| 3 Advanced | 安全、可观测性与端到端验证已覆盖 |
| 4 Expert | 精通高级 readiness 条件 |
| 5 Autonomous | agent 可独立运作：自主发现工作并维持质量，无需人工介入 |
