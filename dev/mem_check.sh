#!/usr/bin/env bash
echo "---===== memcheck  =====----"
PID=$(pgrep -n -f 'traybeat')

echo "=== Memory ==="
grep -E '^(VmRSS|VmSize|RssAnon|RssFile|RssShmem):' "/proc/$PID/status"

echo
echo "=== Detailed memory ==="
cat "/proc/$PID/smaps_rollup" | grep -E '^(Rss|Pss|Private|Shared):'