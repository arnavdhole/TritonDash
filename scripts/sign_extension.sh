#!/usr/bin/env bash
# Signs the extension with Mozilla so Firefox and Zen keep it after a restart.
# A temporary add-on from about:debugging is removed every time the browser quits.
#
# One-time setup:
#   1. Sign in at https://addons.mozilla.org/developers/ with a free Mozilla account.
#   2. Open Tools > Manage API Keys and create credentials.
#   3. Export them in this terminal, never in a file in this project:
#        export AMO_JWT_ISSUER="user:12345:67"
#        export AMO_JWT_SECRET="the long secret"
#
# Each run needs a new "version" in extension/manifest.json, because Mozilla refuses
# to sign the same version twice. The signed file lands in dist/.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

: "${AMO_JWT_ISSUER:?Set AMO_JWT_ISSUER first. See the comments at the top of this script.}"
: "${AMO_JWT_SECRET:?Set AMO_JWT_SECRET first. See the comments at the top of this script.}"

mkdir -p dist
npx --yes web-ext sign \
  --source-dir extension \
  --artifacts-dir dist \
  --channel unlisted \
  --ignore-files "fixtures/**" \
  --api-key "$AMO_JWT_ISSUER" \
  --api-secret "$AMO_JWT_SECRET"

echo
echo "Signed. In Zen or Firefox open about:addons, click the gear icon, choose"
echo "'Install Add-on From File', and pick the .xpi in dist/."
echo "Then turn on the site toggles on the extension's Permissions tab."
