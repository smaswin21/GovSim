#!/usr/bin/env bash
# Initialize the PathFinder submodule and apply the local patches
# (Anthropic fixes, Ollama backend).
set -euo pipefail
cd "$(dirname "$0")/.."
git submodule update --init
for NAME in anthropic ollama; do
  PATCH="$(pwd)/patches/pathfinder-${NAME}.patch"
  if git -C pathfinder apply --check -R "$PATCH" 2>/dev/null; then
    echo "pathfinder-${NAME} patch already applied"
  else
    git -C pathfinder apply "$PATCH"
    echo "pathfinder-${NAME} patch applied"
  fi
done
