#!/usr/bin/env bash
source "$(dirname "$0")/_common.sh"
LOG="logs/$(date +%F)-crawl.tee.log"
python -m ads_insight_keke.web_crawler 2>&1 | tee -a "$LOG"
exit ${PIPESTATUS[0]}
