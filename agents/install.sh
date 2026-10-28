#!/usr/bin/env bash
# Install all skills from this repo into ~/.agents/skills
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$repo_root/skills"
dst="$HOME/.agents/skills"

mkdir -p "$dst"
cp -r "$src"/. "$dst"/

echo "Installed skills:"
for d in "$src"/*/; do
  [ -d "$d" ] || continue
  echo "  $(basename "$d") -> $dst/$(basename "$d")"
done
