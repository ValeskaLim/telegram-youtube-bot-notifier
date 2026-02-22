from telegram import Update
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackContext, JobQueue
import os
import asyncio
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging

load_dotenv()
logging.basicConfig(level=logging.INFO)

# Put your YOUTUBE API KEY here
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')

# Shared session with connection pooling and retries
def _create_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503])
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

HTTP_SESSION = _create_session()

# List of channels
CHANNELS = [
    {"channel_id": "UCMwGHR0BTZuLsmjY_NT5Pwg", "name": "Ninomae Ina'nis"},
    {"channel_id": "UC8rcEBzJSleTkf_-agPM20g", "name": "IRyS"},
    {"channel_id": "UCl69AEx4MdqMZH7Jtsm7Tig", "name": "Raora Panthera"},
    {"channel_id": "UC9p_lqQ0FEDz327Vgf5JwqA", "name": "Koseki Bijou"},
    {"channel_id": "UCgmPnx-EEeOrZSg5Tiw7ZRQ", "name": "Hakos Baelz"},
    {"channel_id": "UCL_qhgtOy0dy1Agp8vkySQg", "name": "Mori Calliope"},
    # {"channel_id": "UCHsx4Hqa-1ORjQTh9TYDhww", "name": "Takanashi Kiara"},
    # {"channel_id": "UC_sFNM0z0MWm9A6WlKPuMMg", "name": "Nerissa Ravencroft"},
    # {"channel_id": "UCgnfPPb9JI3e9A4cXHnWbyg", "name": "Shiori Novella"},
    {"channel_id": "UC3n5uGu18FoCy23ggWWp8tA", "name": "Nanashi Mumei"},
    {"channel_id": "UCvN5h1ShZtc7nly3pezRayg", "name": "Cecilia Immergreen"},
    # {"channel_id": "UCDHABijvPBnJm7F-KlNME3w", "name": "Gigi Murin"},
    {"channel_id": "UCO_aKKYxn4tvrqPjcTzZ6EQ", "name": "Ceres Fauna"},
    {"channel_id": "UCt9H_RpQzhxzlyBxFqrdHqA", "name": "FUWAMOCO"},
    {"channel_id": "UCmbs8T6MWqUHP1tIQvSgKrg", "name": "Ouro Kronii"},
    {"channel_id": "UCoSrY_IQQVpmIRZ9Xf-y93g", "name": "Gawr Gura"},
    # {"channel_id": "UCW5uhrG1eCBYditmhL0Ykjw", "name": "Elizabeth Rose "},
]

# Paste your Chat ID Telegram Bot here
CHAT_ID = os.getenv('CHAT_ID')

async def test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f'This bot works perfectly. My Lord, {update.effective_user.first_name}')

async def check_livestream(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Optional: filter by channel name(s) from command args, e.g. /check_livestream Gawr Gura
    name_filter = " ".join(context.args).strip().lower() if context.args else None
    channels = [c for c in CHANNELS if not name_filter or name_filter in c["name"].lower()]

    if not channels:
        await update.message.reply_text(f"No channels found matching '{name_filter}'.")
        return

    results = await get_live_streams_parallel(channels)
    for channel, live_stream in results:
        if live_stream:
            await update.message.reply_text(f"The channel {channel['name']} is live: {live_stream}")
        else:
            await update.message.reply_text(f"No livestreams for channel {channel['name']} at the moment.")

def get_live_stream(channel_id: str, session: requests.Session | None = None) -> str | None:
    """Check if a channel is live. Returns video URL or None. Uses shared session for connection pooling."""
    session = session or HTTP_SESSION
    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&channelId={channel_id}&eventType=live&type=video&key={YOUTUBE_API_KEY}"
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as e:
        logging.warning("YouTube API request failed for %s: %s", channel_id, e)
        return None

    if "items" in data and len(data["items"]) > 0:
        video_id = data["items"][0]["id"]["videoId"]
        return f"https://www.youtube.com/watch?v={video_id}"
    return None


async def get_live_streams_parallel(channels: list[dict]) -> list[tuple[dict, str | None]]:
    """Fetch live status for multiple channels concurrently. Returns list of (channel, url_or_none)."""

    def _fetch(channel: dict) -> tuple[dict, str | None]:
        try:
            url = get_live_stream(channel["channel_id"])
            return (channel, url)
        except Exception as e:
            logging.warning("Channel check failed for %s: %s", channel["name"], e)
            return (channel, None)

    return await asyncio.gather(*[asyncio.to_thread(_fetch, ch) for ch in channels])

async def periodic_check(context: CallbackContext):
    results = await get_live_streams_parallel(CHANNELS)
    for channel, live_stream in results:
        if live_stream:
            await context.bot.send_message(chat_id=CHAT_ID, text=f"{channel['name']} is live NOW!: {live_stream}")

def main():
    """
    Handles the initial launch of the program (entry point).
    """

    # Put your telegram bot token here
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    app = Application.builder().token(token).concurrent_updates(True).build()
    job_queue = JobQueue()
    app.add_handler(CommandHandler("test", test))
    app.add_handler(CommandHandler("check_livestream", check_livestream))

    job_queue = app.job_queue

    # Adjust the interval of your bots (in seconds)
    job_queue.run_repeating(periodic_check, interval=12600, first=10)

    print("Telegram bot started!", flush=True)
    app.run_polling()

if __name__ == '__main__':
    main()
