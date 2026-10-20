#!/bin/bash
# Open a batch when its episode airs, run on the Mac:  bash "/Volumes/Dev/AI Talks/public/publish.sh" b0007
set -e
B="$1"
if [ -z "$B" ]; then echo "usage: bash publish.sh b0007"; exit 1; fi
cd "$(dirname "$0")"
git pull -q
python3 runner/unseal.py "$B" --key "../.seal/seal.key"
git add "batches/$B/open"
git commit -q -m "Open batch $B"
git push -q
echo "Batch $B is open."
