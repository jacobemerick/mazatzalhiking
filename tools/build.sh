#!/usr/bin/env bash
# The whole build, in order. Cloudflare Workers Builds runs this as its build command
# and then deploys public/; run it locally before `wrangler dev`.
#
#   1. sync_trails   --check   every trail has a markdown file and every leg a section
#   2. build_site              validate the graph and the notes; write static/data/ + data/
#   3. hugo                    render content/ + layouts/ + static/ into public/
#   4. check_launch            the builder's noindex, robots, sitemap and CTA match builderPublic
#
# Any step failing fails the deploy. Nothing here is authored and nothing it writes
# is committed (see .gitignore).
set -euo pipefail
cd "$(dirname "$0")/.."

python3 tools/sync_trails.py --check
python3 tools/build_site.py
hugo --gc --quiet
node tools/check_launch.mjs
echo "built public/ ($(find public -type f | wc -l | tr -d ' ') files)"
