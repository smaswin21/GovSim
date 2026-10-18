#!/usr/bin/env bash
# Initialize the PathFinder submodule and apply the local Anthropic fixes.
set -euo pipefail
cd "$(dirname "$0")/.."
git submodule update --init
PATCH="$(pwd)/patches/pathfinder-anthropic.patch"
if git -C pathfinder apply --check -R "$PATCH" 2>/dev/null; then
  echo "pathfinder patch already applied"
else
  git -C pathfinder apply "$PATCH"
  echo "pathfinder patch applied"
fi
