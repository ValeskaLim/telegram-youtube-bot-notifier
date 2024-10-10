# Telegram Youtube Bot 🤖
The purpose why i made this bot is to built my first bot using Telegram. And it's also aimed to help me on my job. It will send you a notification whetever the channel is go live or not. The default channel list in this bot is Hololive English :D

Built using Youtube Data API V3

## Installation

1. Install the dependency in your virtual environment
```
pip install python-telegram-bot python-telegram python-dotenv requests
```

2. Replace this with your TELEGRAM_BOT_TOKEN, YOUTUBE_API_KEY, and CHAT_ID
```
CHAT_ID = <your-chat-telegram-bot-chat-id>
YOUTUBE_API_KEY = <your-youtube-data-api-key>
token = <your-telegram-bot-token>
```

## Tips

Due to quotas limit of Youtube Data API (Quotas per day) which is 10.000. I reccommend you to set the interval above 2 hours. And limit the channel list (for example 10).
