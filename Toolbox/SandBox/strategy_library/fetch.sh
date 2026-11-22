#!/bin/zsh
# Fetch library items into a dated, git-ignored snapshot; append to its manifest.
# Usage: zsh fetch.sh <dest_dir> <sources.tsv>
#   e.g. zsh Toolbox/SandBox/strategy_library/fetch.sh data/raw/library/<today> \
#          Toolbox/SandBox/strategy_library/still_to_fetch.tsv
# A later pass goes into a new folder dated the day it runs, never into an older snapshot.
# Nothing in the snapshot is overwritten or deleted: each attempt downloads to a temporary
# file, and only a complete download is moved into place, where no file of that name exists.
set -u
dest=$1; list=$2
mkdir -p "$dest"
manifest="$dest/manifest.tsv"
[[ -f "$manifest" ]] || print -r -- $'file\tshelf\ttitle\tlicence\turl\tbytes\tsha256\tstatus' > "$manifest"
tmp=$(mktemp -d)
while IFS=$'\t' read -r file shelf title licence url; do
  [[ -z "$file" || "$file" == \#* ]] && continue
  mkdir -p "$dest/$shelf"
  out="$dest/$shelf/$file"
  part="$tmp/$file"
  if [[ -e "$out" ]]; then
    st=exists; bytes=$(stat -f %z "$out"); sha=$(shasum -a 256 "$out" | cut -d' ' -f1)
  elif curl -sSL -f --max-time 180 -A "Mozilla/5.0 (research library fetch)" -o "$part" "$url"; then
    mv "$part" "$out"
    bytes=$(stat -f %z "$out"); sha=$(shasum -a 256 "$out" | cut -d' ' -f1); st=ok
  else
    bytes=0; sha=-; st=failed
  fi
  print -r -- "$shelf/$file"$'\t'"$shelf"$'\t'"$title"$'\t'"$licence"$'\t'"$url"$'\t'"$bytes"$'\t'"$sha"$'\t'"$st" >> "$manifest"
  print -r -- "$st $bytes $shelf/$file"
  sleep 4
done < "$list"
