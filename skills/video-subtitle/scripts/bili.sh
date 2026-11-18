#!/usr/bin/env bash
# bili.sh — 已弃用的兼容入口
# 实现已迁移到 scripts/bilibili-legacy.sh；新任务请用 scripts/video_subtitle.py。
set -euo pipefail
exec "$(dirname "$0")/bilibili-legacy.sh" "$@"