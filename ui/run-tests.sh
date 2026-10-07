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
node --test ui/plan.test.cjs ui/viewer.test.cjs ui/coupon-evidence.test.cjs ui/massing-review-model.test.cjs ui/evidence-bundle.test.cjs
for check in planning toolpath coupons spatial capabilities massing-review review-edit keep-outs proposal mechanics shell-review bundle; do
  node "ui/$check.browser.test.cjs"
done
node ui/browser.test.cjs
