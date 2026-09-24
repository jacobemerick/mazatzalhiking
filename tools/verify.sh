#!/usr/bin/env bash
# Checks over the built site that go beyond the build itself (#53). CI runs each as its
# own job against the public/ the build job made; this runs the same checks locally,
# after a fresh build, so a push is green before it is pushed.
#
#   tools/verify.sh              build, then every check
#   tools/verify.sh --no-build   check the public/ already there
set -euo pipefail
cd "$(dirname "$0")/.."

[[ "${1:-}" == "--no-build" ]] || tools/build.sh
node tools/check_links.mjs
node tools/check_builder.mjs   # these two drive headless Chrome ($CHROME, or the usual path)
node tools/check_routes.mjs
