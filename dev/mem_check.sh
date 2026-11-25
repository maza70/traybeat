#!/usr/bin/env bash
SCRIPT_NAME=$(basename "${BASH_SOURCE[0]}")
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

print_header "---===== memcheck  =====----"
PID=$(pgrep -n -f 'traybeat')


if [[ -z "$PID" ]]; then
    print_error "Process traybeat not found!"
    exit 1
fi

print_header "=== Process ==="
print_info "PID: $PID"

print_error "=== Memory ==="
grep -E '^(VmRSS|VmSize|RssAnon|RssFile|RssShmem):' "/proc/$PID/status"

print_info "=== Detailed memory ==="
cat "/proc/$PID/smaps_rollup" | grep -E '^(Rss|Pss|Private|Shared):'