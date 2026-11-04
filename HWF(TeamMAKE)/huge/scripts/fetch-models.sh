#!/usr/bin/env sh
# stt·tts·embed·ocr 모델을 볼륨에 내려받고, 끝나면 밖으로 나가는 망을 다시 끊는다.  scripts/up.sh infra 다음에 돌린다
set -e
cd "$(dirname "$0")/.."
MODEL_BOXES="stt embed tts ocr"
MSYS_NO_PATHCONV=1 docker compose -f compose.ai.yml -f compose.ai.fetch.yml up -d --build --wait $MODEL_BOXES
MSYS_NO_PATHCONV=1 docker compose -f compose.ai.yml up -d $MODEL_BOXES
