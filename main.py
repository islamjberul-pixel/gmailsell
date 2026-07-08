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

# Firebase Connect
firebase_json = os.getenv("FIREBASE_KEY")
cred_dict = json.loads(firebase_json)
cred = credentials.Certificate(cred_dict)
firebase_admin.initialize_app(cred)
db = firestore.client()

bot = telebot.TeleBot(TOKEN)
user_temp = {}
user_states = {}
CURRENCY = {"BDT":1, "USD":0.0092, "INR":0.76}

# Settings Doc
def get_settings():
    ref = db.collection('settings').document('config').get()
    if not ref.exists:
        db.collection('settings').document('config').set({
            'new_gmail_price': 12,
            'old_gmail_price': 6,
            'min_withdraw': 25,
            'empty_stock_msg': 'Stock Empty! Admin বলেছে: শীঘ্রই Stock আসবে'
        })
        return {'new_gmail_price': 12, 'old_gmail_price': 6, 'min_withdraw': 25, 'empty_stock_msg': 'Stock Empty! Admin বলেছে: শীঘ্রই Stock আসবে'}
    return ref.to_dict()

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
    user = user_ref.get().to_dict()
    if user.get('blocked', False):
        bot.send_message(message.chat.id, "🚫 তুমি Blocked. Admin: wa.me/"+ADMIN_WHATSAPP)
        return
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
    user = user_doc.to_dict()

    if user.get('blocked', False):
        bot.send_message(chat_id, "🚫 তুমি Blocked")
        return

    # Global Back Button
    if text in ["⬅️ Back", "🔙 Back", "Cancel"]:
        if user_id in user_temp: del user_temp[user_id]
        if user_id in user_states: del user_states[user_id]
        bot.send_message(chat_id, "Main Menu", reply_markup=main_menu())
        return

    # ========== USER PANEL ==========
    if text == "💰 Balance":
        rate = CURRENCY[user['currency']]
        bal = user['balance'] * rate
        submitted = len(user['accounts'])
        bot.send_message(chat_id, f"💰 Main Balance: {bal:.2f} {user['currency']}\n⏳ Hold: {user['hold']} BDT\n📧 Total Submitted: {submitted} Gmail", reply_markup=main_menu())

    elif text == "⏳ Balance Hold":
        bot.send_message(chat_id, f"⏳ Hold Balance: {user['hold']} BDT\nAdmin Approve করলে Main Balance এ Add হবে", reply_markup=main_menu())

    elif text == "📁 My accounts":
        if not user['accounts']: bot.send_message(chat_id, "এখনো কোনো Account নাই", reply_markup=main_menu())
        else:
            msg = "📁 তোমার Accounts:\n\n"
            for acc in user['accounts']: msg += f"📧 {acc['email']}\n💰 {acc['price']} BDT\nStatus: {acc['status']}\n\n"
            bot.send_message(chat_id, msg, reply_markup=main_menu())

    elif text == "⚙️ Settings":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("BDT", "USD", "INR")
        markup.add("⬅️ Back")
        bot.send_message(chat_id, "Currency Select করো:", reply_markup=markup)

    elif text in CURRENCY:
        user_ref.update({'currency': text})
        bot.send_message(chat_id, f"✅ Currency {text} Set", reply_markup=main_menu())

    elif text == "💸 Withdraw":
        if user['balance'] < settings['min_withdraw']:
            bot.send_message(chat_id, f"Balance কম। Min {settings['min_withdraw']} BDT লাগবে", reply_markup=main_menu()); return
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Bkash", callback_data="wd_bkash"))
        markup.add(types.InlineKeyboardButton("Nagad", callback_data="wd_nagad"))
        markup.add(types.InlineKeyboardButton("USDT BEP20", callback_data="wd_usdt"))
        markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="back_menu"))
        bot.send_message(chat_id, f"Min Withdraw: {settings['min_withdraw']} BDT\nCharge: 3%", reply_markup=markup)

    elif text == "➕ Register a new Gmail":
        stock_ref = db.collection('gmail_stock').limit(20).get()
        stock = [doc.to_dict() for doc in stock_ref]
        if not stock: bot.send_message(chat_id, settings['empty_stock_msg'], reply_markup=main_menu()); return
        gmail = random.choice(stock)
        user_temp[user_id] = {'type':'new', 'data':gmail}
        msg = f"""নতুন Gmail:
👤 Name: {gmail['first_name']} {gmail['last_name']}
📧 Email: `{gmail['email']}`
🔑 Password: `{gmail['pass']}`
💰 Price: {gmail['price']} BDT
এই Info দিয়ে Gmail খুলে Submit করো"""
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Submit", callback_data="submit_new"))
        bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=markup)

    elif text == "📦 Old Gmail Sell":
        bot.send_message(chat_id, "Step 1/2\nOld Gmail টা দাও @gmail.com সহ:\n\n⬅️ Back লিখলে Menu")
        user_temp[user_id] = {'type':'old', 'step':'email'}

    # ========== ADMIN PANEL ==========
    elif text == "👑 Admin Panel":
        if user_id == str(ADMIN_ID):
            bot.send_message(chat_id, "👑 Admin Panel", reply_markup=admin_menu())
        else:
            bot.send_message(chat_id, "তুমি Admin না", reply_markup=main_menu())

    elif text == "📧 Pending Gmail" and user_id == str(ADMIN_ID):
        pending_ref = db.collection('pending').get()
        if len(pending_ref) == 0: bot.send_message(chat_id, "কোনো Pending নাই", reply_markup=admin_menu())
        else:
            for doc in pending_ref:
                data = doc.to_dict()
                msg = f"ID: {doc.id}\nUser: {data['user_id']}\nEmail: {data['email']}\nPrice: {data['price']} BDT\nType: {data['type']}"
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{doc.id}"))
                markup.add(types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_{doc.id}"))
                bot.send_message(chat_id, msg, reply_markup=markup)

    elif text == "💸 Pending Withdraw" and user_id == str(ADMIN_ID):
        wd_ref = db.collection('withdraws').where('status', '==', 'Pending').get()
        if len(wd_ref) == 0: bot.send_message(chat_id, "কোনো Pending Withdraw নাই", reply_markup=admin_menu())
        else:
            for doc in wd_ref:
                data = doc.to_dict()
                msg = f"ID: {doc.id}\nUser: {data['user_id']}\nAmount: {data['amount']}\nMethod: {data['method']}\nNumber: {data['number']}"
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("✅ Paid", callback_data=f"paid_{doc.id}"))
                bot.send_message(chat_id, msg, reply_markup=markup)

    elif text == "👥 All Users" and user_id == str(ADMIN_ID):
        users = db.collection('users').get()
        bot.send_message(chat_id, f"Total Users: {len(users)}", reply_markup=admin_menu())

    elif text == "📋 Stock List" and user_id == str(ADMIN_ID):
        stock_ref = db.collection('gmail_stock').get()
        if len(stock_ref) == 0: bot.send_message(chat_id, "Stock Empty", reply_markup=admin_menu())
        else:
            msg = "📋 Stock List:\n\n"
            i = 1
            for doc in stock_ref:
                data = doc.to_dict()
                msg += f"{i}_ {data['first_name']} {data['last_name']} | {data['email']} | {data['pass']} | {data['price']} BDT\n\n"
                i += 1
                if i > 50: msg += "...আরো আছে"; break
            bot.send_message(chat_id, msg, reply_markup=admin_menu())

    elif text == "📊 Stats" and user_id == str(ADMIN_ID):
        users = len(list(db.collection('users').get()))
        stock = len(list(db.collection('gmail_stock').get()))
        pending = len(list(db.collection('pending').get()))
        bot.send_message(chat_id, f"📊 Stats:\nTotal User: {users}\nStock: {stock}\nPending: {pending}\nNew Gmail: {settings['new_gmail_price']} BDT\nOld Gmail: {settings['old_gmail_price']} BDT\nMin Withdraw: {settings['min_withdraw']} BDT", reply_markup=admin_menu())

    elif text == "➕ Add Gmail Stock" and user_id == str(ADMIN_ID):
        bot.send_message(chat_id, "Step 1/4\nFirst Name লিখো:\n\nCancel লিখলে বাদ যাবে")
        user_states[user_id] = {'state':'add_stock', 'step':'first_name', 'data':{}}

    elif text == "💰 Set New Gmail Price" and user_id == str(ADMIN_ID):
        bot.send_message(chat_id, f"Current New Gmail Price: {settings['new_gmail_price']} BDT\nনতুন দাম লিখো:")
        user_states[user_id] = {'state':'set_new_price'}

    elif text == "📦 Set Old Gmail Price" and user_id == str(ADMIN_ID):
        bot.send_message(chat_id, f"Current Old Gmail Price: {settings['old_gmail_price']} BDT\nনতুন দাম লিখো:")
        user_states[user_id] = {'state':'set_old_price'}

    elif text == "⚙️ Set Min Withdraw" and user_id == str(ADMIN_ID):
        bot.send_message(chat_id, f"Current Min: {settings['min_withdraw']} BDT\nনতুন Min Withdraw লিখো:")
        user_states[user_id] = {'state':'set_min'}

    elif text == "🚫 Block User" and user_id == str(ADMIN_ID):
        bot.send_message(chat_id, "যাকে Block করবা তার User ID দাও:\n\nCancel লিখলে বাদ")
        user_states[user_id] = {'state':'block_user'}

    elif text == "📢 Send Notification" and user_id == str(ADMIN_ID):
        bot.send_message(chat_id, "সবাইকে যে Notification পাঠাবা সেটা লিখো:\n\nCancel লিখলে বাদ")
        user_states[user_id] = {'state':'send_noti'}

    # ========== STATE HANDLER ==========
    elif user_id in user_states:
        state = user_states[user_id]

        if text.lower() == "cancel":
            del user_states[user_id]
            bot.send_message(chat_id, "Cancel করা হয়েছে", reply_markup=admin_menu())
            return

        if state['state'] == 'add_stock':
            if state['step'] == 'first_name':
                state['data']['first_name'] = text
                bot.send_message(chat_id, "Step 2/4\nLast Name লিখো:")
                state['step'] = 'last_name'
            elif state['step'] == 'last_name':
                state['data']['last_name'] = text
                bot.send_message(chat_id, "Step 3/4\nEmail লিখো @gmail.com সহ:")
                state['step'] = 'email'
            elif state['step'] == 'email':
                if not re.match(r"[^@]+@gmail\.com", text):
                    bot.send_message(chat_id, "❌ ভুল Format। @gmail.com সহ দাও")
                    return
                state['data']['email'] = text
                bot.send_message(chat_id, "Step 4/4\nPassword লিখো:")
                state['step'] = 'password'
            elif state['step'] == 'password':
                state['data']['pass'] = text
                settings = get_settings()
                db.collection('gmail_stock').document(state['data']['email']).set({
                    'email':state['data']['email'],
                    'pass':state['data']['pass'],
                    'first_name':state['data']['first_name'],
                    'last_name':state['data']['last_name'],
                    'price':settings['new_gmail_price']
                })
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                markup.add("✅ Complete & Add Another", "🔙 Back")
                bot.send_message(chat_id, f"✅ Stock Add: {state['data']['email']}\n\nআরো Add করবা?", reply_markup=markup)
                state['step'] = 'complete'

        elif state['step'] == 'complete':
            if text == "✅ Complete & Add Another":
                bot.send_message(chat_id, "Step 1/4\nFirst Name লিখো:")
                state['step'] = 'first_name'
                state['data'] = {}
            else:
                del user_states[user_id]
                bot.send_message(chat_id, "Done", reply_markup=admin_menu())

        elif state['state'] == 'set_new_price':
            try:
                db.collection('settings').document('config').update({'new_gmail_price': int(text)})
                bot.send_message(chat_id, f"✅ New Gmail Price {text} BDT Set", reply_markup=admin_menu())
            except: bot.send_message(chat_id, "শুধু নাম্বার দাও")
            del user_states[user_id]

        elif state['state'] == 'set_old_price':
            try:
                db.collection('settings').document('config').update({'old_gmail_price': int(text)})
                bot.send_message(chat_id, f"✅ Old Gmail Price {text} BDT Set", reply_markup=admin_menu())
            except: bot.send_message(chat_id, "শুধু নাম্বার দাও")
            del user_states[user_id]

        elif state['state'] == 'set_min':
            try:
                db.collection('settings').document('config').update({'min_withdraw': int(text)})
                bot.send_message(chat_id, f"✅ Min Withdraw {text} BDT Set", reply_markup=admin_menu())
            except: bot.send_message(chat_id, "শুধু নাম্বার দাও")
            del user_states[user_id]

        elif state['state'] == 'block_user':
            db.collection('users').document(text).update({'blocked': True})
            bot.send_message(chat_id, f"✅ User {text} Blocked", reply_markup=admin_menu())
            del user_states[user_id]

        elif state['state'] == 'send_noti':
            users = db.collection('users').get()
            count = 0
            for u in users:
                try:
                    bot.send_message(u.id, f"📢 Notification:\n\n{text}")
                    count += 1
                except: pass
            bot.send_message(chat_id, f"✅ {count} জনকে Notification পাঠানো হয়েছে", reply_markup=admin_menu())
            del user_states[user_id]

    # ========== OLD GMAIL FLOW ==========
    elif user_id in user_temp and user_temp[user_id]['type']=='old':
        if user_temp[user_id]['step'] == 'email':
            if not re.match(r"[^@]+@gmail\.com", text):
                bot.send_message(chat_id, "❌ ভুল Format। @gmail.com সহ পুরা Gmail দাও")
                return
            user_temp[user_id]['email'] = text
            bot.send_message(chat_id, "Step 2/2\nPassword দাও:\n\nCancel লিখলে বাদ")
            user_temp[user_id]['step'] = 'pass'
        elif user_temp[user_id]['step'] == 'pass':
            user_temp[user_id]['pass'] = text
            settings = get_settings()
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✅ Submit Old Gmail", callback_data="submit_old"))
            markup.add(types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_old"))
            bot.send_message(chat_id, f"Gmail: {user_temp[user_id]['email']}\nPrice: {settings['old_gmail_price']} BDT", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    user_id = str(call.from_user.id)
    settings = get_settings()
    user_ref = db.collection('users').document(user_id)
    user_doc = user_ref.get()
    if not user_doc.exists: return
    user = user_doc.to_dict()

    if call.data == "back_menu":
        bot.send_message(call.message.chat.id, "Main Menu", reply_markup=main_menu())
        return

    if call.data == "cancel_old":
        if user_id in user_temp: del user_temp[user_id]
        bot.send_message(call.message.chat.id, "Cancel", reply_markup=main_menu())
        return

    if "wd_" in call.data:
        method = call.data.split("_")[1]
        msg = bot.send_message(call.message.chat.id, f"Amount লিখো Min {settings['min_withdraw']}")
        user_temp[user_id] = {'type':'withdraw', 'method':method}
        bot.register_next_step_handler(msg, get_amount)

    elif call.data == "submit_new":
        gmail = user_temp[user_id]['data']
        pending_id = str(time.time())
        user_ref.update({'hold': firestore.Increment(gmail['price'])})
        db.collection('pending').document(pending_id).set({
            'user_id': user_id, 'email': gmail['email'], 'pass': gmail['pass'], 'price': gmail['price'], 'type':'new'
        })
        db.collection('gmail_stock').document(gmail['email']).delete()
        bot.send_message(call.message.chat.id, f"✅ Submit! {gmail['price']} BDT Hold এ চলে গেছে।")
        del user_temp[user_id]

    elif call.data == "submit_old":
        data = user_temp[user_id]
        settings = get_settings()
        pending_id = str(time.time())
        user_ref.update({'hold': firestore.Increment(settings['old_gmail_price'])})
        db.collection('pending').document(pending_id).set({
            'user_id': user_id, 'email': data['email'], 'pass': data['pass'], 'price': settings['old_gmail_price'], 'type':'old'
        })
        bot.send_message(call.message.chat.id, f"✅ Submit! {settings['old_gmail_price']} BDT Hold এ চলে গেছে।")
        del user_temp[user_id]

    # ADMIN APPROVE/REJECT
    elif "approve_" in call.data and user_id == str(ADMIN_ID):
        pending_id = call.data.split("_")[1]
        data = db.collection('pending').document(pending_id).get().to_dict()
        u_ref = db.collection('users').document(data['user_id'])
        u = u_ref.get().to_dict()
        u_ref.update({'hold': u['hold'] - data['price'], 'balance': firestore.Increment(data['price'])})
        u['accounts'].append({'email':data['email'],'pass':data['pass'],'price':data['price'],'status':'Approved'})
        u_ref.update({'accounts': u['accounts']})
        db.collection('pending').document(pending_id).delete()
        bot.send_message(call.message.chat.id, f"✅ Approved. {data['price']} BDT Main Balance এ গেছে")
        bot.send_message(data['user_id'], f"✅ তোমার {data['email']} Approve হয়েছে। {data['price']} BDT Main Balance এ Add হয়েছে")

    elif "reject_" in call.data and user_id == str(ADMIN_ID):
        pending_id = call.data.split("_")[1]
        data = db.collection('pending').document(pending_id).get().to_dict()
        u_ref = db.collection('users').document(data['user_id'])
        u = u_ref.get().to_dict()
        u_ref.update({'hold': u['hold'] - data['price']})
        db.collection('pending').document(pending_id).delete()
        bot.send_message(call.message.chat.id, "❌ Rejected. Hold থেকে টাকা কাটা হয়েছে")
        bot.send_message(data['user_id'], f"❌ তোমার {data['email']} Reject হয়েছে। {data['price']} BDT Hold থেকে কাটা হয়েছে")

    elif "paid_" in call.data and user_id == str(ADMIN_ID):
        db.collection('withdraws').document(call.data.split("_")[1]).update({'status':'Paid'})
        bot.send_message(call.message.chat.id, "✅ Withdraw Paid Marked")

def get_amount(message):
    user_id = str(message.from_user.id)
    settings = get_settings()
    try:
        amount = float(message.text)
        if amount < settings['min_withdraw']: bot.send_message(message.chat.id, f"Min {settings['min_withdraw']}"); return
        charge = amount * 0.03
        bot.send_message(message.chat.id, f"Amount: {amount}\nCharge: {charge:.2f}\nNumber দাও:")
        user_temp[user_id]['amount'] = amount
        bot.register_next_step_handler(message, get_number)
    except:
        bot.send_message(message.chat.id, "ভুল Amount")
        if user_id in user_temp: del user_temp[user_id]

def get_number(message):
    user_id = str(message.from_user.id)
    if user_id not in user_temp: return
    data = user_temp[user_id]
    db.collection('withdraws').add({'user_id':user_id,'amount':data['amount'],'method':data['method'],'number':message.text,'status':'Pending'})
    db.collection('users').document(user_id).update({'balance': firestore.Increment(-data['amount'])})
    bot.send_message(message.chat.id, f"✅ Withdraw Pending. 48 ঘন্টায় Complete হবে", reply_markup=main_menu())
    bot.send_message(message.chat.id, f"https://wa.me/{ADMIN_WHATSAPP}?text=Withdraw {data['amount']} to {message.text}")
    del user_temp[user_id]

print("Bot Running...")
bot.infinity_polling(timeout=180, long_polling_timeout=180)
