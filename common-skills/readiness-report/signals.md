# Readiness 信号目录

本目录是 Phase 3 逐信号评估的依据。每个信号带：ID、名称、类别、scope（repository / application）、
评估口径。共 **84 个信号**，按原版二进制的 criterion 数组（`FK`）与 9 个 category 对齐。

- **scope = repository**：整个仓库一个判定，分母恒 1。
- **scope = application**：对 Phase 2 盘点的每个 application 各判一次，分母 = N。
- 标注 **[Skippable]** 的信号在前提不满足时允许 numerator = null 并注明原因；其余信号必须给出 0/1（repository）或 0..N（application）。
- 引用块中的英文为原版二进制 instructions 原文（仅换行重排）；未引用原文的条目为口径摘要，评估语义与原版一致。

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
scope: application。命名约定被强制执行：ESLint `@typescript-eslint/naming-convention`、
pylint naming-style、Checkstyle naming 模块，或 AGENTS.md/CONTRIBUTING.md 明文写出命名约定。

### cyclomatic_complexity — Cyclomatic Complexity
scope: application。复杂度被分析或监控：ESLint complexity 规则、Python 的 radon/lizard、
Go 的 gocyclo/go-critic、Java 的 PMD CyclomaticComplexity、SonarQube 复杂度质量门。

### pre_commit_hooks — Pre-commit Hooks
scope: application。通过 Git hooks 强制质量检查：Husky/lint-staged（TS/JS）、
`.pre-commit-config.yaml`（Python）、Gradle 的 check task 挂 pre-commit。

## Build System

### build_cmd_doc — Build Command Documentation
scope: repository。README/AGENTS.md 写明构建或打包命令（如 `npm run build`、`mvn package`）。

### deps_pinned — Dependencies Pinned
scope: repository。依赖锁定：lockfile 已提交（`package-lock.json`、`yarn.lock`、`pnpm-lock.yaml`、
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
scope: application。单测可用一条有界命令本地运行。原版命令契约（原文）：

> Tests runnable locally – Use one direct, bounded Execute command. Set the Execute
> timeout field; do not put shell output controls after the test runner. Forbidden
> evidence-command text includes `2>&1`, `|`, `head`, `tail`, `tee`, and the shell
> `timeout` command. The Execute tool captures output and preserves the runner exit
> status. For TS/JS, use a runner-native list or collection mode and confirm it lists
> tests without PASS/FAIL results or an executed-test count. Inspect package.json
> first. A test-file argument to a package script is not sufficient because the script
> can still run its complete configured suite. BAD: `npm test -- test/foo.test.ts | head`
> can execute the full configured suite and hide the runner exit status. When the test
> script invokes Jest, GOOD: `npm test -- --listTests`; for Vitest, GOOD:
> `npx --no-install vitest list`. Do not execute TS/JS tests. For Python, select one
> existing test file from the bounded unit_tests_exist sample and run
> `python -m pytest --collect-only <test-file>`; successful collection is sufficient,
> so do not execute tests. If uv or tox is unavailable but Python and pytest are
> installed, use this direct command instead of skipping. For Java, select one
> existing test from the bounded unit_tests_exist sample. For Gradle, BAD:
> `./gradlew test --tests ExampleTest --dry-run` does not prove test execution. GOOD:
> `./gradlew --rerun-tasks test --tests <TestClass>`, replacing `test` with
> `<module>:test` when needed. For Maven, run `./mvnw -Dtest=<TestClass> test`. For a
> Maven module, run `./mvnw -f <module>/pom.xml -Dtest=<TestClass> test`. Never pass
> Gradle's `--rerun-tasks` option to Maven. Pass Java only if the direct command exits
> zero and the selected test task runs. A Gradle test task marked UP-TO-DATE,
> FROM-CACHE, SKIPPED, or NO-SOURCE does not prove execution. Java task-listing,
> dry-run, and compile-only commands also do not pass. Do not run the full suite. If
> the command reports an unavailable, invalid, or incompatible JDK, correct an evident
> environment issue once and retry. Skip only if the required JDK remains unavailable.
> For other ecosystems, skip only when the language runtime is unavailable. Do not
> treat unrelated shell or build failures as a missing runtime or JDK.

### integration_tests_exist — Integration Tests Exist
scope: application。存在集成或 e2e 测试：cypress/、`playwright.config.ts`、
`tests/integration/`、Behave `.feature`、Java 的 `*IT.java`。

### test_coverage_thresholds — Test Coverage Thresholds
scope: application。最低覆盖率被强制执行。原版口径（原文）：

> Test coverage thresholds – Minimum coverage percentages are enforced. Common
> approaches: vitest.config.* coverage thresholds, jest.config.* coverageThreshold,
> pytest --cov-fail-under, Maven jacoco:check, Gradle JaCoCo violationRules/verification
> tasks, Kotlin Kover verification, Codecov/Coveralls with PR status checks blocking on
> coverage, or SonarQube/SonarCloud quality gates. Other CI gates or tools that enforce
> minimum coverage also satisfy this criterion. Agents must know they have to maintain
> coverage, not just that it is tracked.

### test_performance_tracking — Test Performance Tracking
scope: application。测试时长被度量跟踪。原版口径（原文）：

> Test performance tracking – Test suite duration is measured and tracked. Check:
> 1) CI outputs that show test timing (e.g., vitest --verbose, pytest --durations).
> 2) Test reports uploaded as artifacts. 3) Integration with test analytics platforms
> (BuildPulse, Datadog CI, GitHub Actions test reporting). 4) Config flags for test
> timing output in package.json scripts or CI workflows. Maven Surefire/Failsafe and
> Gradle reports qualify only when CI retains or analyzes them. Evidence that org
> monitors test performance, not just pass/fail.

### flaky_test_detection — Flaky Test Detection [Skippable]
scope: application。主动管理不稳定测试。原版口径（原文）：

> Flaky test detection – Check for proactive flaky test management. If `gh` or `glab`
> CLI is available and authenticated, run `gh pr list --state all --limit 10 --json
> statusCheckRollup` to detect duplicate check names (indicates retries/flakiness).
> Also check for: 1) Test retry configuration (vitest-retry, pytest-rerunfailures,
> Gradle test-retry, Develocity testRetry, or Maven Surefire rerunFailingTestsCount).
> 2) Flaky test tracking tools (BuildPulse, Develocity). 3) CI quarantine/skip
> mechanisms. 4) Test stability metrics. Skip if `gh`/`glab` CLI is not available or
> not authenticated and no other flaky test detection evidence exists.

### test_naming_conventions — Test File Naming Conventions
scope: application。测试文件命名一致且被强制：lint 规则、CI 检查或文档明文约定
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
scope: repository。文档随代码变更保持更新。原版口径（原文）：

> Documentation freshness – Run
> `git log --since="180 days ago" --name-only -- README.md AGENTS.md CONTRIBUTING.md
> | grep -E "\.(md)$" | head -1`. PASS if at least one of README.md, AGENTS.md, or
> CONTRIBUTING.md was modified in the last 180 days. This is a simple binary check:
> key docs updated recently = pass.

### automated_doc_generation — Automated Documentation Generation
scope: repository。工具自动生成/更新技术文档：Swagger/OpenAPI、JSDoc、Sphinx、Javadoc/Dokka、
docusaurus 自动 API 文档。

### agents_md_validation — AGENTS.md Freshness Validation
scope: repository。有自动化校验 AGENTS.md 与代码一致：CI 脚本检查文档命令存在、AGENTS.md
lint、文档链接检查器。

### skills — Skills Configuration
scope: repository。仓库有符合 Claude skills 标准的技能目录。原版口径（原文）：

> Skills configured – Check for skills directories (common locations:
> `.factory/skills/`, `.skills/`, `.claude/skills/`, walk up to git root). Each skill
> should be in `{skill-name}/SKILL.md` format with either YAML frontmatter containing
> at minimum `name` and `description`, or table format (`| name | description |`).
> Verify at least one valid skill exists with non-empty prompt content. See
> https://code.claude.com/docs/en/skills for the open standard reference.

### api_schema_docs — API Schema Docs [Skippable]
scope: application。提供机器可读 API schema。原版口径（原文）：

> API schema docs – OpenAPI/Swagger specification or GraphQL schema exists for
> service APIs. Search recursively for files matching patterns:
> **/openapi.{json,yaml,yml}, **/swagger.{json,yaml,yml}, **/*.openapi.{json,yaml},
> **/*.swagger.{json,yaml}, **/schema.graphql, **/*.graphql, **/*.gql. PASS if any
> valid API schema file is found anywhere in the repository. Skip for non-API apps
> (e.g., libraries, CLI tools without HTTP APIs).

### service_flow_documented — Service Architecture Documented
scope: repository。架构图与服务依赖被文档化。原版口径（原文）：

> Service architecture documented – Check for: 1) Architecture diagram files
> (*.mermaid, *.puml, *.plantuml, docs/architecture*, docs/diagrams*). 2) Service
> dependency documentation showing external services, APIs, or databases the
> application calls. 3) Images in README/docs with names containing "architecture",
> "flow", "diagram", "sequence". PASS if any architecture diagrams OR service
> dependency documentation exists.

### interactive_qa_exists — Interactive QA Exists
scope: application。存在交互式验收途径：手动 QA 指南、验收 checklist、可操作的 demo/
验收环境说明（对应原版 Interactive QA Exists，"Interactive QA/acceptance testing exists,
e.g., manual test guides or acceptance checklists"）。

### interactive_qa_runnable — Interactive QA Runnable [Skippable]
scope: application。交互式验收当前可实际运行：本地能拉起目标应用并按指南操作。
本地缺运行时或环境依赖时按 skip 规则处理，不臆断。

## Development Environment

### devcontainer — Dev Container
scope: repository。`.devcontainer/devcontainer.json` 存在且有效。

### devcontainer_runnable — Devcontainer Runnable [Skippable]
scope: repository。devcontainer 能构建并运行；本地无容器运行时按 skip 规则处理，不臆断。

### env_template — Environment Template
scope: repository。`.env.example` 或文档列全必需环境变量。

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
scope: application。应用实现请求链路追踪。原版口径（原文，无前缀）：

> Check for trace ID or request ID propagation through the application
> (OpenTelemetry, X-Request-ID headers, Micrometer Tracing, Spring Cloud Sleuth,
> etc.) that allows following a request through the system.

### metrics_collection — Metrics Collection
scope: application。性能遥测。原版口径（原文，无前缀）：

> Check for metrics/telemetry instrumentation (Datadog, Axiom, Prometheus, New Relic,
> CloudWatch, Micrometer, Spring Boot Actuator metrics, etc.) for understanding
> application performance.

### code_quality_metrics — Code Quality Metrics Dashboard
scope: application。覆盖率、复杂度、可维护性指标被监控。原版口径（原文）：

> Code quality metrics tracked – Coverage, complexity, and maintainability metrics are
> monitored. If no admin/maintainer access, skip the code-scanning API check but still
> check for other approaches. Code scanning check: run
> `gh api /repos/{owner}/{repo}/code-scanning/analyses`; 403 "Code Security must be
> enabled" = FAIL, 200 with array = PASS. Also check: coverage bots in PR comments
> (run `gh pr list --state merged --limit 10 --json comments` and search for "coverage",
> "codecov", "coveralls"), coverage configuration (grep for "--coverage" in package.json
> test scripts, or check vite.config.* or vitest.config.* coverage settings),
> SonarQube/SonarCloud (provides coverage, maintainability, reliability metrics with
> quality gates; strong evidence if sonar.qualitygate.wait=true in CI). For Java, also
> check JaCoCo coverage, PMD complexity rules, PMD/SpotBugs maintainability reports,
> and Develocity dashboards configured with code-quality signals. Other code quality
> platforms or CI checks that track these metrics also satisfy this criterion.
> PASS if ANY method found. Skip if no evidence found and `gh`/`glab` CLI is not
> available, not authenticated, or lacks admin/maintainer access.

### error_tracking_contextualized — Error Tracking Contextualized
scope: application。Sentry/Bugsnag 集成带 source map 和 breadcrumbs，而非裸上报。

### alerting_configured — Alerting Configured
scope: application。PagerDuty/OpsGenie 集成或告警规则（alertmanager 规则、CloudWatch alarms）。

### runbooks_documented — Runbooks Documented
scope: repository。事故响应手册存在：`runbooks/`、`docs/incident/`、值班 playbook。

### deployment_observability — Deployment Observability
scope: application。部署影响可实时观察：部署标记接入监控（Sentry release tracking、
Datadog deployment markers）、发布后错误率/延迟对比视图、deploy dashboard。

### health_checks — Health Checks
scope: application。健康检查端点或存活探针：`/healthz`、Kubernetes liveness/readiness probe、
Rails `up` 路由。

### profiling_instrumentation — Profiling Instrumentation
scope: application。性能剖析基础设施：py-spy、pprof、continuous profiler (Pyroscope/Parca)。

### circuit_breakers — Circuit Breakers
scope: application。熔断/韧性模式：resilience4j、Polly、circuit breaker 库、超时重试策略。

## Security

### branch_protection — Branch Protection [Skippable]
scope: repository。仓库有分支保护规则。原版口径（原文）：

> Branch protection – Repository has branch protection rules. If no admin/maintainer
> access, skip this criterion. If access confirmed, check in order: 1) Modern
> rulesets: run `gh api repos/{owner}/{repo}/rulesets` and look for active rulesets
> targeting main/dev branches. If found, inspect ruleset details with
> `gh api repos/{owner}/{repo}/rulesets/{id}` to verify PR review requirements and
> direct push prevention. 2) Legacy branch protection (only if rulesets returns
> empty []): run `gh api repos/{owner}/{repo}/branches/main/protection` and
> `gh api repos/{owner}/{repo}/branches/dev/protection`. If both methods return
> 404/empty, branch protection is not configured. Skip if `gh`/`glab` CLI is not
> available, not authenticated, or lacks admin/maintainer access.

### secret_scanning — Secret Scanning [Skippable]
scope: repository。仓库扫描误提交的 secret。原版口径（原文）：

> Secret scanning – Repository scans for accidentally committed secrets. If no
> admin/maintainer access, skip the native secret scanning API check but still check
> for other approaches. Native check: run
> `gh api /repos/{owner}/{repo}/secret-scanning/alerts`; 404 with "disabled" message
> = FAIL (feature not enabled), 200 with array = PASS. Also check: GitHub Actions
> running gitleaks, trufflehog, or detect-secrets, pre-commit hooks with secret
> scanning, SonarQube/SonarCloud with security hotspots enabled (verify it is not
> explicitly disabled in sonar properties). Other secret detection tools or CI checks
> also satisfy this criterion. Skip if no evidence found and `gh`/`glab` CLI is not
> available, not authenticated, or lacks admin/maintainer access.

### codeowners — CODEOWNERS File
scope: repository。`CODEOWNERS` 存在于 `.github/`、根目录或 `docs/`。

### automated_security_review — Automated Security Review Generation [Skippable]
scope: repository。系统自动生成安全审查报告（不是只有 pass/fail）。原版口径（原文）：

> Automated security review generation – System automatically generates security
> review reports or assessments. If no admin/maintainer access, skip the
> code-scanning API check but still check for other approaches. Code scanning check:
> run `gh api /repos/{owner}/{repo}/code-scanning/alerts` for SAST tools (Semgrep,
> CodeQL, Snyk); 403 "Code Security must be enabled" = FAIL, 200 with results = PASS.
> Also look for: dependency audit reports in PR comments (Snyk, Dependabot), container
> scan summaries, or droid exec security assessments. Must generate readable reports,
> not just pass/fail status. Skip if no evidence found and `gh`/`glab` CLI is not
> available, not authenticated, or lacks admin/maintainer access.

### dast_scanning — DAST Scanning [Skippable]
scope: application。动态安全测试对运行中应用执行：OWASP ZAP CI job、Burp 扫描流水线。无
web 应用 skip。

### pii_handling — PII Handling
scope: application。PII 检测/处理工具：PII 扫描器、数据脱敏中间件、`pii-anonymizer`。

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
scope: repository。CI 反馈在 10 分钟内。原版口径（原文）：

> Fast CI feedback – CI pipeline provides feedback in under 10 minutes. If `gh` or
> `glab` CLI is available and authenticated, run
> `gh pr list --state merged --limit 20 --json statusCheckRollup`. For each PR, find
> all status checks in statusCheckRollup array and calculate CI duration from earliest
> startedAt to latest completedAt or updatedAt (ISO8601 timestamps). Example: if
> checks start at 10:00:00Z and finish at 10:06:00Z, CI duration is 6 minutes. Verify
> average CI duration is under 10 minutes for typical PRs. IMPORTANT: Calculate CI
> check duration, NOT PR merge time (createdAt to mergedAt). Focus on the primary CI
> workflow that runs on PRs. Skip if `gh`/`glab` CLI is not available or not
> authenticated.

本地补充：无 `gh` 时可从 workflow 配置与典型 job 时长合理推断，但无耗时证据时判 fail
（原版无此降级路径，此处为本地版口径）。

### build_performance_tracking — Build Performance Tracking [Skippable]
scope: repository。构建时长被度量优化：turbo/nx/Gradle/Maven 构建缓存、`gh run view --log`
构建计时、Develocity。无 `gh` 时查构建缓存配置。

### deployment_frequency — Deployment Frequency [Skippable]
scope: repository。系统每周多次自动化部署。原版口径（原文）：

> Frequent deployments – System deploys multiple times per week with automation. If
> `gh` or `glab` CLI is available and authenticated, run BOTH: 1) `gh release list
> --limit 30` to check for release-based deploys. 2) For workflow-based deploys, first
> list workflows with `ls .github/workflows/ | grep -i deploy` to find deploy workflow
> filenames, then run `gh run list --workflow={exact-name}.yml --limit 30` for each
> (gh CLI does not support wildcards in --workflow). Alternatively, run
> `gh run list --limit 50` and filter for deploy-related workflows. Some orgs use
> releases, others use workflow runs - either is valid. Count successful deploys from
> both sources combined and verify multiple deploys per week minimum. Also verify
> deployment automation (auto-deploy on merge, CD pipelines). This is about culture of
> frequent shipping. Skip if `gh`/`glab` CLI is not available or not authenticated.

### automated_pr_review — Automated PR Review Generation
scope: repository。自动 PR review：CodeRabbit、Codium、Factory Droid review、GitHub CODEOWNERS
机器人评论。`gh pr list` 查 review 机器人痕迹。

### agentic_development — Agentic Development
scope: repository。AI agent 已进入开发工作流。原版口径（原文）：

> Agentic development detected – Look for evidence that AI agents are part of the
> development workflow. Check: 1) Git history for agent co-authorship:
> `git log --format='%an|||%ae|||%s|||%b' -100` and search for AI coding agent
> identifiers in author/co-author fields. Common patterns include AI tool names
> (often with '[bot]' suffix) in author fields or 'Co-authored-by' headers (e.g.,
> 'factory-droid[bot]', 'Claude Code'). Note: dependency bots like dependabot or
> renovate do not count. Also note that these examples are non-exhaustive - look for
> any AI coding agent identifiers. Optional: if `gh` CLI available, use
> `gh pr list --json commits` for more reliable co-author detection. 2) CI/CD
> workflows that invoke agents for reviews, code generation, or documentation.
> 3) Scripts/Makefiles with agent CLI commands (e.g., droid exec). 4) Agent
> configuration directories, skills, or hooks (e.g., .factory/droids/,
> .factory/skills/, .factory/hooks/). Need at least one strong evidence point showing
> agents actively participate in development.

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
scope: application。DRY 检测：jscpd、PMD CPD、simian 配置。

### n_plus_one_detection — N+1 Query Detection [Skippable]
scope: application。N+1 检测：bullet/django-silk（Rails 的 bullet、Django nplusone）、
`includes` lint 规则。无 ORM 的 repo skip。

### large_file_detection — Large File Detection
scope: repository。超大文件被检测/阻止：pre-commit 检查、`.gitattributes` 大小限制、CI
文件大小 guard（一般 > 1MB 的源文件视为 fail 迹象，除非有工具豁免）。

### code_modularization — Code Modularization Enforcement
scope: application。模块边界被工具强制：Nx module boundaries、eslint-plugin-boundaries、
ArchUnit、import-linter。

## Task Discovery

Task Discovery 在原版中是一个 category（"Infrastructure for agents to find and scope work
autonomously"），不是 criterion；本类别含下列信号。

### issue_templates — Issue Templates
scope: repository。`.github/ISSUE_TEMPLATE/` 结构化模板存在。

### pr_templates — PR Templates
scope: repository。`.github/pull_request_template.md` 存在。

### issue_labeling_system — Issue Labeling System
scope: repository。一致的 priority/type/area 标签体系（`.github/labels.yml` 或仓库标签约定
文档）。

### backlog_health — Backlog Health [Skippable]
scope: repository。issue 标题清晰且有近期活跃。无远端访问权限时 skip。

### error_to_insight_pipeline — Error to Insight Pipeline
scope: application。错误从跟踪系统流向可执行 issue：Sentry→GitHub issue 集成、自动工单创建。

## Product & Experimentation

### product_analytics_instrumentation — Product Analytics Instrumentation [Skippable]
scope: application。Mixpanel/Amplitude/PostHog 埋点接入。非面向用户的产品（纯库、CLI 工具集）
skip。

### feature_flag_infrastructure — Feature Flag Infrastructure
scope: repository。LaunchDarkly、Statsig、Unleash、GrowthBook 或自建 flag 系统配置。

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
