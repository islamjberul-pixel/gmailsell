import telebot
import random
import firebase_admin
from firebase_admin import credentials, firestore
from telebot import types
import time

TOKEN = "8850356807:AAEwHB5mxxTPmuOAu8K-6-qZnII2f20_rsQ"
ADMIN_ID = 7602082599 # এখানে তোমার Telegram User ID বসাও
ADMIN_WHATSAPP = "8801796103936"

# Firebase Connect
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

bot = telebot.TeleBot(TOKEN)
user_temp = {}
user_states = {}
CURRENCY = {"BDT":1, "USD":0.0092, "INR":0.76}

def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("➕ Register a new Gmail")
    markup.add("📁 My accounts", "💰 Balance")
    markup.add("💸 Withdraw", "⏳ Balance Hold")
    markup.add("📦 Old Gmail Sell", "⚙️ Settings")
    markup.add("👑 Admin Panel") # সবাই দেখবে, ভিতরে Check হবে
    return markup

def admin_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("➕ Add Gmail Stock", "👥 All Users")
    markup.add("💸 Pending Withdraw", "📧 Pending Gmail")
    markup.add("🔙 Back")
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    user_id = str(message.from_user.id)
    user_ref = db.collection('users').document(user_id)
    if not user_ref.get().exists:
        user_ref.set({'balance':0, 'hold':0, 'accounts':[], 'currency':'BDT'})
    bot.send_message(message.chat.id, "Welcome to BK71 CLUB Bot!", reply_markup=main_menu())

@bot.message_handler(func=lambda m: True)
def handler(message):
    user_id = str(message.from_user.id)
    chat_id = message.chat.id
    text = message.text
    user_ref = db.collection('users').document(user_id)
    user = user_ref.get().to_dict() if user_ref.get().exists else None

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
        markup.add("BDT", "USD", "INR", "⬅️ Back")
        bot.send_message(chat_id, "Currency Select করো:", reply_markup=markup)

    elif text in CURRENCY:
        user_ref.update({'currency': text})
        bot.send_message(chat_id, f"✅ Currency {text} Set", reply_markup=main_menu())

    elif text == "⬅️ Back":
        bot.send_message(chat_id, "Main Menu", reply_markup=main_menu())

    elif text == "💸 Withdraw":
        if user['balance'] < 25: 
            bot.send_message(chat_id, "Balance কম। Min 25 BDT লাগবে", reply_markup=main_menu()); return
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Bkash", callback_data="wd_bkash"))
        markup.add(types.InlineKeyboardButton("Nagad", callback_data="wd_nagad"))
        markup.add(types.InlineKeyboardButton("USDT BEP20", callback_data="wd_usdt"))
        bot.send_message(chat_id, "Min Withdraw: 25 BDT\nCharge: 3%", reply_markup=markup)

    elif text == "➕ Register a new Gmail":
        stock_ref = db.collection('gmail_stock').limit(20).get()
        stock = [doc.to_dict() for doc in stock_ref]
        if not stock: bot.send_message(chat_id, "Stock Empty! Admin কে জানাও", reply_markup=main_menu()); return
        gmail = random.choice(stock)
        user_temp[user_id] = {'type':'new', 'data':gmail}
        msg = f"""নতুন Gmail:
👤 Name: {gmail['name']}
📧 Email: `{gmail['email']}`
🔑 Password: `{gmail['pass']}`
💰 Price: {gmail['price']} BDT
এই Info দিয়ে Gmail খুলে Submit করো"""
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Submit", callback_data="submit_new"))
        bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=markup)

    elif text == "📦 Old Gmail Sell":
        bot.send_message(chat_id, "Step 1/2\nOld Gmail টা দাও:")
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

    elif text == "➕ Add Gmail Stock" and user_id == str(ADMIN_ID):
        bot.send_message(chat_id, "Format: email|password|name|price\nExample: abc@gmail.com|123|Abc|12")
        user_states[user_id] = 'add_stock'

    elif user_id in user_states and user_states[user_id] == 'add_stock':
        try:
            email, password, name, price = text.split('|')
            db.collection('gmail_stock').document(email).set({'email':email,'pass':password,'name':name,'price':int(price)})
            bot.send_message(chat_id, f"✅ Stock Add: {email}", reply_markup=admin_menu())
        except:
            bot.send_message(chat_id, "Format ভুল। email|password|name|price", reply_markup=admin_menu())
        user_states[user_id] = None

    elif text == "🔙 Back":
        bot.send_message(chat_id, "Main Menu", reply_markup=main_menu())

    # ========== OLD GMAIL FLOW ==========
    elif user_id in user_temp and user_temp[user_id]['type']=='old':
        if user_temp[user_id]['step'] == 'email':
            user_temp[user_id]['email'] = text
            bot.send_message(chat_id, "Step 2/2\nPassword দাও:")
            user_temp[user_id]['step'] = 'pass'
        elif user_temp[user_id]['step'] == 'pass':
            user_temp[user_id]['pass'] = text
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✅ Submit Old Gmail", callback_data="submit_old"))
            bot.send_message(chat_id, f"Gmail: {user_temp[user_id]['email']}\nPrice: 6 BDT", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    user_id = str(call.from_user.id)
    user_ref = db.collection('users').document(user_id)
    user = user_ref.get().to_dict()

    if "wd_" in call.data:
        method = call.data.split("_")[1]
        msg = bot.send_message(call.message.chat.id, "Amount লিখো Min 25")
        user_temp[user_id] = {'type':'withdraw', 'method':method}
        bot.register_next_step_handler(msg, get_amount)

    elif call.data == "submit_new":
        gmail = user_temp[user_id]['data']
        pending_id = str(time.time())
        db.collection('pending').document(pending_id).set({
            'user_id': user_id, 'email': gmail['email'], 'pass': gmail['pass'], 'price': gmail['price'], 'type':'new'
        })
        db.collection('gmail_stock').document(gmail['email']).delete()
        bot.send_message(call.message.chat.id, "✅ Submit! Admin Approve করলে Balance Hold এ যাবে")
        del user_temp[user_id]

    elif call.data == "submit_old":
        data = user_temp[user_id]
        pending_id = str(time.time())
        db.collection('pending').document(pending_id).set({
            'user_id': user_id, 'email': data['email'], 'pass': data['pass'], 'price': 6, 'type':'old'
        })
        bot.send_message(call.message.chat.id, "✅ Submit! Admin Approve করলে 6 BDT Hold এ যাবে")
        del user_temp[user_id]

    # ADMIN APPROVE/REJECT
    elif "approve_" in call.data and user_id == str(ADMIN_ID):
        pending_id = call.data.split("_")[1]
        data = db.collection('pending').document(pending_id).get().to_dict()
        u_ref = db.collection('users').document(data['user_id'])
        u = u_ref.get().to_dict()
        u_ref.update({'hold': u['hold'] + data['price']})
        u['accounts'].append({'email':data['email'],'pass':data['pass'],'price':data['price'],'status':'Hold'})
        u_ref.update({'accounts': u['accounts']})
        db.collection('pending').document(pending_id).delete()
        bot.send_message(call.message.chat.id, f"✅ Approved. {data['price']} BDT Hold এ গেছে")
        bot.send_message(data['user_id'], f"✅ তোমার {data['email']} Approve হয়েছে। {data['price']} BDT Hold এ আছে")

    elif "reject_" in call.data and user_id == str(ADMIN_ID):
        db.collection('pending').document(call.data.split("_")[1]).delete()
        bot.send_message(call.message.chat.id, "❌ Rejected")

    elif "paid_" in call.data and user_id == str(ADMIN_ID):
        db.collection('withdraws').document(call.data.split("_")[1]).update({'status':'Paid'})
        bot.send_message(call.message.chat.id, "✅ Withdraw Paid Marked")

def get_amount(message):
    user_id = str(message.from_user.id)
    try:
        amount = float(message.text)
        if amount < 25: bot.send_message(message.chat.id, "Min 25"); return
        charge = amount * 0.03
        bot.send_message(message.chat.id, f"Amount: {amount}\nCharge: {charge}\nNumber দাও:")
        user_temp[user_id]['amount'] = amount
        bot.register_next_step_handler(message, get_number)
    except: bot.send_message(message.chat.id, "ভুল Amount")

def get_number(message):
    user_id = str(message.from_user.id)
    data = user_temp[user_id]
    db.collection('withdraws').add({'user_id':user_id,'amount':data['amount'],'method':data['method'],'number':message.text,'status':'Pending'})
    db.collection('users').document(user_id).update({'balance': firestore.Increment(-data['amount'])})
    bot.send_message(message.chat.id, f"✅ Withdraw Pending. 48 ঘন্টায় Complete হবে", reply_markup=main_menu())
    bot.send_message(message.chat.id, f"https://wa.me/{ADMIN_WHATSAPP}?text=Withdraw {data['amount']} to {message.text}")
    del user_temp[user_id]

print("Bot Running...")
while True:
    try:
        bot.infinity_polling(timeout=180, long_polling_timeout=180)
    except Exception as e:
        print("Error:", e)
        print("5 সেকেন্ড পর আবার চালু হচ্ছে...")
        time.sleep(5)
