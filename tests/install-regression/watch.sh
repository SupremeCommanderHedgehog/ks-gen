#!/usr/bin/env bash
set -uo pipefail
BUILD="$HOME/.cache/ks-gen-install-regression"
LOG="$BUILD/serial.log"
until [[ -f "$LOG" ]]; do sleep 5; done
echo "serial.log appeared at $(date -Is)"
tail -n 0 -F "$LOG" 2>&1 \
  | grep -E --line-buffered 'Starting installer|Running pre-installation|Found storage|Setting up disk|ignoredisk|clearpart|partitioning|Bootloader installation|Running %post|Performing post-installation|Pane is dead|Installation complete|Traceback|anaconda.*ERROR|kernel panic|emergency mode|reboot --eject|install-regression PASS|FAIL:|ok:'
