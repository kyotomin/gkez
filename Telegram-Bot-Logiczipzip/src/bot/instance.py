from aiogram import Bot
from src.config import BOT_TOKEN

bot = None

def create_bot():
    global bot
    if BOT_TOKEN:
        bot = Bot(token=BOT_TOKEN)
    return bot

def get_bot():
    return bot
