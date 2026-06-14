"""Telegram notifier for VTuber livestreams.

Detects when monitored Hololive channels go live and pushes a Telegram message.

Primary data source is the Holodex API: a single request returns the live/upcoming
state for every monitored channel at once, so the bot can poll frequently (default
every 2 minutes) while staying well within rate limits. If no Holodex key is set,
it falls back to the YouTube Data API (one search per channel, 100 quota units each).
"""
import os
import html
import time
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackContext

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid %s, using default %s", name, default)
        return default


def _bool_env(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
HOLODEX_API_KEY = os.getenv("HOLODEX_API_KEY")          # primary source (recommended)
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")          # optional fallback

# How often to poll. Holodex is cheap so 120s gives near-instant alerts.
CHECK_INTERVAL_SECONDS = _int_env("CHECK_INTERVAL_SECONDS", 120)
HTTP_TIMEOUT = _int_env("HTTP_TIMEOUT_SECONDS", 15)
# If true, also alert for streams already live when the bot (re)starts.
# Default false avoids a burst of alerts every time the service restarts.
NOTIFY_ON_STARTUP = _bool_env("NOTIFY_ON_STARTUP", False)

HOLODEX_LIVE_URL = "https://holodex.net/api/v2/users/live"
HOLODEX_MAX_CHANNELS = 50  # API caps channels per request
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_SEARCH_COST = 100  # quota units per search.list call
USER_AGENT = "telegram-youtube-bot/2.0 (+https://github.com/ValeskaLim)"

# Cloudflare in front of Holodex rejects the default python user-agent, so set one.
def _create_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": USER_AGENT})
    return session


HTTP_SESSION = _create_session()

# Channels to monitor (Hololive English).
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
    {"channel_id": "UCW5uhrG1eCBYditmhL0Ykjw", "name": "Elizabeth Rose Bloodflame"},
]
CHANNEL_NAMES = {c["channel_id"]: c["name"] for c in CHANNELS}
CHANNEL_IDS = [c["channel_id"] for c in CHANNELS]


# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #
@dataclass
class ChannelState:
    is_live: bool = False
    video_id: Optional[str] = None
    title: Optional[str] = None
    notified_video_id: Optional[str] = None  # last video we already alerted for
    last_live_at: float = 0.0


@dataclass
class AppState:
    channel_states: Dict[str, ChannelState] = field(
        default_factory=lambda: {cid: ChannelState() for cid in CHANNEL_IDS}
    )
    last_check: float = 0.0
    last_check_ok: bool = False
    consecutive_failures: int = 0
    first_sync_done: bool = False
    holodex_calls_today: int = 0
    youtube_units_today: int = 0
    last_reset: float = field(default_factory=time.time)


APP_STATE = AppState()


def reset_daily_counters() -> None:
    if time.time() - APP_STATE.last_reset > 86400:
        APP_STATE.holodex_calls_today = 0
        APP_STATE.youtube_units_today = 0
        APP_STATE.last_reset = time.time()
        logger.info("Daily counters reset")


# --------------------------------------------------------------------------- #
# Data sources (sync; run via asyncio.to_thread)
# --------------------------------------------------------------------------- #
def _fetch_live_holodex() -> Dict[str, dict]:
    """Return {channel_id: {'video_id', 'title'}} for channels that are LIVE.

    Raises requests.RequestException on failure so the caller can react.
    """
    live: Dict[str, dict] = {}
    for i in range(0, len(CHANNEL_IDS), HOLODEX_MAX_CHANNELS):
        chunk = CHANNEL_IDS[i:i + HOLODEX_MAX_CHANNELS]
        resp = HTTP_SESSION.get(
            HOLODEX_LIVE_URL,
            params={"channels": ",".join(chunk)},
            headers={"X-APIKEY": HOLODEX_API_KEY},
            timeout=HTTP_TIMEOUT,
        )
        APP_STATE.holodex_calls_today += 1
        resp.raise_for_status()
        for video in resp.json() or []:
            if video.get("status") != "live":
                continue
            channel_id = (video.get("channel") or {}).get("id") or video.get("channel_id")
            if channel_id:
                live[channel_id] = {"video_id": video.get("id"), "title": video.get("title")}
    return live


def _fetch_live_youtube() -> Dict[str, dict]:
    """Fallback: one search per channel via the YouTube Data API (100 units each).

    Skips channels that error so a single failure doesn't sink the whole cycle.
    Raises only if *every* channel request failed.
    """
    live: Dict[str, dict] = {}
    any_ok = False
    last_error: Optional[Exception] = None
    for cid in CHANNEL_IDS:
        try:
            resp = HTTP_SESSION.get(
                YOUTUBE_SEARCH_URL,
                params={
                    "part": "snippet", "channelId": cid, "eventType": "live",
                    "type": "video", "maxResults": 1, "key": YOUTUBE_API_KEY,
                },
                timeout=HTTP_TIMEOUT,
            )
            APP_STATE.youtube_units_today += YOUTUBE_SEARCH_COST
            resp.raise_for_status()
            any_ok = True
            items = resp.json().get("items", [])
            if items:
                live[cid] = {
                    "video_id": items[0]["id"].get("videoId"),
                    "title": items[0].get("snippet", {}).get("title"),
                }
        except requests.RequestException as e:
            last_error = e
            logger.warning("YouTube check failed for %s: %s", CHANNEL_NAMES.get(cid, cid), e)
    if not any_ok and last_error:
        raise last_error
    return live


def collect_live_streams() -> Optional[Dict[str, dict]]:
    """Detect currently-live channels. Returns the live map, or None if detection
    failed entirely (so callers can preserve prior state instead of marking all offline).
    """
    if HOLODEX_API_KEY:
        try:
            return _fetch_live_holodex()
        except requests.RequestException as e:
            logger.warning("Holodex check failed: %s", e)
            if not YOUTUBE_API_KEY:
                return None
            logger.info("Falling back to YouTube API for this cycle")
    if YOUTUBE_API_KEY:
        try:
            return _fetch_live_youtube()
        except requests.RequestException as e:
            logger.warning("YouTube fallback failed: %s", e)
    return None


# --------------------------------------------------------------------------- #
# Notification + state diff
# --------------------------------------------------------------------------- #
async def _send_live_alert(context: CallbackContext, name: str, state: ChannelState) -> None:
    url = f"https://www.youtube.com/watch?v={state.video_id}"
    text = f"🔴 <b>{html.escape(name)}</b> is LIVE NOW!\n"
    if state.title:
        text += f"<i>{html.escape(state.title)}</i>\n"
    text += url
    try:
        await context.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="HTML")
        logger.info("🔴 Notified: %s (%s)", name, url)
    except Exception as e:  # noqa: BLE001 - never let a send failure crash the cycle
        logger.error("Failed to send notification for %s: %s", name, e)


async def apply_live_state(live: Dict[str, dict], context: CallbackContext, notify: bool = True) -> None:
    """Update channel states from the live map and alert on newly-live channels.

    De-dupes by video id: an ongoing stream is never re-announced, while a new
    stream (new video id) always is.
    """
    now = time.time()
    for cid in CHANNEL_IDS:
        state = APP_STATE.channel_states[cid]
        info = live.get(cid)
        if info and info.get("video_id"):
            state.is_live = True
            state.video_id = info["video_id"]
            state.title = info.get("title")
            state.last_live_at = now
            if state.video_id != state.notified_video_id:
                if notify:
                    await _send_live_alert(context, CHANNEL_NAMES[cid], state)
                state.notified_video_id = state.video_id  # mark handled (also seeds silent sync)
        else:
            if state.is_live:
                logger.info("⚫ %s stream ended", CHANNEL_NAMES[cid])
            state.is_live = False
            state.video_id = None
            state.title = None


# --------------------------------------------------------------------------- #
# Jobs & commands
# --------------------------------------------------------------------------- #
async def run_check(context: CallbackContext) -> Optional[int]:
    """Run one detection cycle. Returns live channel count, or None on failure."""
    reset_daily_counters()
    live = await asyncio.to_thread(collect_live_streams)
    APP_STATE.last_check = time.time()
    if live is None:
        APP_STATE.last_check_ok = False
        APP_STATE.consecutive_failures += 1
        logger.warning("Live check failed (streak %d); keeping previous state",
                       APP_STATE.consecutive_failures)
        return None
    APP_STATE.last_check_ok = True
    APP_STATE.consecutive_failures = 0
    notify = APP_STATE.first_sync_done or NOTIFY_ON_STARTUP
    await apply_live_state(live, context, notify=notify)
    APP_STATE.first_sync_done = True
    return sum(1 for s in APP_STATE.channel_states.values() if s.is_live)


async def periodic_check(context: CallbackContext) -> None:
    live_count = await run_check(context)
    if live_count is not None:
        logger.info("Check complete. %d/%d live. Holodex calls today: %d",
                    live_count, len(CHANNELS), APP_STATE.holodex_calls_today)


def _source_label() -> str:
    if HOLODEX_API_KEY:
        return "Holodex"
    if YOUTUBE_API_KEY:
        return "YouTube (fallback)"
    return "none"


async def test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    live_count = sum(1 for s in APP_STATE.channel_states.values() if s.is_live)
    await update.message.reply_text(
        f"✅ Bot is working, {update.effective_user.first_name}!\n\n"
        f"📊 Status:\n"
        f"• Source: {_source_label()}\n"
        f"• Channels monitored: {len(CHANNELS)}\n"
        f"• Currently live: {live_count}\n"
        f"• Poll interval: {CHECK_INTERVAL_SECONDS}s"
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reset_daily_counters()
    live = [(c["name"], APP_STATE.channel_states[c["channel_id"]])
            for c in CHANNELS if APP_STATE.channel_states[c["channel_id"]].is_live]
    last = (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(APP_STATE.last_check))
            if APP_STATE.last_check else "Never")
    text = (
        f"📊 <b>Bot Status</b>\n\n"
        f"🛰️ Source: {_source_label()}\n"
        f"🔴 Live: {len(live)} / {len(CHANNELS)}\n"
        f"⏱️ Last check: {last} ({'ok' if APP_STATE.last_check_ok else 'FAILED'})\n"
        f"🔁 Holodex calls today: {APP_STATE.holodex_calls_today}\n"
    )
    if APP_STATE.youtube_units_today:
        text += f"📉 YouTube units today: {APP_STATE.youtube_units_today}/10000\n"
    if live:
        text += "\n<b>Currently Live:</b>\n" + "\n".join(
            f"• {html.escape(n)}: https://youtu.be/{s.video_id}" for n, s in live[:15]
        )
    await update.message.reply_text(text, parse_mode="HTML")


async def check_livestream(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    name_filter = " ".join(context.args).strip().lower() if context.args else None
    channels = [c for c in CHANNELS if not name_filter or name_filter in c["name"].lower()]
    if not channels:
        await update.message.reply_text(f"No channels found matching '{name_filter}'.")
        return
    await update.message.reply_text(f"🔄 Checking {len(channels)} channel(s)...")
    # One call refreshes every channel regardless of the filter; filter is display-only.
    if await run_check(context) is None:
        await update.message.reply_text("⚠️ Live check failed (source unavailable). Try again shortly.")
        return
    results = [
        f"🔴 {c['name']}: https://youtu.be/{APP_STATE.channel_states[c['channel_id']].video_id}"
        for c in channels if APP_STATE.channel_states[c["channel_id"]].is_live
    ]
    await update.message.reply_text("\n".join(results) if results else "No live streams found.")


async def force_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🔄 Forcing fresh check of all channels...")
    live_count = await run_check(context)
    if live_count is None:
        await update.message.reply_text("⚠️ Check failed (source unavailable). Try again shortly.")
        return
    await update.message.reply_text(f"✅ Check complete! {live_count}/{len(CHANNELS)} channels are live.")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment!")
        return
    if not CHAT_ID:
        logger.error("CHAT_ID not found in environment!")
        return
    if not HOLODEX_API_KEY and not YOUTUBE_API_KEY:
        logger.error("Set HOLODEX_API_KEY (recommended) or YOUTUBE_API_KEY in environment!")
        return
    if not HOLODEX_API_KEY:
        logger.warning("HOLODEX_API_KEY not set - using YouTube fallback "
                       "(%d units per channel per check).", YOUTUBE_SEARCH_COST)

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).concurrent_updates(True).build()
    app.add_handler(CommandHandler("test", test))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("check_livestream", check_livestream))
    app.add_handler(CommandHandler("force_check", force_check))

    app.job_queue.run_repeating(periodic_check, interval=CHECK_INTERVAL_SECONDS, first=5)

    logger.info("Bot started. Monitoring %d channels every %ds via %s",
                len(CHANNELS), CHECK_INTERVAL_SECONDS, _source_label())
    print("Telegram bot started!", flush=True)
    app.run_polling()


if __name__ == "__main__":
    main()
