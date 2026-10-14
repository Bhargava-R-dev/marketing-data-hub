#!/bin/bash
# Wrap "Marketing Data Hub.app" in a drag-to-Applications disk image.
# Usage: build_dmg.sh <path-to-.app> <output.dmg>
set -euo pipefail
APP="$1"
OUT="$2"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
rm -f "$OUT"
hdiutil create -volname "Marketing Data Hub" -srcfolder "$STAGE" -fs HFS+ -format UDZO -ov "$OUT"
echo "built $OUT"
