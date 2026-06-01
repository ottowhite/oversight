#!/usr/bin/env bash
# Install oversight cron jobs:
#   - daily sync at 7am
#   - daily digest email at 9am
#   - weekly PaCMAP projection refresh, Sunday 3am (heavy: ~30-60 min on
#     the full corpus, runs offpeak to avoid clashing with sync)
# Run with sudo.
set -euo pipefail
REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
USER_="${SUDO_USER:-$USER}"
UV_DIR="$(dirname "$(sudo -u "$USER_" bash -lc 'command -v uv')")"
sudo install -d -o "$USER_" "$REPO/data/logs"
sudo tee /etc/cron.d/oversight >/dev/null <<EOF
PATH=$UV_DIR:/usr/bin:/bin
0 7 * * * $USER_ cd $REPO && make oversight/sync    >> $REPO/data/logs/sync.log    2>&1
0 9 * * * $USER_ cd $REPO && make oversight/digest  >> $REPO/data/logs/digest.log  2>&1
0 3 * * 0 $USER_ cd $REPO && make oversight/projections >> $REPO/data/logs/projections.log 2>&1
EOF
sudo chmod 0644 /etc/cron.d/oversight
echo "Wrote /etc/cron.d/oversight."
