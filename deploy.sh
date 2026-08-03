#!/usr/bin/env bash
#
# Deploy RankBoard on the production server.
#
#   ssh in, then:  bash /home/infyappseodashbo/rankboard/deploy.sh
#
# Why this script exists
# ---------------------
# `git pull` alone can NEVER update the front end. The browser loads compiled
# JavaScript from client/dist/, and dist/ is in .gitignore — it is not in the
# repo. On top of that, the web root is ~/public_html, not client/dist, so the
# build has to be COPIED into place afterwards. Three separate steps, and
# skipping any one of them leaves the old site live while the source looks
# correct.
#
set -euo pipefail

REPO="/home/infyappseodashbo/rankboard"
WEB_ROOT="/home/infyappseodashbo/public_html"

# How to restart the API. Read from the environment so you never have to edit
# this tracked file (editing it makes the working tree dirty on every deploy).
# Put your command in ~/.rankboard-deploy.env, e.g.:
#
#   RESTART_CMD="sudo systemctl restart rankboard"     # systemd
#   RESTART_CMD="pm2 restart rankboard-api"            # pm2
#   RESTART_CMD="touch $HOME/rankboard/server-python/tmp/restart.txt"  # passenger
#
[ -f "$HOME/.rankboard-deploy.env" ] && . "$HOME/.rankboard-deploy.env"
RESTART_CMD="${RESTART_CMD:-}"

step() { printf "\n\033[1m==> %s\033[0m\n" "$1"; }

[ -d "$REPO/.git" ]   || { echo "No git repo at $REPO"; exit 1; }
[ -d "$WEB_ROOT" ]    || { echo "No web root at $WEB_ROOT"; exit 1; }

step "Pulling latest code"
cd "$REPO"
# Only tracked, modified files matter — untracked stuff sitting in the working
# directory is none of this script's business, and refusing to deploy over it was
# just obstructive. If a local edit really does conflict, git pull says so.
DIRTY="$(git diff --name-only; git diff --cached --name-only)"
if [ -n "$DIRTY" ]; then
    echo "Note: locally modified tracked files (the pull will fail if they conflict):"
    printf '  %s\n' $(echo "$DIRTY" | sort -u)
fi
if ! git pull --ff-only; then
    echo
    echo "Pull failed. Either a local edit conflicts (git status), or the branch"
    echo "has diverged and needs a merge. Nothing was built or published."
    exit 1
fi
git log -1 --oneline

step "Installing front-end dependencies"
cd "$REPO/client"
npm install --no-audit --no-fund

step "Building front end"
npm run build
[ -f dist/index.html ] || { echo "Build produced no dist/index.html"; exit 1; }

step "Publishing build to $WEB_ROOT"
# Only ever touch assets/ and the build's own files. Never delete the whole
# directory — .htaccess (SPA routing + /api proxy), .user.ini and .well-known/
# (SSL renewal) live here and are NOT in the repo.
rm -rf "$WEB_ROOT/assets"
cp -r dist/. "$WEB_ROOT/"

step "Restarting the API"
if [ -n "$RESTART_CMD" ]; then
    eval "$RESTART_CMD"
    echo "Ran: $RESTART_CMD"
else
    echo "!! RESTART_CMD is not set in this script."
    echo "!! Restart the Python backend by hand, or schema migrations"
    echo "!! (ALTER TABLE in db.py) will not run."
fi

step "Verifying"
SERVED_JS=$(grep -o 'assets/index-[A-Za-z0-9_-]*\.js' "$WEB_ROOT/index.html" || true)
BUILT_JS=$(grep -o 'assets/index-[A-Za-z0-9_-]*\.js' dist/index.html || true)
echo "built  : ${BUILT_JS:-none}"
echo "served : ${SERVED_JS:-none}"
if [ -n "$SERVED_JS" ] && [ "$SERVED_JS" = "$BUILT_JS" ]; then
    echo "OK — web root matches the build."
else
    echo "MISMATCH — the copy did not land. Check permissions on $WEB_ROOT."
    exit 1
fi

printf "\n\033[1mDone.\033[0m Hard-reload the browser (DevTools open, 'Disable cache' ticked).\n"
