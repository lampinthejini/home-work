#!/usr/bin/env sh
# 공유 네트워크를 만들고 infra → ai → app 순서로 띄운다.  사용: sh scripts/up.sh [infra|ai|app]
set -e
cd "$(dirname "$0")/.."
docker network inspect huge-front >/dev/null 2>&1 || docker network create huge-front
docker network inspect huge-internal >/dev/null 2>&1 || docker network create --internal huge-internal
for part in ${1:-infra ai app}; do
  MSYS_NO_PATHCONV=1 docker compose -f "compose.$part.yml" up -d --build
done
