from telegram import Update
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackContext, JobQueue
import os
import json
import requests
import logging

load_dotenv()
logging.basicConfig(level=logging.INFO)

# Put your YOUTUBE API KEY here
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')

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
    # {"channel_id": "UCvN5h1ShZtc7nly3pezRayg", "name": "Cecilia Immergreen"},
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
    for channel in CHANNELS:    
        live_stream = get_live_stream(channel['channel_id'])
        if live_stream:
            await update.message.reply_text(f"The channel {channel['name']} is live: {live_stream}")
        else:
            await update.message.reply_text(f"No livestreams for channel {channel['name']} at the moment.")

def get_live_stream(channel_id):
    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&channelId={channel_id}&eventType=live&type=video&key={YOUTUBE_API_KEY}"
    response = requests.get(url)
    data = response.json()

    if "items" in data and len(data["items"]) > 0:
        video_id = data["items"][0]["id"]["videoId"]
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        return video_url
    return None

async def periodic_check(context: CallbackContext):
    for channel in CHANNELS:
        live_stream = get_live_stream(channel['channel_id'])
        if live_stream:
            await context.bot.send_message(chat_id=CHAT_ID, text=f"{channel['name']} is live NOW!: {live_stream}")
        elif not live_stream:
            await context.bot.send_message(chat_id=CHAT_ID, text=f"No livestreams for channel {channel['name']} at the moment.")

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
    job_queue.run_repeating(periodic_check, interval=10800, first=10)

    print("Telegram bot started!", flush=True)
    app.run_polling()

if __name__ == '__main__':
    main()
