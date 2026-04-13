# Deployment Guide

## Quick Deploy (Automated)

If you have SSH access to your VPS:

```bash
# Make script executable
chmod +x deploy.sh

# Run deployment (replace with your VPS details)
./deploy.sh your-username your-vps-ip ~/youtube-notifier
```

The script will:
1. ✅ Backup existing installation
2. ✅ Stop the running bot
3. ✅ Pull latest code from GitHub
4. ✅ Install dependencies
5. ✅ Configure systemd service
6. ✅ Start the bot

---

## Manual Deployment

### Step 1: Backup Existing Installation

SSH into your VPS:
```bash
ssh user@your-vps-ip
```

Create backup:
```bash
cd ~
tar -czf youtube-notifier-backup-$(date +%Y%m%d-%H%M%S).tar.gz youtube-notifier/
echo "Backup created: youtube-notifier-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
```

### Step 2: Stop Existing Bot

If running as systemd service:
```bash
sudo systemctl stop youtube-notifier
```

If running in screen/tmux:
```bash
pkill -f "python.*main.py"
# Or find the process: ps aux | grep main.py
# Then: kill <PID>
```

### Step 3: Update Code

Option A - Git pull (if already cloned):
```bash
cd ~/youtube-notifier
git pull origin main
```

Option B - Fresh clone:
```bash
cd ~
rm -rf youtube-notifier
git clone https://github.com/ValeskaLim/telegram-youtube-bot-notifier.git
cd youtube-notifier
```

### Step 4: Install Dependencies

```bash
cd ~/youtube-notifier

# Create virtual environment
python3 -m venv venv

# Activate and install
source venv/bin/activate
pip install -r requirements.txt
```

### Step 5: Configure Environment

```bash
# Copy example and edit
cp .env.example .env
nano .env  # Or use your preferred editor
```

Edit `.env` with your credentials:
```env
TELEGRAM_BOT_TOKEN=your_actual_token_here
YOUTUBE_API_KEY=your_actual_api_key_here
CHAT_ID=your_actual_chat_id_here
```

### Step 6: Test Before Deploying

```bash
cd ~/youtube-notifier
source venv/bin/activate
python main.py
```

Check for errors. Press `Ctrl+C` to stop after confirming it starts correctly.

### Step 7: Setup Systemd Service (Recommended)

Create service file:
```bash
sudo nano /etc/systemd/system/youtube-notifier.service
```

Paste this (replace `your-username`):
```ini
[Unit]
Description=YouTube Telegram Notifier Bot
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/home/your-username/youtube-notifier
Environment=PATH=/home/your-username/youtube-notifier/venv/bin
ExecStart=/home/your-username/youtube-notifier/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable youtube-notifier
sudo systemctl start youtube-notifier
```

### Step 8: Verify It's Running

```bash
# Check status
sudo systemctl status youtube-notifier

# View logs
sudo journalctl -u youtube-notifier -f

# Test bot (send /test to your bot on Telegram)
```

---

## Push to GitHub

From your local machine:

```bash
cd telegram-youtube-bot-notifier

# If you haven't configured git credentials yet:
git config user.email "your-email@example.com"
git config user.name "Your Name"

# Commit and push
git add .
git commit -m "feat: optimize API usage with smart caching"
git push origin main
```

If using HTTPS and prompted for password, use a [GitHub Personal Access Token](https://github.com/settings/tokens):
- Generate token with `repo` scope
- Use token as password when prompted

---

## Testing Checklist

After deployment, verify:

- [ ] Bot responds to `/test` command
- [ ] Bot responds to `/status` command
- [ ] Check logs show successful startup
- [ ] Wait for next check interval or use `/force_check`
- [ ] Verify notifications are sent when channels go live
- [ ] Monitor API usage with `/status` (should be reasonable)

---

## Rollback (If Needed)

If something goes wrong:

```bash
# Stop bot
sudo systemctl stop youtube-notifier

# Restore backup
cd ~
tar -xzf youtube-notifier-backup-YYYYMMDD-HHMMSS.tar.gz

# Restart
sudo systemctl start youtube-notifier
```

---

## Troubleshooting

**Bot won't start:**
```bash
# Check logs
sudo journalctl -u youtube-notifier -n 50

# Test manually
cd ~/youtube-notifier
source venv/bin/activate
python main.py
```

**Common issues:**
- Missing `.env` file or incorrect credentials
- Python version mismatch (need 3.10+)
- Port already in use (check if another instance is running)
- Firewall blocking outbound connections

**API quota concerns:**
- Use `/status` to check current API usage
- Increase `CHECK_INTERVAL_SECONDS` in `main.py` if needed
- Reduce number of channels in `CHANNELS` list
