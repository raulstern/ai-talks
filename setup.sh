#!/bin/bash
# One-time setup, run on the Mac:  bash "/Volumes/Dev/AI Talks/public/setup.sh" <org-name>
# Creates the public repo <org-name>/ai-talks, pushes this folder to it, and stores the API key as a secret.
set -e
ORG="$1"
if [ -z "$ORG" ]; then echo "usage: bash setup.sh <org-name>"; exit 1; fi
cd "$(dirname "$0")"
command -v gh >/dev/null || { echo "Install the GitHub CLI first:  brew install gh"; exit 1; }
gh auth status >/dev/null 2>&1 || gh auth login --web --git-protocol https --scopes workflow
# pushing .github/workflows needs the "workflow" permission
gh auth status 2>&1 | grep -q "'workflow'" || gh auth refresh -h github.com -s workflow
gh auth setup-git
sed -i '' "s#<owner>#$ORG#g" VERIFY.md
if [ ! -d .git ]; then
  git init -q -b main
  git config user.name >/dev/null || git config user.name "AI Talks"
  git config user.email >/dev/null || git config user.email "$ORG@users.noreply.github.com"
  git add -A
  git commit -q -m "AI Talks runner"
fi
gh repo create "$ORG/ai-talks" --public --source . --push --description "Two AIs talk, unscripted. Every conversation is signed."
echo
echo "Now paste the API key named github-runner (it won't show), then press Enter:"
gh secret set ANTHROPIC_API_KEY -R "$ORG/ai-talks"
pip3 install -q pyrage==1.4.0 anthropic==1.16.0 || true
echo
echo "Done: https://github.com/$ORG/ai-talks"
