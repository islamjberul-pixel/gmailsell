import telebot
import random
import firebase_admin
import os
import json
import re
from firebase_admin import credentials, firestore
from telebot import types
import time

TOKEN = os.getenv("TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
ADMIN_WHATSAPP = "8801796103936"

firebase_json = os.getenv("FIREBASE_KEY")
cred_dict = json.loads(firebase_json)
cred = credentials.Certificate(cred_dict)
firebase_admin.initialize_app(cred)
db = firestore.client()

bot = telebot.TeleBot(TOKEN)
user_temp = {}
user_states = {}
CURRENCY = {"BDT":1, "USD":0.0092, "INR":0.76}

def get_settings():
    ref = db.collection('settings').document('config').get()
    if not ref.exists:
        db.collection('settings').document('config').set({
            'new_gmail_price': 12, 'old_gmail_price': 6, 'min_withdraw': 25,
            'empty_stock_msg': 'Stock Empty! Admin বলেছে: শীঘ্রই Stock আসবে'
        })
        return {'new_gmail_price': 12, 'old_gmail_price': 6, 'min_withdraw': 25, 'empty_stock_msg': 'Stock Empty! Admin বলেছে: শীঘ্রই Stock আসবে'}
    data = ref.to_dict()
    if 'min_withdraw' not in data: data['min_withdraw'] = 25
    return data

def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("➕ Register a new Gmail")
    markup.add("📁 My accounts", "💰 Balance")
    markup.add("💸 Withdraw", "⏳ Balance Hold")
    markup.add("📦 Old Gmail Sell", "⚙️ Settings")
    markup.add("👑 Admin Panel")
    return markup

def admin_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("➕ Add Gmail Stock", "📋 Stock List")
    markup.add("📧 Pending Gmail", "💸 Pending Withdraw")
    markup.add("👥 All Users", "🚫 Block User")
    markup.add("💰 Set New Gmail Price", "📦 Set Old Gmail Price")
    markup.add("📢 Send Notification", "⚙️ Set Min Withdraw")
    markup.add("📊 Stats", "🔙 Back")
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    user_id = str(message.from_user.id)
    user_ref = db.collection('users').document(user_id)
    if not user_ref.get().exists:
        user_ref.set({'balance':0, 'hold':0, 'accounts':[], 'currency':'BDT', 'blocked': False})
    if user_id in user_temp: del user_temp[user_id]
    if user_id in user_states: del user_states[user_id]
    bot.send_message(message.chat.id, "Welcome to BK71 CLUB Bot! 🤖", reply_markup=main_menu())

@bot.message_handler(func=lambda m: True)
def handler(message):
    user_id = str(message.from_user.id)
    chat_id = message.chat.id
    text = message.text
    settings = get_settings()

    user_ref = db.collection('users').document(user_id)
    user_doc = user_ref.get()
    if not user_doc.exists: return

    # Global Cancel - সবার আগে Check
    if text in ["⬅️ Back", "🔙 Back", "Cancel"]:
        if user_id in user_temp: del user_temp[user_id]
        if user_id in user_states: del user_states[user_id]
        bot.send_message(chat_id, "✅ Cancel করা হয়েছে", reply_markup=main_menu())
        return

    # যদি State এ থাকো আর নতুন Admin বাটন চাপো
    admin_buttons = ["➕ Add Gmail Stock", "📋 Stock List", "📧 Pending Gmail", "💸 Pending Withdraw",
                     "👥 All Users", "🚫 Block User", "💰 Set New Gmail Price", "📦 Set Old Gmail Price",
                     "📢 Send Notification", "⚙️ Set Min Withdraw", "📊 Stats", "👑 Admin Panel"]
    if user_id in user_states and text in admin_buttons:
        del user_states[user_id]

    # ========== USER PANEL ==========
    if text == "💰 Balance":
        user = user_ref.get().to_dict()
        rate = CURRENCY[user['currency']]
        bal = user['balance'] * rate
        bot.send_message(chat_id, f"💰 Main Balance: {bal:.2f} {user['currency']}\n⏳ Hold: {user['hold']} BDT", reply_markup=main_menu())

    elif text == "📦 Old Gmail Sell":
        bot.send_message(chat_id, "Step 1/2\nOld Gmail টা দাও @gmail.com সহ:\n\nCancel লিখলে বাদ")
        user_temp[user_id] = {'type':'old', 'step':'email'}

    elif text == "➕ Register a new Gmail":
        stock_ref = db.collection('gmail_stock').limit(1).get()
        stock = [doc.to_dict() for doc in stock_ref]
        if not stock: bot.send_message(chat_id, settings['empty_stock_msg'], reply_markup=main_menu()); return
        gmail = stock[0]
        user_temp[user_id] = {'type':'new', 'data':gmail}
        msg = f"👤 Name: {gmail['first_name']} {gmail['last_name']}\n📧 Email: `{gmail['email']}`\n🔑 Pass: `{gmail['pass']}`\n💰 Price: {gmail['price']} BDT"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Submit", callback_data="submit_new"))
        bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=markup)

    # ========== ADMIN PANEL ==========
    elif text == "👑 Admin Panel":
        if user_id == str(ADMIN_ID):
            bot.send_message(chat_id, "👑 Admin Panel", reply_markup=admin_menu())
        else:
            bot.send_message(chat_id, "তুমি Admin না", reply_markup=main_menu())

    elif text == "➕ Add Gmail Stock" and user_id == str(ADMIN_ID):
        bot.send_message(chat_id, "Step 1/4\nFirst Name লিখো:")
        user_states[user_id] = {'state':'add_stock', 'step':'first_name', 'data':{}}

    elif text == "📦 Set Old Gmail Price" and user_id == str(ADMIN_ID):
        bot.send_message(chat_id, f"Current: {settings['old_gmail_price']} BDT\nনতুন দাম লিখো:")
        user_states[user_id] = {'state':'set_old_price'}

    elif text == "⚙️ Set Min Withdraw" and user_id == str(ADMIN_ID):
        bot.send_message(chat_id, f"Current: {settings['min_withdraw']} BDT\nনতুন Min লিখো:")
        user_states[user_id] = {'state':'set_min'}

    elif text == "📢 Send Notification" and user_id == str(ADMIN_ID):
        bot.send_message(chat_id, "Notification লিখো:")
        user_states[user_id] = {'state':'send_noti'}

    # ========== STATE HANDLER - MAIN FIX ==========
    elif user_id in user_states:
        state = user_states[user_id]

        try:
            if state['state'] == 'add_stock':
                if state['step'] == 'first_name':
                    state['data']['first_name'] = text
                    bot.send_message(chat_id, "Step 2/4\nLast Name লিখো:")
                    state['step'] = 'last_name'
                elif state['step'] == 'last_name':
                    state['data']['last_name'] = text
                    bot.send_message(chat_id, "Step 3/4\nEmail লিখো:")
                    state['step'] = 'email'
                elif state['step'] == 'email':
                    state['data']['email'] = text
                    bot.send_message(chat_id, "Step 4/4\nPassword লিখো:")
                    state['step'] = 'password'
                elif state['step'] == 'password': # এখানেই Reply আটকাতো
                    state['data']['pass'] = text
                    settings = get_settings()
                    db.collection('gmail_stock').document(state['data']['email']).set({
                        'email':state['data']['email'], 'pass':state['data']['pass'],
                        'first_name':state['data']['first_name'], 'last_name':state['data']['last_name'],
                        'price':settings['new_gmail_price']
                    })
                    # Reply দেয়ার পর State Clear
                    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    markup.add("✅ Complete & Add Another", "🔙 Back")
                    bot.send_message(chat_id, f"✅ Added: {state['data']['email']}", reply_markup=markup)
                    state['step'] = 'complete'

            elif state.get('step') == 'complete':
                del user_states[user_id] # Reply দিয়েই Clear
                bot.send_message(chat_id, "Done", reply_markup=admin_menu())

            elif state['state'] == 'set_old_price': # এখানেও Reply আটকাতো
                db.collection('settings').document('config').update({'old_gmail_price': int(text)})
                bot.send_message(chat_id, f"✅ Old Price {text} BDT Set")
                del user_states[user_id] # Reply দিয়েই Clear
                bot.send_message(chat_id, "Admin Panel", reply_markup=admin_menu())

            elif state['state'] == 'set_min':
                db.collection('settings').document('config').update({'min_withdraw': int(text)})
                bot.send_message(chat_id, f"✅ Min Withdraw {text} BDT Set")
                del user_states[user_id] # Reply দিয়েই Clear
                bot.send_message(chat_id, "Admin Panel", reply_markup=admin_menu())

            elif state['state'] == 'send_noti':
                users = db.collection('users').get()
                for u in users:
                    try: bot.send_message(u.id, f"📢 {text}")
                    except: pass
                bot.send_message(chat_id, f"✅ Notification Sent")
                del user_states[user_id] # Reply দিয়েই Clear
                bot.send_message(chat_id, "Admin Panel", reply_markup=admin_menu())
        except Exception as e:
            bot.send_message(chat_id, f"Error: {e}")
            del user_states[user_id]

    # ========== OLD GMAIL FLOW FIX ==========
    elif user_id in user_temp and user_temp[user_id]['type']=='old':
        if user_temp[user_id]['step'] == 'email':
            user_temp[user_id]['email'] = text
            bot.send_message(chat_id, "Step 2/2\nPassword দাও:")
            user_temp[user_id]['step'] = 'pass'
        elif user_temp[user_id]['step'] == 'pass': # এখানেই Reply আটকাতো
            user_temp[user_id]['pass'] = text
            settings = get_settings()
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✅ Submit Old Gmail", callback_data="submit_old"))
            bot.send_message(chat_id, f"Gmail: {user_temp[user_id]['email']}\nPrice: {settings['old_gmail_price']} BDT", reply_markup=markup)
            # এখানে State Clear করবা না, Submit চাপার পর Clear হবে

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    user_id = str(call.from_user.id)
    settings = get_settings()

    if call.data == "submit_old":
        data = user_temp[user_id]
        user_ref = db.collection('users').document(user_id)
        user_ref.update({'hold': firestore.Increment(settings['old_gmail_price'])})
        pending_id = str(time.time())
        db.collection('pending').document(pending_id).set({
            'user_id': user_id, 'email': data['email'], 'pass': data['pass'], 'price': settings['old_gmail_price'], 'type':'old'
        })
        bot.send_message(call.message.chat.id, f"✅ Submit! {settings['old_gmail_price']} BDT Hold এ গেছে।")
        del user_temp[user_id] # Submit এর পর Clear

    elif call.data == "submit_new":
        gmail = user_temp[user_id]['data']
        user_ref = db.collection('users').document(user_id)
        user_ref.update({'hold': firestore.Increment(gmail['price'])})
        pending_id = str(time.time())
        db.collection('pending').document(pending_id).set({
            'user_id': user_id, 'email': gmail['email'], 'pass': gmail['pass'], 'price': gmail['price'], 'type':'new'
        })
        db.collection('gmail_stock').document(gmail['email']).delete()
        bot.send_message(call.message.chat.id, f"✅ Submit! {gmail['price']} BDT Hold এ গেছে।")
        del user_temp[user_id]

print("Bot Running...")
bot.infinity_polling(timeout=180, long_polling_timeout=180)
