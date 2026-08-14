#!/usr/bin/env bash
#
# Publish a built frontend zip to the docroot, without a window where the site is
# broken.
#
#   ./deploy-frontend.sh ~/seo-frontend.zip
#   ./deploy-frontend.sh ~/seo-frontend.zip ~/public_html
#   ./deploy-frontend.sh --rollback
#
# The manual sequence this replaces was:
#
#     cd $WEB && rm -rf assets index.html
#     unzip -o ~/seo-frontend.zip -d $WEB
#
# which took the site down for twenty minutes: the delete succeeded, the unzip
# failed on a zip that wasn't there, and Apache served a directory listing of what
# was left. The order is the bug — it destroys the working copy before confirming
# the replacement exists.
#
# Here nothing is removed until a complete new tree has been staged and checked.
# The swap is two renames, and the previous release is kept for one-command
# rollback.

set -euo pipefail

ZIP="${1:-}"
WEB="${2:-$HOME/public_html}"
STAGE="$WEB.staging.$$"
PREV="$WEB.previous"

die() { printf '\nerror: %s\n' "$1" >&2; exit 1; }
step() { printf '  %s\n' "$1"; }

# Any refusal below exits straight out, which otherwise left the half-built
# staging tree next to the docroot — a directory per failed attempt, each a full
# copy of the site. On success $STAGE has already been renamed, so this is a
# no-op. Set before the first mkdir so no exit path can skip it.
cleanup() { [[ -n "${STAGE:-}" ]] && rm -rf "$STAGE"; }
trap cleanup EXIT

# ── rollback ──────────────────────────────────────────────────────────
if [[ "$ZIP" == "--rollback" ]]; then
  WEB="${2:-$HOME/public_html}"
  PREV="$WEB.previous"
  [[ -d "$PREV" ]] || die "no previous release at $PREV"
  SWAP="$WEB.rollingback.$$"
  mv "$WEB" "$SWAP"
  mv "$PREV" "$WEB"
  mv "$SWAP" "$PREV"
  echo "Rolled back. The release you just removed is now at $PREV."
  exit 0
fi

[[ -n "$ZIP" ]] || die "usage: $0 <zip> [docroot]   (or --rollback)"
[[ -f "$ZIP" ]] || die "$ZIP does not exist. Upload it first — this is the failure that caused the outage."
command -v unzip >/dev/null || die "unzip is not installed. Use cPanel File Manager's Extract instead."
[[ -d "$WEB" ]] || die "$WEB is not a directory. Pass the docroot as the second argument."

echo "Deploying $ZIP -> $WEB"

# ── 1. the archive is intact and is what we think it is ───────────────
step "checking the archive"
unzip -tqq "$ZIP" >/dev/null 2>&1 || die "$ZIP is corrupt or truncated (unzip -t failed)."
unzip -l "$ZIP" | grep -q ' index.html$' \
  || die "$ZIP has no top-level index.html — wrong archive, or it was zipped with a wrapping folder."
unzip -l "$ZIP" | grep -qE ' assets/index-[A-Za-z0-9_-]+\.js$' \
  || die "$ZIP has no assets/index-*.js — this doesn't look like a Vite build."

# ── 2. stage a complete tree before touching the live one ─────────────
step "staging"
rm -rf "$STAGE"
mkdir -p "$STAGE"
# Anything the build doesn't ship but the site needs (uploads, .htaccess, files
# put there by hand) is carried across. rsync isn't guaranteed on shared hosting,
# so this is cp with a glob that includes dotfiles.
if compgen -G "$WEB"/* >/dev/null 2>&1 || compgen -G "$WEB"/.[!.]* >/dev/null 2>&1; then
  cp -a "$WEB"/. "$STAGE"/ 2>/dev/null || true
fi
# Fingerprinted filenames mean stale chunks accumulate forever and a cached
# index.html can keep loading them. Clear the build's own output, keep the rest.
rm -rf "$STAGE/assets" "$STAGE/index.html"
unzip -oq "$ZIP" -d "$STAGE" || die "unzip into the staging directory failed — the live site is untouched."

# ── 3. the staged tree is actually servable ───────────────────────────
step "verifying the staged tree"
[[ -f "$STAGE/index.html" ]] || die "staged tree has no index.html — refusing to publish."
ENTRY="$(grep -oE 'assets/index-[A-Za-z0-9_-]+\.js' "$STAGE/index.html" | head -1 || true)"
[[ -n "$ENTRY" ]] || die "index.html references no entry bundle — refusing to publish."
[[ -f "$STAGE/$ENTRY" ]] || die "index.html points at $ENTRY, which is not in the archive — refusing to publish."

# Every chunk index.html asks for must exist, or the app white-screens on load
# with a bare 404 in the console.
MISSING=0
while read -r ref; do
  [[ -z "$ref" ]] && continue
  [[ -f "$STAGE/$ref" ]] || { printf '    missing: %s\n' "$ref"; MISSING=1; }
done < <(grep -oE 'assets/[A-Za-z0-9_.-]+\.(js|css)' "$STAGE/index.html" | sort -u)
[[ "$MISSING" -eq 0 ]] || die "staged tree is incomplete — refusing to publish."

step "setting permissions"
find "$STAGE" -type d -exec chmod 0755 {} \;
find "$STAGE" -type f -exec chmod 0644 {} \;

# ── 4. swap ───────────────────────────────────────────────────────────
# Two renames within one filesystem. The gap where the docroot doesn't exist is
# microseconds, versus the minutes the old sequence left it empty.
step "swapping into place"
rm -rf "$PREV"
mv "$WEB" "$PREV"
mv "$STAGE" "$WEB"

echo
echo "Deployed. Entry bundle: $ENTRY"
echo "Previous release kept at $PREV — undo with:"
echo "    $0 --rollback $WEB"
echo
echo "Hard-reload the browser (Ctrl+Shift+R): index.html is not fingerprinted and"
echo "a cached copy will keep requesting the old chunk filenames."
