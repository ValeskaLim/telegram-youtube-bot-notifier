# Telegram YouTube Bot Notifier 🤖

Smart, lightweight notifier that pings you on Telegram the moment a monitored
Hololive VTuber goes live on YouTube.

## ✨ How it works

The bot polls the [Holodex](https://holodex.net) API, which is purpose-built for
VTuber stream tracking. A **single request returns the live/upcoming state of
every monitored channel at once**, so the bot can check often (every ~2 minutes
by default) for near-instant alerts while using almost no quota.

If a `HOLODEX_API_KEY` isn't configured, it falls back to the YouTube Data API
(one search per channel, 100 quota units each).

### Key features

- **One API call per check** for all channels (vs. one expensive call *per channel*)
- **Fast polling** (~2 min) so alerts arrive promptly, not hours later
- **De-duplicated alerts** — keyed by video ID, so an ongoing stream is never
  re-announced, but a brand-new stream always is
- **No restart spam** — already-live streams are silently synced on startup
  (toggle with `NOTIFY_ON_STARTUP`)
- **Resilient** — a failed check keeps the previous state instead of marking
  everyone offline; automatic retries with backoff; optional YouTube fallback

## 📦 Installation

```bash
git clone https://github.com/ValeskaLim/telegram-youtube-bot-notifier.git
cd telegram-youtube-bot-notifier

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file (see `.env.example`):

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
CHAT_ID=your_telegram_chat_id
HOLODEX_API_KEY=your_holodex_api_key
# YOUTUBE_API_KEY=        # optional fallback
# CHECK_INTERVAL_SECONDS=120
# NOTIFY_ON_STARTUP=false
```

Get a free Holodex key: sign in at <https://holodex.net> → Account → create an API key.

Run it:

```bash
python main.py
```

## 🤖 Telegram commands

| Command | Description |
|---------|-------------|
| `/test` | Quick health check and status |
| `/status` | Detailed status, current live channels, daily call count |
| `/check_livestream [name]` | Run a fresh check now (optional name filter for display) |
| `/force_check` | Force a fresh check of all channels |

## ⚙️ Configuration

Set via environment variables (see `.env.example`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `CHECK_INTERVAL_SECONDS` | `120` | Seconds between checks |
| `HTTP_TIMEOUT_SECONDS` | `15` | Per-request timeout |
| `NOTIFY_ON_STARTUP` | `false` | Alert for already-live streams on (re)start |

The monitored channels live in the `CHANNELS` list in `main.py`.

## 📊 Quota notes

- **Holodex:** one cached `/users/live` request per check. At 120s that's ~720
  calls/day — comfortably within the free tier.
- **YouTube fallback:** `search.list` costs **100 units** of the 10,000/day quota,
  i.e. only ~100 calls/day total. The bot tracks units in `/status`; if you rely
  on YouTube alone, raise `CHECK_INTERVAL_SECONDS` accordingly.

> Note: Holodex sits behind Cloudflare and rejects the default Python user-agent,
> so the bot sends a custom `User-Agent` header. Keep that if you tweak requests.

## 🖥️ VPS deployment

See [DEPLOYMENT.md](DEPLOYMENT.md). In short: run as a `systemd` service with
`Restart=always`, keep the `.env` on the server, and tail logs with
`sudo journalctl -u youtube-notifier -f`.

## 📝 Monitored channels

Hololive English (Myth, Promise, Advent, Justice). Edit the `CHANNELS` list in
`main.py` to customize.

## 📄 License

MIT — see [LICENSE](LICENSE).
