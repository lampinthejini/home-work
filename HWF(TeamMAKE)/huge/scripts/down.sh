#!/usr/bin/env sh
# app → ai → infra 순서로 내린다 (볼륨은 지우지 않는다).  사용: sh scripts/down.sh [app|ai|infra]
cd "$(dirname "$0")/.."
for part in ${1:-app ai infra}; do docker compose -f "compose.$part.yml" down; done
