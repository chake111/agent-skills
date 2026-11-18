#!/usr/bin/env bash
# Link the skills in this repository into an agent skills directory.
# Usage: ./scripts/install.sh [target-dir]   (default: ~/.agents/skills)

set -euo pipefail

target="${1:-$HOME/.agents/skills}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
skills_dir="$repo_root/skills"

if [ ! -d "$skills_dir" ]; then
    echo "skills directory not found: $skills_dir" >&2
    exit 1
fi

mkdir -p "$target"
echo "source: $skills_dir"
echo "target: $target"
echo

created=0
skipped=0

for source in "$skills_dir"/*/; do
    name="$(basename "$source")"
    source="${source%/}"
    link="$target/$name"

    if [ -e "$link" ] || [ -L "$link" ]; then
        echo "skip   $name (already exists)"
        skipped=$((skipped + 1))
        continue
    fi

    ln -s "$source" "$link"
    echo "link   $name -> $source"
    created=$((created + 1))
done

echo
echo "created: $created, skipped: $skipped"