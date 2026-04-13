# Telegram YouTube Bot Notifier 🤖

Smart, optimized YouTube livestream notifier for Telegram. Monitors VTuber channels and sends instant notifications when they go live.

## ✨ Features

- **Smart Caching** - Reduces API calls by caching channel states with intelligent TTL
- **Rate Limiting Protection** - Built-in delays and quota tracking to stay under YouTube API limits
- **Duplicate Notification Prevention** - Only notifies when channels newly go live (not repeated alerts)
- **Concurrent Checking** - Checks multiple channels efficiently with connection pooling
- **Live Stream Detection** - Automatically detects when streams end
- **Daily Quota Management** - Tracks API usage and stays under 10,000 daily limit

## 🚀 Optimization Improvements

### Before (Inefficient)
- ❌ Every check called YouTube API for ALL channels
- ❌ No caching - redundant API calls
- ❌ No state tracking - couldn't detect new vs. ongoing streams
- ❌ Wasted quota on channels just checked

### After (Optimized)
- ✅ Smart caching with 1-hour TTL (5-min for live channels)
- ✅ State tracking per channel (live/offline status)
- ✅ Only notifies on NEW live streams
- ✅ Daily quota tracking with 9,000 call soft limit
- ✅ Connection pooling with retry logic
- ✅ Rate limiting delays between checks

## 📦 Installation

1. Clone the repository:
```bash
git clone https://github.com/ValeskaLim/telegram-youtube-bot-notifier.git
cd telegram-youtube-bot-notifier
```

2. Create virtual environment and install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Create `.env` file with your credentials:
```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
YOUTUBE_API_KEY=your_youtube_api_key
CHAT_ID=your_telegram_chat_id
```

4. Run the bot:
```bash
python main.py
```

## 🤖 Telegram Commands

| Command | Description |
|---------|-------------|
| `/test` | Test bot connectivity and show status |
| `/status` | Detailed bot statistics and live channels |
| `/check_livestream [name]` | Manual check (optional: filter by channel name) |
| `/force_check` | Force fresh check of all channels (bypass cache) |

## 📊 Quota Management

YouTube Data API v3 has a daily quota of 10,000 units. Each search call costs ~100 units.

**Recommended Settings:**
- **Check Interval:** 3.5 hours (12,600 seconds) - default
- **Channels:** 10-15 channels
- **Daily API Calls:** ~100-200 (well under limit)

**Quota Calculation:**
```
15 channels × 4 checks/day × 100 units = 6,000 units/day
```

## 🔧 Configuration

Edit these constants in `main.py`:

```python
CHECK_INTERVAL_SECONDS = 12600  # Time between full checks (3.5 hours)
CHANNEL_CHECK_DELAY = 0.5       # Delay between channel checks (rate limiting)
CACHE_TTL_SECONDS = 3600        # Cache validity (1 hour)
```

## 🖥️ VPS Deployment

### Backup Existing Installation
```bash
# SSH into your VPS
ssh user@your-vps-ip

# Backup current installation
cd ~
tar -czf youtube-notifier-backup-$(date +%Y%m%d).tar.gz youtube-notifier/
```

### Deploy New Version
```bash
# Stop existing bot (if running as service)
sudo systemctl stop youtube-notifier

# Or kill running process
pkill -f "python.*main.py"

# Update code
cd ~/youtube-notifier
git pull origin main

# Install/update dependencies
pip install -r requirements.txt

# Restart bot
sudo systemctl start youtube-notifier
# Or run manually: python main.py
```

### Systemd Service (Recommended)
Create `/etc/systemd/system/youtube-notifier.service`:
```ini
[Unit]
Description=YouTube Telegram Notifier Bot
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/home/your-user/youtube-notifier
Environment=PATH=/home/your-user/youtube-notifier/venv/bin
ExecStart=/home/your-user/youtube-notifier/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable youtube-notifier
sudo systemctl daemon-reload
```

## 📝 Monitored Channels

Default: Hololive English VTubers
- Ninomae Ina'nis
- IRyS
- Raora Panthera
- Koseki Bijou
- Hakos Baelz
- Mori Calliope
- Nanashi Mumei
- Cecilia Immergreen
- Ceres Fauna
- FUWAMOCO
- Ouro Kronii
- Gawr Gura

Edit the `CHANNELS` list in `main.py` to customize.

## 🐛 Troubleshooting

**Bot not sending notifications:**
- Check `CHAT_ID` is correct (use @userinfobot to get your ID)
- Verify bot has permission to send messages to the chat

**API quota errors:**
- Reduce check interval or number of channels
- Check `api_calls_today` with `/status` command

**Bot crashes on startup:**
- Verify `.env` file exists with all required variables
- Check Python version (3.10+ recommended)

## 📄 License

MIT License - see LICENSE file

## 🙏 Credits

Built with:
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- YouTube Data API v3
- ❤️ for VTubers
