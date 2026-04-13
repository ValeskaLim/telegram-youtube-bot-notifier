#!/bin/bash
# deploy.sh - Deploy optimized YouTube notifier to VPS
# Usage: ./deploy.sh <vps-user> <vps-host> [vps-path]

set -e

VPS_USER="${1:-}"
VPS_HOST="${2:-}"
VPS_PATH="${3:-~/youtube-notifier}"
BACKUP_DIR="~/backups"

if [ -z "$VPS_USER" ] || [ -z "$VPS_HOST" ]; then
    echo "Usage: $0 <vps-user> <vps-host> [vps-path]"
    echo "Example: $0 user 192.168.1.100 ~/youtube-notifier"
    exit 1
fi

echo "🚀 YouTube Notifier Deployment Script"
echo "======================================"
echo "VPS: $VPS_USER@$VPS_HOST"
echo "Path: $VPS_PATH"
echo ""

# Step 1: Backup existing installation
echo "📦 Step 1: Creating backup on VPS..."
ssh $VPS_USER@$VPS_HOST "
    mkdir -p $BACKUP_DIR
    if [ -d '$VPS_PATH' ]; then
        BACKUP_NAME='youtube-notifier-backup-\$(date +%Y%m%d-%H%M%S).tar.gz'
        tar -czf \$BACKUP_DIR/\$BACKUP_NAME -C \$(dirname '$VPS_PATH') \$(basename '$VPS_PATH')
        echo \"✅ Backup created: \$BACKUP_DIR/\$BACKUP_NAME\"
    else
        echo '⚠️  No existing installation found, skipping backup'
    fi
"

# Step 2: Stop existing bot
echo "🛑 Step 2: Stopping existing bot..."
ssh $VPS_USER@$VPS_HOST "
    if systemctl is-active --quiet youtube-notifier 2>/dev/null; then
        sudo systemctl stop youtube-notifier
        echo '✅ Stopped systemd service'
    else
        pkill -f 'python.*main.py' 2>/dev/null && echo '✅ Killed running process' || echo '⚠️  No running process found'
    fi
"

# Step 3: Deploy new code
echo "📤 Step 3: Deploying new code..."
if [ -d ".git" ]; then
    # If running from git repo, push first
    echo "   Pushing to GitHub..."
    git push origin main
    echo "   ✅ Pushed to GitHub"
    
    # Pull on VPS
    ssh $VPS_USER@$VPS_HOST "
        if [ -d '$VPS_PATH/.git' ]; then
            cd '$VPS_PATH'
            git pull origin main
            echo '✅ Pulled latest changes'
        else
            echo '⚠️  Not a git repository, skipping pull'
        fi
    "
else
    # Copy files via scp
    echo "   Copying files via SCP..."
    ssh $VPS_USER@$VPS_HOST "mkdir -p '$VPS_PATH'"
    scp main.py requirements.txt README.md .env.example $VPS_USER@$VPS_HOST:"$VPS_PATH/"
    echo "   ✅ Files copied"
fi

# Step 4: Install dependencies
echo "📦 Step 4: Installing dependencies..."
ssh $VPS_USER@$VPS_HOST "
    cd '$VPS_PATH'
    if [ ! -d 'venv' ]; then
        python3 -m venv venv
        echo '✅ Created virtual environment'
    fi
    source venv/bin/activate
    pip install -r requirements.txt --upgrade
    echo '✅ Dependencies installed'
"

# Step 5: Setup systemd service
echo "⚙️  Step 5: Configuring systemd service..."
ssh $VPS_USER@$VPS_HOST "
    cat > /tmp/youtube-notifier.service << 'EOF'
[Unit]
Description=YouTube Telegram Notifier Bot
After=network.target

[Service]
Type=simple
User=$VPS_USER
WorkingDirectory=$VPS_PATH
Environment=PATH=$VPS_PATH/venv/bin
ExecStart=$VPS_PATH/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    sudo mv /tmp/youtube-notifier.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable youtube-notifier
    echo '✅ Systemd service configured'
"

# Step 6: Start bot
echo "🚀 Step 6: Starting bot..."
ssh $VPS_USER@$VPS_HOST "
    sudo systemctl start youtube-notifier
    sleep 2
    if systemctl is-active --quiet youtube-notifier; then
        echo '✅ Bot started successfully!'
        sudo systemctl status youtube-notifier --no-pager
    else
        echo '❌ Bot failed to start. Check logs:'
        sudo journalctl -u youtube-notifier -n 20 --no-pager
        exit 1
    fi
"

echo ""
echo "======================================"
echo "✅ Deployment complete!"
echo ""
echo "Useful commands:"
echo "  View logs:     ssh $VPS_USER@$VPS_HOST 'sudo journalctl -u youtube-notifier -f'"
echo "  Stop bot:      ssh $VPS_USER@$VPS_HOST 'sudo systemctl stop youtube-notifier'"
echo "  Restart bot:   ssh $VPS_USER@$VPS_HOST 'sudo systemctl restart youtube-notifier'"
echo "  Status:        ssh $VPS_USER@$VPS_HOST 'sudo systemctl status youtube-notifier'"
echo ""
