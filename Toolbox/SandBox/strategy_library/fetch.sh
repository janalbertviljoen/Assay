#!/bin/zsh
# Fetch the strategy library into a dated, git-ignored snapshot; record a manifest.
# Usage: fetch.sh <dest_dir> <sources.tsv>
# e.g. zsh Toolbox/SandBox/strategy_library/fetch.sh data/raw/library/2026-11-22 \
#        Toolbox/SandBox/strategy_library/still_to_fetch.tsv
set -u
dest=$1; list=$2
mkdir -p "$dest"
manifest="$dest/manifest.tsv"
[[ -f "$manifest" ]] || print -r -- $'file\tshelf\ttitle\tlicence\turl\tbytes\tsha256\tstatus' > "$manifest"
while IFS=$'\t' read -r file shelf title licence url; do
  [[ -z "$file" || "$file" == \#* ]] && continue
  mkdir -p "$dest/$shelf"
  out="$dest/$shelf/$file"
  if curl -sSL -f --max-time 180 -A "Mozilla/5.0 (research library fetch)" -o "$out" "$url"; then
    bytes=$(stat -f %z "$out"); sha=$(shasum -a 256 "$out" | cut -d' ' -f1); st=ok
  else
    rm -f "$out"; bytes=0; sha=-; st=failed
  fi
  print -r -- "$shelf/$file"$'\t'"$shelf"$'\t'"$title"$'\t'"$licence"$'\t'"$url"$'\t'"$bytes"$'\t'"$sha"$'\t'"$st" >> "$manifest"
  print -r -- "$st $bytes $shelf/$file"
  sleep 4
done < "$list"
