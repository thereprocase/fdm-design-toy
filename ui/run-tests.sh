#!/usr/bin/env bash
# Run on a test worker; Playwright stays outside the project dependencies.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${FDM_PREVIEW_MESH:?Set FDM_PREVIEW_MESH to the matching body-mounted.stl}"
if [[ ! -f "$FDM_PREVIEW_MESH" ]]; then
  echo 'FDM_PREVIEW_MESH must name an existing STL file' >&2
  exit 2
fi
# Respect a system-browser override, otherwise use the installed Playwright browser.
export CHROMIUM_PATH="${CHROMIUM_PATH:-$(node -e 'process.stdout.write(require("playwright").chromium.executablePath())')}"
if [[ ! -x "$CHROMIUM_PATH" ]]; then
  echo 'Install the Playwright Chromium browser or set CHROMIUM_PATH' >&2
  exit 2
fi
# Discover new regressions automatically, without running browser scripts in Node's
# parallel test worker pool. The legacy mesh smoke test has a distinct filename.
export LC_ALL=C
shopt -s nullglob
unit_checks=()
for check in ui/*.test.cjs; do
  case "$check" in
    *.browser.test.cjs|ui/browser.test.cjs) ;;
    *) unit_checks+=("$check") ;;
  esac
done
browser_checks=(ui/*.browser.test.cjs ui/browser.test.cjs)
if (( ${#unit_checks[@]} == 0 || ${#browser_checks[@]} == 0 )); then
  echo 'Expected both Node and browser regression files' >&2
  exit 2
fi
printf 'Running %d Node test files and %d browser scripts (sequential browser runs)\n' "${#unit_checks[@]}" "${#browser_checks[@]}"
node --test "${unit_checks[@]}"
for check in "${browser_checks[@]}"; do
  printf 'Browser check: %s\n' "$check"
  node "$check"
done
