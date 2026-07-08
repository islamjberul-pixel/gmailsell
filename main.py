import telebot
from telebot import types
import firebase_admin
from firebase_admin import credentials, firestore
import os
import random
import uuid
import datetime
import json

TOKEN = os.getenv('TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
FIREBASE_KEY = os.getenv('FIREBASE_KEY')

if not TOKEN or not FIREBASE_KEY:
    print("Missing environment variables!")
    exit(1)

# Firebase Init
if not firebase_admin._apps:
    try:
        cred_dict = json.loads(FIREBASE_KEY)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        print(f"Firebase init error: {e}")
        exit(1)

db = firestore.client()
bot = telebot.TeleBot(TOKEN)

user_states = {}
user_temp = {}

def get_settings():
    settings_ref = db.collection('settings').document('config')
    settings = settings_ref.get()
    if settings.exists:
        return settings.to_dict()
    else:
        default_settings = {'new_gmail_price': 12, 'old_gmail_price': 6, 'min_withdraw': 25}
        settings_ref.set(default_settings)
        return default_settings

def save_settings(settings):
    db.collection('settings').document('config').set(settings)

def get_user_data(user_id):
    user_ref = db.collection('users').document(str(user_id))
    user = user_ref.get()
    if not user.exists:
        user_data = {'balance': 0.0, 'hold': 0.0, 'accounts': [], 'currency': 'BDT', 'blocked': False, 'submitted_count': 0}
        user_ref.set(user_data)
        return user_data
    return user.to_dict()

def update_user_data(user_id, data):
    db.collection('users').document(str(user_id)).update(data)

def is_admin(user_id):
    return user_id == ADMIN_ID

def create_main_keyboard(is_admin_user=False):
    keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    keyboard.add('➕ Register a new Gmail', '📦 Old Gmail Sell')
    keyboard.add('💰 Balance', '⏳ Balance Hold')
    keyboard.add('📁 My accounts', '💸 Withdraw')
    keyboard.add('⚙️ Settings')
    if is_admin_user:
        keyboard.add('👑 Admin Panel')
    return keyboard

def create_back_keyboard():
    keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    keyboard.add('⬅️ Back', 'Cancel')
    return keyboard

def clear_user_state(user_id):
    user_states.pop(user_id, None)
    user_temp.pop(user_id, None)

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    clear_user_state(user_id)
    user_data = get_user_data(user_id)
    if user_data.get('blocked', False):
        bot.reply_to(message, "🚫 You are blocked by admin.")
        return
    bot.reply_to(message, "👋 Welcome to Gmail Buy Sell Bot!", reply_markup=create_main_keyboard(is_admin(user_id)))

# EKTAI MESSAGE HANDLER - FIX 1
@bot.message_handler(content_types=['text'])
def handle_all(message):
    user_id = message.from_user.id
    text = message.text.strip()
    user_data = get_user_data(user_id)

    if user_data.get('blocked', False) and not is_admin(user_id):
        bot.reply_to(message, "🚫 You are blocked.")
        return

    settings = get_settings()

    if text in ['⬅️ Back', 'Cancel']:
        clear_user_state(user_id)
        bot.reply_to(message, "✅ Cancelled", reply_markup=create_main_keyboard(is_admin(user_id)))
        return

    # Admin Panel Button
    if text == '👑 Admin Panel' and is_admin(user_id):
        show_admin_panel(message)
        return

    # Admin States First
    if is_admin(user_id) and user_id in user_states:
        handle_admin_state(message, user_states[user_id], user_id, text, settings)
        return

    # User States
    if user_id in user_states:
        handle_state(message, user_states[user_id], user_id, text, settings)
        return

    # Main Menu
    if text == '➕ Register a new Gmail':
        register_new_gmail(message, user_id)
    elif text == '📦 Old Gmail Sell':
        start_old_gmail_sell(message, user_id)
    elif text == '💰 Balance':
        show_balance(message, user_data)
    elif text == '⏳ Balance Hold':
        bot.reply_to(message, f"⏳ Hold: {user_data.get('hold', 0)} BDT")
    elif text == '📁 My accounts':
        show_my_accounts(message, user_id)
    elif text == '💸 Withdraw':
        start_withdraw(message, user_id)
    elif text == '⚙️ Settings':
        user_states[user_id] = 'change_currency'
        bot.reply_to(message, "💱 Send BDT/USD/INR:", reply_markup=create_back_keyboard())
    else:
        bot.reply_to(message, "❓ Select from menu", reply_markup=create_main_keyboard(is_admin(user_id)))

def handle_state(message, state, user_id, text, settings):
    try:
        if state == 'old_email':
            user_temp[user_id] = {'old_email': text}
            user_states[user_id] = 'old_pass'
            bot.reply_to(message, "🔑 Send Password:", reply_markup=create_back_keyboard())

        elif state == 'old_pass': # FIX 3: এখানে Clear করবা না
            temp = user_temp.get(user_id, {})
            email = temp.get('old_email')
            price = settings.get('old_gmail_price', 6)
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton('✅ Submit Old Gmail', callback_data=f'submit_old_{user_id}'))
            bot.reply_to(message, f"📧 {email}\n🔑 {text}\n💰 {price} BDT", reply_markup=markup)
            user_temp[user_id]['old_pass'] = text
            user_temp[user_id]['old_price'] = price
            # clear_user_state(user_id) <-- এটা বাদ

        elif state == 'withdraw_method':
            user_temp[user_id] = {'withdraw_method': text}
            user_states[user_id] = 'withdraw_number'
            bot.reply_to(message, "📱 Enter Number:", reply_markup=create_back_keyboard())

        elif state == 'withdraw_number':
            user_temp[user_id]['withdraw_number'] = text
            user_states[user_id] = 'withdraw_amount'
            bot.reply_to(message, f"💰 Enter Amount Min: {settings.get('min_withdraw', 25)}:", reply_markup=create_back_keyboard())

        elif state == 'withdraw_amount':
            amount = float(text)
            user_data = get_user_data(user_id)
            if amount < settings.get('min_withdraw', 25) or amount > user_data.get('balance', 0):
                bot.reply_to(message, "❌ Invalid amount")
                clear_user_state(user_id)
                return
            temp = user_temp[user_id]
            wid = str(uuid.uuid4())[:8]
            db.collection('withdraws').document(wid).set({
                'id': wid, 'user_id': user_id, 'amount': amount, 'method': temp['withdraw_method'],
                'number': temp['withdraw_number'], 'status': 'Pending', 'timestamp': datetime.datetime.utcnow().isoformat()
            })
            update_user_data(user_id, {'balance': user_data['balance'] - amount})
            bot.reply_to(message, f"✅ Withdraw Pending. ID: {wid}")
            clear_user_state(user_id)

        elif state == 'change_currency':
            if text.upper() in ['BDT', 'USD', 'INR']:
                update_user_data(user_id, {'currency': text.upper()})
                bot.reply_to(message, f"✅ Currency: {text.upper()}")
            clear_user_state(user_id)
    except Exception as e:
        bot.reply_to(message, "❌ Error")
        clear_user_state(user_id)

def handle_admin_state(message, state, user_id, text, settings):
    try:
        if state == 'add_first_name':
            user_temp[user_id] = {'first_name': text}
            user_states[user_id] = 'add_last_name'
            bot.reply_to(message, "2️⃣ Last Name:", reply_markup=create_back_keyboard())
        elif state == 'add_last_name':
            user_temp[user_id]['last_name'] = text
            user_states[user_id] = 'add_email'
            bot.reply_to(message, "3️⃣ Email:", reply_markup=create_back_keyboard())
        elif state == 'add_email':
            user_temp[user_id]['email'] = text
            user_states[user_id] = 'add_pass'
            bot.reply_to(message, "4️⃣ Password:", reply_markup=create_back_keyboard())
        elif state == 'add_pass':
            temp = user_temp[user_id]
            price = settings.get('new_gmail_price', 12)
            db.collection('gmail_stock').document(temp['email']).set({
                'first_name': temp['first_name'], 'last_name': temp['last_name'],
                'email': temp['email'], 'pass': text, 'price': price
            })
            bot.reply_to(message, f"✅ Added: {temp['email']}")
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton('✅ Complete & Add Another', callback_data='add_another'))
            bot.reply_to(message, "Add another?", reply_markup=markup)
            clear_user_state(user_id)

        elif state == 'set_new_price':
            settings['new_gmail_price'] = float(text)
            save_settings(settings)
            bot.reply_to(message, f"✅ New Price: {text}")
            clear_user_state(user_id)
            bot.reply_to(message, "Admin Panel", reply_markup=create_main_keyboard(True))

        elif state == 'set_old_price':
            settings['old_gmail_price'] = float(text)
            save_settings(settings)
            bot.reply_to(message, f"✅ Old Price: {text}")
            clear_user_state(user_id)
            bot.reply_to(message, "Admin Panel", reply_markup=create_main_keyboard(True))

        elif state == 'set_min_withdraw':
            settings['min_withdraw'] = float(text)
            save_settings(settings)
            bot.reply_to(message, f"✅ Min Withdraw: {text}")
            clear_user_state(user_id)
            bot.reply_to(message, "Admin Panel", reply_markup=create_main_keyboard(True))

        elif state == 'block_user':
            update_user_data(int(text), {'blocked': True})
            bot.reply_to(message, f"✅ Blocked: {text}")
            clear_user_state(user_id)

        elif state == 'broadcast':
            for u in db.collection('users').stream():
                try: bot.send_message(u.id, f"📢 {text}")
                except: pass
            bot.reply_to(message, "✅ Sent")
            clear_user_state(user_id)
    except Exception as e:
        bot.reply_to(message, "❌ Error")
        clear_user_state(user_id)

def register_new_gmail(message, user_id):
    stocks = list(db.collection('gmail_stock').stream())
    if not stocks: bot.reply_to(message, "❌ No Stock"); return
    doc = random.choice(stocks)
    data = doc.to_dict()
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('✅ Submit', callback_data=f'submit_new_{doc.id}_{user_id}'))
    bot.reply_to(message, f"👤 {data['first_name']} {data['last_name']}\n📧 {doc.id}\n🔑 {data['pass']}\n💰 {data['price']} BDT", reply_markup=markup)

def start_old_gmail_sell(message, user_id):
    user_states[user_id] = 'old_email'
    bot.reply_to(message, "📧 Send Email:", reply_markup=create_back_keyboard())

def show_balance(message, user_data):
    bot.reply_to(message, f"💰 Main: {user_data['balance']} BDT\n⏳ Hold: {user_data['hold']} BDT")

def show_my_accounts(message, user_id):
    accs = get_user_data(user_id).get('accounts', [])
    if not accs: bot.reply_to(message, "No accounts"); return
    msg = "📁 Your Accounts:\n\n"
    for a in accs: msg += f"📧 {a['email']} | {a['price']} BDT\n"
    bot.reply_to(message, msg)

def start_withdraw(message, user_id):
    if get_user_data(user_id)['balance'] < 25: bot.reply_to(message, "❌ Min 25 BDT"); return
    markup = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
    markup.add('Bkash', 'Nagad', 'USDT BEP20', '⬅️ Back')
    bot.reply_to(message, "💸 Select Method:", reply_markup=markup)
    user_states[user_id] = 'withdraw_method'

def show_admin_panel(message):
    keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    for btn in ['➕ Add Gmail Stock', '📋 Stock List', '📧 Pending Gmail', '💸 Pending Withdraw', '👥 All Users', '🚫 Block User', '💰 Set New Gmail Price', '📦 Set Old Gmail Price', '📢 Send Notification', '⚙️ Set Min Withdraw', '📊 Stats', '🔙 Back']:
        keyboard.add(btn)
    bot.reply_to(message, "👑 Admin Panel", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    data = call.data
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    msg_id = call.message.message_id

    if data.startswith('submit_new_'):
        _, _, email, buyer_id = data.split('_')
        buyer_id = int(buyer_id)
        stock = db.collection('gmail_stock').document(email).get()
        if not stock.exists: return
        sdata = stock.to_dict()
        price = sdata['price']
        pid = str(uuid.uuid4())[:8]
        db.collection('pending').document(pid).set({'id': pid, 'user_id': buyer_id, 'email': email, 'pass': sdata['pass'], 'first_name': sdata['first_name'], 'last_name': sdata['last_name'], 'price': price, 'type': 'new'})
        db.collection('gmail_stock').document(email).delete()
        user_data = get_user_data(buyer_id)
        update_user_data(buyer_id, {'hold': user_data['hold'] + price})
        bot.edit_message_text("✅ Submitted! Wait for approval.", chat_id, msg_id)
        bot.send_message(ADMIN_ID, f"🔔 New Submission: {email}")

    elif data.startswith('submit_old_'):
        temp = user_temp.get(user_id, {})
        pid = str(uuid.uuid4())[:8]
        db.collection('pending').document(pid).set({'id': pid, 'user_id': user_id, 'email': temp['old_email'], 'pass': temp['old_pass'], 'price': temp['old_price'], 'type': 'old'})
        user_data = get_user_data(user_id)
        update_user_data(user_id, {'hold': user_data['hold'] + temp['old_price']})
        bot.edit_message_text("✅ Submitted! Wait for approval.", chat_id, msg_id)
        bot.send_message(ADMIN_ID, f"🔔 Old Gmail: {temp['old_email']}")
        clear_user_state(user_id) # Submit এর পর Clear

    elif data == 'add_another':
        clear_user_state(user_id)
        user_states[user_id] = 'add_first_name'
        bot.send_message(chat_id, "1️⃣ First Name:", reply_markup=create_back_keyboard())

    elif data.startswith('approve_'): # FIX 2: Seller কে টাকা দাও
        pid = data.split('_')[1]
        pdata = db.collection('pending').document(pid).get().to_dict()
        seller_id = pdata['user_id']
        price = pdata['price']
        sdata = get_user_data(seller_id)
        update_user_data(seller_id, {
            'hold': sdata['hold'] - price,
            'balance': sdata['balance'] + price,
            'submitted_count': sdata['submitted_count'] + 1,
            'accounts': sdata['accounts'] + [{'email': pdata['email'], 'price': price, 'status': 'Approved'}]
        })
        db.collection('pending').document(pid).delete()
        bot.edit_message_text("✅ Approved!", chat_id, msg_id)
        bot.send_message(seller_id, f"🎉 Approved! +{price} BDT added")

    elif data.startswith('reject_'):
        pid = data.split('_')[1]
        pdata = db.collection('pending').document(pid).get().to_dict()
        sdata = get_user_data(pdata['user_id'])
        update_user_data(pdata['user_id'], {'hold': sdata['hold'] - pdata['price']})
        db.collection('pending').document(pid).delete()
        bot.edit_message_text("❌ Rejected", chat_id, msg_id)

    elif data.startswith('paid_'):
        db.collection('withdraws').document(data.split('_')[1]).update({'status': 'Paid'})
        bot.edit_message_text("✅ Paid", chat_id, msg_id)

# Admin Button Handler - একই function এর ভিতরে
@bot.message_handler(func=lambda m: is_admin(m.from_user.id))
def admin_buttons(message):
    text = message.text
    user_id = message.from_user.id

    if text == '➕ Add Gmail Stock':
        clear_user_state(user_id)
        user_states[user_id] = 'add_first_name'
        bot.reply_to(message, "1️⃣ First Name:", reply_markup=create_back_keyboard())
    elif text == '📋 Stock List':
        stocks = list(db.collection('gmail_stock').stream())
        msg = "📋 Stock:\n\n"
        for i, s in enumerate(stocks, 1):
            d = s.to_dict()
            msg += f"{i}. {d['first_name']} {d['last_name']} | {s.id}\n"
        bot.reply_to(message, msg)
    elif text == '📧 Pending Gmail':
        for p in db.collection('pending').stream():
            d = p.to_dict()
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton('✅ Approve', callback_data=f'approve_{p.id}'), types.InlineKeyboardButton('❌ Reject', callback_data=f'reject_{p.id}'))
            bot.send_message(message.chat.id, f"ID: {p.id}\nUser: {d['user_id']}\nEmail: {d['email']}\nPrice: {d['price']}", reply_markup=markup)
    elif text == '💸 Pending Withdraw':
        for w in db.collection('withdraws').where('status', '==', 'Pending').stream():
            d = w.to_dict()
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton('✅ Paid', callback_data=f'paid_{w.id}'))
            bot.send_message(message.chat.id, f"ID: {w.id}\nUser: {d['user_id']}\nAmount: {d['amount']}", reply_markup=markup)
    elif text == '👥 All Users':
        bot.reply_to(message, f"Total: {len(list(db.collection('users').stream()))}")
    elif text == '🚫 Block User':
        user_states[user_id] = 'block_user'
        bot.reply_to(message, "Enter User ID:", reply_markup=create_back_keyboard())
    elif text == '💰 Set New Gmail Price':
        user_states[user_id] = 'set_new_price'
        bot.reply_to(message, "Enter New Price:", reply_markup=create_back_keyboard())
    elif text == '📦 Set Old Gmail Price':
        user_states[user_id] = 'set_old_price'
        bot.reply_to(message, "Enter Old Price:", reply_markup=create_back_keyboard())
    elif text == '📢 Send Notification':
        user_states[user_id] = 'broadcast'
        bot.reply_to(message, "Write message:", reply_markup=create_back_keyboard())
    elif text == '⚙️ Set Min Withdraw':
        user_states[user_id] = 'set_min_withdraw'
        bot.reply_to(message, "Enter Min:", reply_markup=create_back_keyboard())
    elif text == '📊 Stats':
        s = get_settings()
        bot.reply_to(message, f"📊 Users: {len(list(db.collection('users').stream()))}\nStock: {len(list(db.collection('gmail_stock').stream()))}\nPending: {len(list(db.collection('pending').stream()))}\nNew: {s['new_gmail_price']}\nOld: {s['old_gmail_price']}\nMin: {s['min_withdraw']}")
    elif text == '🔙 Back':
        clear_user_state(user_id)
        bot.reply_to(message, "Back", reply_markup=create_main_keyboard(True))

print("Bot Running...")
bot.infinity_polling()
