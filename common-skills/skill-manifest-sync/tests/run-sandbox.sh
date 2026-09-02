#!/usr/bin/env bash
# 宿主侧入口：构建沙箱镜像并运行 skill-manifest-sync 的 Docker 测试。
# 仓库以只读方式挂进容器，测试在容器内拷贝（/work/repo）上执行，不污染宿主仓库。
set -euo pipefail
cd "$(dirname "$0")"

docker build -q -t skill-manifest-sync-sandbox . >/dev/null
docker run --rm -i \
  -v "$(cd ../../.. && pwd):/src/mason-skills:ro" \
  skill-manifest-sync-sandbox \
  bash -c 'cp -r /src/mason-skills /work/repo && bash /work/repo/common-skills/skill-manifest-sync/tests/sandbox-tests.sh'