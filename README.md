# WalkingPad Z1 / C2 tracker (Georgia)

Checks Georgian marketplaces and shops once a day on GitHub Actions and sends
Telegram alerts for new listings, restocks and price drops of the Xiaomi
WalkingPad Z1 and C2.

- **Sites:** edit `sites.py` to add/remove sites or fix a search address.
- **Schedule:** every day at 09:17 Tbilisi time (`.github/workflows/tracker.yml`).
- **Memory:** `state.json` stores what was already sent, so nothing is sent twice.
- **Order:** used listings in Tbilisi first, then other used, then new; cheapest first.
- **Honesty:** only listings actually found on a page are reported. Unknown price,
  condition or location is shown as "not shown"/"not stated", never guessed.
- **Failures:** sites that can't be loaded are listed in a Telegram warning.

## Run manually
GitHub → **Actions** → **WalkingPad tracker** → **Run workflow**, then pick:
- `run` – normal check
- `test-telegram` – sends a test message
- `find-chat-id` – shows your Telegram chat ID in the log

## Secrets needed
Settings → Secrets and variables → Actions:
- `TELEGRAM_BOT_TOKEN` – from @BotFather
- `TELEGRAM_CHAT_ID` – from the `find-chat-id` run
