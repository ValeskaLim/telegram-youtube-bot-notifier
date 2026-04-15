from telegram import Update
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackContext, JobQueue
import os
import asyncio
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging
import time
from typing import Dict, Optional, Set
from dataclasses import dataclass, field

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Put your YOUTUBE API KEY here
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')

# Configuration
CHECK_INTERVAL_SECONDS = 12600  # 3.5 hours between full checks
CHANNEL_CHECK_DELAY = 0.5  # Delay between individual channel checks to avoid rate limiting
CACHE_TTL_SECONDS = 3600  # Cache results for 1 hour

@dataclass
class ChannelState:
    """Track state for each channel"""
    is_live: bool = False
    last_checked: float = 0.0
    last_live_notification: float = 0.0
    video_id: Optional[str] = None
    consecutive_failures: int = 0

@dataclass
class AppState:
    """Global application state"""
    channel_states: Dict[str, ChannelState] = field(default_factory=dict)
    last_full_check: float = 0.0
    api_calls_today: int = 0
    last_reset: float = field(default_factory=lambda: time.time())

# Shared session with connection pooling and retries
def _create_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503])
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10, pool_block=False)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

HTTP_SESSION = _create_session()
APP_STATE = AppState()

# List of channels
CHANNELS = [
    {"channel_id": "UCMwGHR0BTZuLsmjY_NT5Pwg", "name": "Ninomae Ina'nis"},
    {"channel_id": "UC8rcEBzJSleTkf_-agPM20g", "name": "IRyS"},
    {"channel_id": "UCl69AEx4MdqMZH7Jtsm7Tig", "name": "Raora Panthera"},
    {"channel_id": "UC9p_lqQ0FEDz327Vgf5JwqA", "name": "Koseki Bijou"},
    {"channel_id": "UCgmPnx-EEeOrZSg5Tiw7ZRQ", "name": "Hakos Baelz"},
    {"channel_id": "UCL_qhgtOy0dy1Agp8vkySQg", "name": "Mori Calliope"},
    {"channel_id": "UCHsx4Hqa-1ORjQTh9TYDhww", "name": "Takanashi Kiara"},
    {"channel_id": "UC_sFNM0z0MWm9A6WlKPuMMg", "name": "Nerissa Ravencroft"},
    {"channel_id": "UCgnfPPb9JI3e9A4cXHnWbyg", "name": "Shiori Novella"},
    {"channel_id": "UCvN5h1ShZtc7nly3pezRayg", "name": "Cecilia Immergreen"},
    {"channel_id": "UCDHABijvPBnJm7F-KlNME3w", "name": "Gigi Murin"},
    {"channel_id": "UCt9H_RpQzhxzlyBxFqrdHqA", "name": "FUWAMOCO"},
    {"channel_id": "UCmbs8T6MWqUHP1tIQvSgKrg", "name": "Ouro Kronii"},
    {"channel_id": "UCW5uhrG1eCBYditmhL0Ykjw", "name": "Elizabeth Rose "},
]

# Paste your Chat ID Telegram Bot here
CHAT_ID = os.getenv('CHAT_ID')


def reset_daily_quota():
    """Reset API call counter if a new day has started"""
    current_time = time.time()
    if current_time - APP_STATE.last_reset > 86400:  # 24 hours
        APP_STATE.api_calls_today = 0
        APP_STATE.last_reset = current_time
        logger.info("Daily API quota reset")


def should_check_channel(channel_id: str) -> bool:
    """Determine if a channel should be checked based on cache TTL"""
    if channel_id not in APP_STATE.channel_states:
        APP_STATE.channel_states[channel_id] = ChannelState()
    
    state = APP_STATE.channel_states[channel_id]
    time_since_check = time.time() - state.last_checked
    
    # Always check if cache expired or channel was live (need to detect when it ends)
    if time_since_check > CACHE_TTL_SECONDS:
        return True
    
    # Check recently live channels more frequently to detect stream end
    if state.is_live and time_since_check > 300:  # Check live channels every 5 min
        return True
    
    return False


def get_live_stream(channel_id: str, channel_name: str, session: requests.Session | None = None) -> tuple[Optional[str], bool]:
    """
    Check if a channel is live. Returns (video_url, success).
    Uses shared session for connection pooling.
    """
    session = session or HTTP_SESSION
    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&channelId={channel_id}&eventType=live&type=video&maxResults=1&key={YOUTUBE_API_KEY}"
    
    try:
        response = session.get(url, timeout=10)
        APP_STATE.api_calls_today += 1
        
        if response.status_code == 429:
            logger.warning(f"Rate limited for {channel_name}. Backing off.")
            return (None, False)
        
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout checking {channel_name}")
        return (None, False)
    except requests.exceptions.RequestException as e:
        logger.warning(f"YouTube API request failed for {channel_name}: {e}")
        return (None, False)
    except ValueError as e:
        logger.warning(f"Invalid JSON response for {channel_name}: {e}")
        return (None, False)

    if "items" in data and len(data["items"]) > 0:
        video_id = data["items"][0]["id"]["videoId"]
        return (f"https://www.youtube.com/watch?v={video_id}", True)
    
    return (None, True)


async def check_single_channel(channel: dict, context: CallbackContext) -> None:
    """Check a single channel and send notification if newly live"""
    channel_id = channel["channel_id"]
    channel_name = channel["name"]
    
    if not should_check_channel(channel_id):
        logger.debug(f"Skipping {channel_name} (cached)")
        return
    
    if APP_STATE.api_calls_today >= 9000:  # Stay under 10k daily limit with buffer
        logger.warning("Approaching daily API quota limit. Skipping remaining checks.")
        return
    
    logger.info(f"Checking {channel_name}...")
    
    video_url, success = await asyncio.to_thread(get_live_stream, channel_id, channel_name, HTTP_SESSION)
    
    # Update state
    if channel_id not in APP_STATE.channel_states:
        APP_STATE.channel_states[channel_id] = ChannelState()
    
    state = APP_STATE.channel_states[channel_id]
    state.last_checked = time.time()
    
    if not success:
        state.consecutive_failures += 1
        if state.consecutive_failures >= 3:
            logger.error(f"Multiple failures for {channel_name}. Backing off.")
        return
    
    state.consecutive_failures = 0
    was_live = state.is_live
    
    if video_url:
        state.is_live = True
        state.video_id = video_url.split('v=')[1] if 'v=' in video_url else None
        
        # Only notify if newly live (not already notified)
        if not was_live:
            logger.info(f"🔴 {channel_name} is NOW LIVE!")
            try:
                await context.bot.send_message(
                    chat_id=CHAT_ID,
                    text=f"🔴 <b>{channel_name}</b> is LIVE NOW!\n{video_url}",
                    parse_mode='HTML'
                )
                state.last_live_notification = time.time()
            except Exception as e:
                logger.error(f"Failed to send notification for {channel_name}: {e}")
        else:
            logger.debug(f"{channel_name} still live (already notified)")
    else:
        if was_live:
            logger.info(f"⚫ {channel_name} stream ended")
        state.is_live = False
        state.video_id = None
    
    # Small delay to avoid rate limiting
    await asyncio.sleep(CHANNEL_CHECK_DELAY)


async def periodic_check(context: CallbackContext) -> None:
    """Periodic job to check all channels with smart caching"""
    reset_daily_quota()
    
    logger.info(f"Starting periodic check. API calls today: {APP_STATE.api_calls_today}")
    APP_STATE.last_full_check = time.time()
    
    # Check channels concurrently but with rate limiting
    tasks = [check_single_channel(channel, context) for channel in CHANNELS]
    await asyncio.gather(*tasks, return_exceptions=True)
    
    # Log summary
    live_count = sum(1 for state in APP_STATE.channel_states.values() if state.is_live)
    logger.info(f"Check complete. {live_count}/{len(CHANNELS)} channels currently live. API calls: {APP_STATE.api_calls_today}")


async def test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Test command to verify bot is working"""
    live_count = sum(1 for state in APP_STATE.channel_states.values() if state.is_live)
    await update.message.reply_text(
        f"✅ Bot is working perfectly, my Lord {update.effective_user.first_name}!\n\n"
        f"📊 Status:\n"
        f"• Channels monitored: {len(CHANNELS)}\n"
        f"• Currently live: {live_count}\n"
        f"• API calls today: {APP_STATE.api_calls_today}"
    )


async def check_livestream(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manual check command with optional channel filter"""
    name_filter = " ".join(context.args).strip().lower() if context.args else None
    channels = [c for c in CHANNELS if not name_filter or name_filter in c["name"].lower()]

    if not channels:
        await update.message.reply_text(f"No channels found matching '{name_filter}'.")
        return

    await update.message.reply_text(f"Checking {len(channels)} channel(s)...")
    
    # Force refresh by clearing cache for these channels
    for channel in channels:
        if channel["channel_id"] in APP_STATE.channel_states:
            APP_STATE.channel_states[channel["channel_id"]].last_checked = 0
    
    # Check immediately
    for channel in channels:
        await check_single_channel(channel, context)
    
    # Report results
    results = []
    for channel in channels:
        state = APP_STATE.channel_states.get(channel["channel_id"])
        if state and state.is_live and state.video_id:
            results.append(f"🔴 {channel['name']}: https://www.youtube.com/watch?v={state.video_id}")
    
    if results:
        await update.message.reply_text("\n".join(results))
    else:
        await update.message.reply_text("No live streams found.")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show detailed bot status and statistics"""
    reset_daily_quota()
    
    live_channels = []
    offline_channels = []
    
    for channel in CHANNELS:
        state = APP_STATE.channel_states.get(channel["channel_id"])
        if state and state.is_live:
            live_channels.append(channel["name"])
        else:
            offline_channels.append(channel["name"])
    
    status_text = (
        f"📊 <b>Bot Status</b>\n\n"
        f"🔴 Live: {len(live_channels)}\n"
        f"⚪ Offline: {len(offline_channels)}\n"
        f"📈 API calls today: {APP_STATE.api_calls_today}/10000\n"
        f"⏱️ Last full check: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(APP_STATE.last_full_check)) if APP_STATE.last_full_check > 0 else 'Never'}\n\n"
    )
    
    if live_channels:
        status_text += "<b>Currently Live:</b>\n" + "\n".join(f"• {name}" for name in live_channels[:10])
        if len(live_channels) > 10:
            status_text += f"\n... and {len(live_channels) - 10} more"
    
    await update.message.reply_text(status_text, parse_mode='HTML')


async def force_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Force immediate check of all channels (bypass cache)"""
    await update.message.reply_text("🔄 Forcing fresh check of all channels...")
    
    # Clear all caches
    for channel_id in APP_STATE.channel_states:
        APP_STATE.channel_states[channel_id].last_checked = 0
    
    # Run check
    APP_STATE.last_full_check = time.time()
    tasks = [check_single_channel(channel, context) for channel in CHANNELS]
    await asyncio.gather(*tasks, return_exceptions=True)
    
    live_count = sum(1 for state in APP_STATE.channel_states.values() if state.is_live)
    await update.message.reply_text(f"✅ Check complete! {live_count}/{len(CHANNELS)} channels are live.")


def main():
    """Main entry point"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment!")
        return
    
    if not YOUTUBE_API_KEY:
        logger.error("YOUTUBE_API_KEY not found in environment!")
        return
    
    if not CHAT_ID:
        logger.error("CHAT_ID not found in environment!")
        return
    
    app = Application.builder().token(token).concurrent_updates(True).build()
    
    # Command handlers
    app.add_handler(CommandHandler("test", test))
    app.add_handler(CommandHandler("check_livestream", check_livestream))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("force_check", force_check))
    
    # Job queue
    job_queue = app.job_queue
    
    # Schedule periodic checks
    job_queue.run_repeating(periodic_check, interval=CHECK_INTERVAL_SECONDS, first=10)
    
    logger.info(f"Telegram bot started! Monitoring {len(CHANNELS)} channels")
    logger.info(f"Check interval: {CHECK_INTERVAL_SECONDS/3600:.1f} hours")
    logger.info(f"Cache TTL: {CACHE_TTL_SECONDS/60:.0f} minutes")
    
    print("Telegram bot started!", flush=True)
    app.run_polling()


if __name__ == '__main__':
    main()
