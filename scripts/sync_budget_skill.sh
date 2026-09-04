#!/bin/bash
# Sync budget-familiare-workflow skill to GitHub
# Runs every 30 minutes via cron job

SKILL_DIR="/opt/data/profiles/budgetingagent/skills/budget-familiare-workflow"

cd "$SKILL_DIR" || exit 0

# Check if there are changes to commit
if git diff --quiet && git diff --cached --quiet; then
  # No changes
  exit 0
fi

# Stage all changes
git add -A

# Commit with timestamp
TIMESTAMP=$(date '+%Y-%m-%d %H:%M')
git commit -m "auto-sync: $TIMESTAMP"

# Push to GitHub
git push origin main

echo "Pushed skill changes to GitHub at $TIMESTAMP"
