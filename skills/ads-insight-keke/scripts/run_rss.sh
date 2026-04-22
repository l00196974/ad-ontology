#!/usr/bin/env bash
source "$(dirname "$0")/_common.sh"
LOG="logs/$(date +%F)-rss.tee.log"
python -m ads_insight_keke.rss_collector 2>&1 | tee -a "$LOG"
exit ${PIPESTATUS[0]}
