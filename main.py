import telebot

TOKEN = '8947764328:AAFzICxFaQ0RV1PsrSgXi7jcDp7nUjCj04o'
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "Bot Cholteche ✅")

print("Bot started...")
bot.polling(none_stop=True)
