#!/bin/bash
# One-time Mac setup for the WalkingPad tracker. Safe to run again.
set -e
DIR="$HOME/walkingpad-tracker"
REPO="NickNotAvailable/walkingpad-tracker"
LABEL="ge.walkingpad.tracker"

echo "==> Downloading the tracker into $DIR"
mkdir -p "$DIR"
curl -fsSL "https://codeload.github.com/$REPO/tar.gz/refs/heads/main" \
  | tar -xz -C "$DIR" --strip-components=1 --exclude='state.json'

echo "==> Installing Python tools (one time, takes a few minutes)"
if ! command -v uv >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/uv" ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
cd "$DIR"
[ -x .venv/bin/python ] || UV_VENV_CLEAR=1 "$UV" venv --quiet --clear --python 3.12 .venv
"$UV" pip install --quiet --python .venv/bin/python -r requirements.txt
[ -d "/Applications/Google Chrome.app" ] || .venv/bin/python -m playwright install chromium

if [ ! -f .env ]; then
  echo
  read -r -p "Paste your Telegram bot token: " TOKEN < /dev/tty
  read -r -p "Paste your Telegram chat ID: " CHAT < /dev/tty
  printf 'TELEGRAM_BOT_TOKEN=%s\nTELEGRAM_CHAT_ID=%s\n' "$TOKEN" "$CHAT" > .env
  chmod 600 .env
fi

cat > run-home.sh <<RUN
#!/bin/bash
cd "$DIR" && TRACKER_WHERE=home .venv/bin/python tracker.py "\$@" >> tracker.log 2>&1
RUN
chmod +x run-home.sh

echo "==> Scheduling a daily check (10:00, or when the Mac wakes / you log in)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$DIR/run-home.sh</string></array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>0</integer></dict>
  <key>RunAtLoad</key><true/>
</dict></plist>
PL
launchctl unload "$PLIST" 2>/dev/null || true

echo "==> Sending a test Telegram message"
TRACKER_WHERE=home .venv/bin/python tracker.py test-telegram
echo "==> Running the first check now (a Chrome window will open briefly)"
./run-home.sh force || true
tail -n 12 tracker.log
launchctl load "$PLIST"
echo
echo "All set. Your Mac will check MyMarket, Zoommer, Alta and ee.ge once a day."
