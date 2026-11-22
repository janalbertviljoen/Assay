#!/bin/bash
# Fetch fund fact sheets into a dated, git-ignored snapshot; record a manifest. Deletes
# nothing: each attempt goes to its own temporary file, and a verified PDF is moved in.
# Usage: bash fetch_fund_sheets.sh <dest_dir> <fund_sheets.tsv> <tmp_dir>
# The fund list names an owner's holdings, so it and the sheets live in the owner's
# private workspace, never in this repository; e.g. from the repository root:
#   bash Toolbox/SandBox/strategy_library/fetch_fund_sheets.sh \
#     ../Personal/Finances/fund_sheets/<date> ../Personal/Finances/fund_sheets/fund_sheets.tsv "$TMPDIR/fs"
# Each line of the list: ticker, fund name, candidate URLs separated by "|", tab-separated.
set -u
dest="$1"
list="$2"
tmp="$3"
mkdir -p "$dest" "$tmp"
printf 'ticker\tfund\turl\tbytes\tsha256\tstatus\n' > "$dest/manifest.tsv"
grep -v '^#' "$list" | while IFS=$'\t' read -r ticker name urls; do
  status=failed
  used=-
  i=0
  for url in $(echo "$urls" | tr '|' ' '); do
    i=$((i + 1))
    part="$tmp/$ticker.$i"
    if curl -sSL -f --max-time 90 -A "Mozilla/5.0" -o "$part" "$url" 2>/dev/null \
      && head -c 4 "$part" | grep -q '%PDF'; then
      mv "$part" "$dest/$ticker.pdf"
      status=ok
      used="$url"
      break
    fi
  done
  if [ "$status" = ok ]; then
    bytes=$(stat -f %z "$dest/$ticker.pdf")
    sha=$(shasum -a 256 "$dest/$ticker.pdf" | cut -d' ' -f1)
  else
    bytes=0
    sha=-
  fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$ticker" "$name" "$used" "$bytes" "$sha" "$status" \
    >> "$dest/manifest.tsv"
  echo "$status $ticker $bytes $used"
  sleep 1
done
