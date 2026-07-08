import telebot
from telebot import types
import firebase_admin
from firebase_admin import credentials, firestore
import os
import random
import uuid
import datetime
import json
import threading
import time

# Environment variables
TOKEN = os.getenv('TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
FIREBASE_KEY = os.getenv('FIREBASE_KEY')
ADMIN_WHATSAPP = os.getenv('ADMIN_WHATSAPP', 'Not Set')

if not TOKEN or not FIREBASE_KEY:
    print("Missing environment variables!")
    exit(1)

# Initialize Firebase
if not firebase_admin._apps:
    try:
        if os.path.exists(FIREBASE_KEY):
            cred = credentials.Certificate(FIREBASE_KEY)
        else:
            # Try as JSON string
            cred_dict = json.loads(FIREBASE_KEY)
            cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        print(f"Firebase init error: {e}")
        exit(1)

db = firestore.client()

bot = telebot.TeleBot(TOKEN)

# Global dicts
user_states = {}
user_temp = {}

# Default settings
def get_settings():
    settings_ref = db.collection('settings').document('config')
    settings = settings_ref.get()
    if settings.exists:
        return settings.to_dict()
    else:
        default_settings = {
            'new_gmail_price': 12,
            'old_gmail_price': 6,
            'min_withdraw': 25,
            'currency': 'BDT'
        }
        settings_ref.set(default_settings)
        return default_settings

def save_settings(settings):
    db.collection('settings').document('config').set(settings)

# Helper functions
def get_user_data(user_id):
    user_ref = db.collection('users').document(str(user_id))
    user = user_ref.get()
    if not user.exists:
        user_data = {
            'balance': 0.0,
            'hold': 0.0,
            'accounts': [],
            'currency': 'BDT',
            'blocked': False,
            'submitted_count': 0
        }
        user_ref.set(user_data)
        return user_data
    return user.to_dict()

def update_user_data(user_id, data):
    db.collection('users').document(str(user_id)).update(data)

def is_admin(user_id):
    return user_id == ADMIN_ID

def create_main_keyboard(is_admin_user=True):
    keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    keyboard.add(types.KeyboardButton('➕ Register a new Gmail'))
    keyboard.add(types.KeyboardButton('📦 Old Gmail Sell'))
    keyboard.add(types.KeyboardButton('💰 Balance'))
    keyboard.add(types.KeyboardButton('⏳ Balance Hold'))
    keyboard.add(types.KeyboardButton('📁 My accounts'))
    keyboard.add(types.KeyboardButton('💸 Withdraw'))
    keyboard.add(types.KeyboardButton('⚙️ Settings'))
    if is_admin_user:
        keyboard.add(types.KeyboardButton('👑 Admin Panel'))
    return keyboard

def create_back_keyboard():
    keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    keyboard.add(types.KeyboardButton('⬅️ Back'))
    keyboard.add(types.KeyboardButton('Cancel'))
    return keyboard

# Clear state
def clear_user_state(user_id):
    if user_id in user_states:
        del user_states[user_id]
    if user_id in user_temp:
        del user_temp[user_id]

# Start command
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    clear_user_state(user_id)
    user_data = get_user_data(user_id)
    if user_data.get('blocked', False):
        bot.reply_to(message, "🚫 You are blocked by admin.")
        return
    
    markup = create_main_keyboard(is_admin(user_id))
    bot.reply_to(message, "👋 Welcome to Gmail Buy Sell Bot!\nSelect an option:", reply_markup=markup)

# Main message handler
@bot.message_handler(content_types=['text'])
def handle_message(message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    user_data = get_user_data(user_id)
    if user_data.get('blocked', False) and not is_admin(user_id):
        bot.reply_to(message, "🚫 You are blocked.")
        return
    
    settings = get_settings()
    currency = user_data.get('currency', 'BDT')
    
    # Handle back and cancel
    if text in ['⬅️ Back', 'Cancel']:
        clear_user_state(user_id)
        markup = create_main_keyboard(is_admin(user_id))
        bot.reply_to(message, "✅ Action cancelled. Back to main menu.", reply_markup=markup)
        return
    
    # Admin check for admin panel
    if text == '👑 Admin Panel' and is_admin(user_id):
        show_admin_panel(message)
        return
    
    current_state = user_states.get(user_id)
    
    # Handle states
    if current_state:
        handle_state(message, current_state, user_id, text, settings, currency)
        return
    
    # Main menu handlers
    if text == '➕ Register a new Gmail':
        register_new_gmail(message, user_id)
    elif text == '📦 Old Gmail Sell':
        start_old_gmail_sell(message, user_id)
    elif text == '💰 Balance':
        show_balance(message, user_data, currency)
    elif text == '⏳ Balance Hold':
        show_hold(message, user_data, currency)
    elif text == '📁 My accounts':
        show_my_accounts(message, user_id)
    elif text == '💸 Withdraw':
        start_withdraw(message, user_id)
    elif text == '⚙️ Settings':
        show_settings(message, user_id, user_data)
    else:
        markup = create_main_keyboard(is_admin(user_id))
        bot.reply_to(message, "❓ Please select from menu.", reply_markup=markup)

def handle_state(message, state, user_id, text, settings, currency):
    try:
        if state == 'old_email':
            user_temp[user_id] = {'old_email': text}
            user_states[user_id] = 'old_pass'
            bot.reply_to(message, "🔑 Send Password:", reply_markup=create_back_keyboard())
            
        elif state == 'old_pass':
            temp = user_temp.get(user_id, {})
            email = temp.get('old_email')
            if not email or not text:
                bot.reply_to(message, "❌ Invalid data.")
                clear_user_state(user_id)
                return
            
            price = settings.get('old_gmail_price', 6)
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton('✅ Submit Old Gmail', callback_data=f'submit_old_{user_id}'))
            info = f"📧 Email: {email}\n🔑 Pass: {text}\n💰 Price: {price} {currency}"
            bot.reply_to(message, info, reply_markup=markup)
            user_temp[user_id]['old_pass'] = text
            user_temp[user_id]['old_price'] = price
            clear_user_state(user_id)  # Clear after showing submit
            
        elif state == 'withdraw_method':
            user_temp[user_id] = {'withdraw_method': text}
            user_states[user_id] = 'withdraw_number'
            bot.reply_to(message, "📱 Enter Number/Account:", reply_markup=create_back_keyboard())
            
        elif state == 'withdraw_number':
            temp = user_temp.get(user_id, {})
            method = temp.get('withdraw_method')
            number = text
            user_temp[user_id]['withdraw_number'] = number
            user_states[user_id] = 'withdraw_amount'
            bot.reply_to(message, f"💰 Enter Amount (Min: {settings.get('min_withdraw', 25)} {currency}):", reply_markup=create_back_keyboard())
            
        elif state == 'withdraw_amount':
            try:
                amount = float(text)
                min_w = settings.get('min_withdraw', 25)
                if amount < min_w:
                    bot.reply_to(message, f"❌ Minimum withdraw is {min_w} {currency}")
                    clear_user_state(user_id)
                    return
                user_data = get_user_data(user_id)
                if amount > user_data.get('balance', 0):
                    bot.reply_to(message, "❌ Insufficient balance.")
                    clear_user_state(user_id)
                    return
                
                temp = user_temp.get(user_id, {})
                method = temp.get('withdraw_method')
                number = temp.get('withdraw_number')
                
                # Save withdraw
                wid = str(uuid.uuid4())[:8]
                withdraw_data = {
                    'id': wid,
                    'user_id': user_id,
                    'amount': amount,
                    'method': method,
                    'number': number,
                    'status': 'Pending',
                    'timestamp': datetime.datetime.utcnow().isoformat()
                }
                db.collection('withdraws').document(wid).set(withdraw_data)
                
                # Deduct from balance
                new_balance = user_data['balance'] - amount
                update_user_data(user_id, {'balance': new_balance})
                
                bot.reply_to(message, f"✅ Withdraw request submitted!\nID: {wid}\nAmount: {amount} {currency}\nStatus: Pending")
            except ValueError:
                bot.reply_to(message, "❌ Invalid amount.")
            finally:
                clear_user_state(user_id)
        
        elif state == 'change_currency':
            if text.upper() in ['BDT', 'USD', 'INR']:
                update_user_data(user_id, {'currency': text.upper()})
                bot.reply_to(message, f"✅ Currency changed to {text.upper()}")
            else:
                bot.reply_to(message, "❌ Invalid currency. Use BDT, USD or INR.")
            clear_user_state(user_id)
        
        # Admin states
        elif is_admin(user_id):
            handle_admin_state(message, state, user_id, text, settings)
    except Exception as e:
        print(f"State error: {e}")
        bot.reply_to(message, "❌ Error occurred. Try again.")
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
            temp = user_temp.get(user_id, {})
            first = temp.get('first_name')
            last = temp.get('last_name')
            email = temp.get('email')
            password = text
            price = settings.get('new_gmail_price', 12)
            
            stock_data = {
                'first_name': first,
                'last_name': last,
                'email': email,
                'pass': password,
                'price': price,
                'timestamp': datetime.datetime.utcnow().isoformat()
            }
            db.collection('gmail_stock').document(email).set(stock_data)
            
            bot.reply_to(message, f"✅ Gmail added to stock!\nEmail: {email}\nPrice: {price}")
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton('✅ Complete & Add Another', callback_data='add_another'))
            bot.reply_to(message, "Add another?", reply_markup=markup)
            clear_user_state(user_id)
        
        elif state == 'set_new_price':
            try:
                price = float(text)
                settings['new_gmail_price'] = price
                save_settings(settings)
                bot.reply_to(message, f"✅ New Gmail price set to {price}")
            except:
                bot.reply_to(message, "❌ Invalid price")
            clear_user_state(user_id)
            
        elif state == 'set_old_price':
            try:
                price = float(text)
                settings['old_gmail_price'] = price
                save_settings(settings)
                bot.reply_to(message, f"✅ Old Gmail price set to {price}")
            except:
                bot.reply_to(message, "❌ Invalid price")
            clear_user_state(user_id)
            
        elif state == 'set_min_withdraw':
            try:
                val = float(text)
                settings['min_withdraw'] = val
                save_settings(settings)
                bot.reply_to(message, f"✅ Min withdraw set to {val}")
            except:
                bot.reply_to(message, "❌ Invalid value")
            clear_user_state(user_id)
            
        elif state == 'block_user':
            try:
                block_id = int(text)
                update_user_data(block_id, {'blocked': True})
                bot.reply_to(message, f"✅ User {block_id} blocked.")
            except:
                bot.reply_to(message, "❌ Invalid User ID")
            clear_user_state(user_id)
            
        elif state == 'broadcast':
            users = db.collection('users').stream()
            count = 0
            for user_doc in users:
                try:
                    bot.send_message(user_doc.id, f"📢 Broadcast:\n{text}")
                    count += 1
                except:
                    pass
            bot.reply_to(message, f"✅ Broadcast sent to {count} users.")
            clear_user_state(user_id)
            
    except Exception as e:
        print(f"Admin state error: {e}")
        bot.reply_to(message, "❌ Error.")
        clear_user_state(user_id)

# New Gmail
def register_new_gmail(message, user_id):
    stock_ref = db.collection('gmail_stock')
    stocks = list(stock_ref.stream())
    if not stocks:
        bot.reply_to(message, "❌ No Gmail stock available.")
        return
    
    # Pick random
    random_doc = random.choice(stocks)
    data = random_doc.to_dict()
    email = random_doc.id
    
    price = data.get('price', 12)
    info = f"📧 New Gmail Available:\n\n👤 Name: {data.get('first_name')} {data.get('last_name')}\n📧 Email: {email}\n🔑 Pass: {data.get('pass')}\n💰 Price: {price} BDT"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('✅ Submit', callback_data=f'submit_new_{email}_{user_id}'))
    
    bot.reply_to(message, info, reply_markup=markup)

# Old Gmail Sell
def start_old_gmail_sell(message, user_id):
    user_states[user_id] = 'old_email'
    bot.reply_to(message, "📧 Send Email (@gmail.com):", reply_markup=create_back_keyboard())

# Balance
def show_balance(message, user_data, currency):
    balance = user_data.get('balance', 0)
    hold = user_data.get('hold', 0)
    total = balance + hold
    text = f"💰 Your Balance\n\nMain: {balance} {currency}\nHold: {hold} {currency}\nTotal: {total} {currency}\nSubmitted: {user_data.get('submitted_count', 0)}"
    bot.reply_to(message, text)

def show_hold(message, user_data, currency):
    hold = user_data.get('hold', 0)
    bot.reply_to(message, f"⏳ Hold Balance: {hold} {currency}")

# My Accounts
def show_my_accounts(message, user_id):
    user_data = get_user_data(user_id)
    accounts = user_data.get('accounts', [])
    if not accounts:
        bot.reply_to(message, "📁 No accounts yet.")
        return
    text = "📁 Your Accounts:\n\n"
    for acc in accounts:
        text += f"📧 {acc.get('email')}\n💰 {acc.get('price')} | Status: {acc.get('status', 'Approved')}\n\n"
    bot.reply_to(message, text)

# Withdraw
def start_withdraw(message, user_id):
    user_data = get_user_data(user_id)
    if user_data.get('balance', 0) < 25:
        bot.reply_to(message, "❌ Insufficient balance for withdraw.")
        return
    markup = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
    markup.add('Bkash', 'Nagad', 'USDT BEP20')
    markup.add('⬅️ Back')
    bot.reply_to(message, "💸 Select Method:", reply_markup=markup)
    user_states[user_id] = 'withdraw_method'

# Settings user
def show_settings(message, user_id, user_data):
    curr = user_data.get('currency', 'BDT')
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('Change Currency', callback_data=f'change_curr_{user_id}'))
    text = f"⚙️ Settings\nCurrency: {curr}"
    bot.reply_to(message, text, reply_markup=markup)

# Admin Panel
def show_admin_panel(message):
    keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    buttons = [
        '➕ Add Gmail Stock', '📋 Stock List', '📧 Pending Gmail',
        '💸 Pending Withdraw', '👥 All Users', '🚫 Block User',
        '💰 Set New Gmail Price', '📦 Set Old Gmail Price',
        '📢 Send Notification', '⚙️ Set Min Withdraw', '📊 Stats', '🔙 Back'
    ]
    for btn in buttons:
        keyboard.add(types.KeyboardButton(btn))
    bot.reply_to(message, "👑 Admin Panel", reply_markup=keyboard)

# Callback handler
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    try:
        data = call.data
        user_id = call.from_user.id
        message_id = call.message.message_id
        chat_id = call.message.chat.id
        
        settings = get_settings()
        
        if data.startswith('submit_new_'):
            parts = data.split('_')
            email = parts[2]
            buyer_id = int(parts[3])
            
            stock_ref = db.collection('gmail_stock').document(email)
            stock = stock_ref.get()
            if not stock.exists:
                bot.answer_callback_query(call.id, "❌ Already taken.")
                return
            
            sdata = stock.to_dict()
            price = sdata.get('price', 12)
            
            # Move to pending
            pid = str(uuid.uuid4())[:8]
            pending_data = {
                'id': pid,
                'user_id': buyer_id,
                'email': email,
                'pass': sdata.get('pass'),
                'first_name': sdata.get('first_name'),
                'last_name': sdata.get('last_name'),
                'price': price,
                'type': 'new',
                'timestamp': datetime.datetime.utcnow().isoformat()
            }
            db.collection('pending').document(pid).set(pending_data)
            
            # Delete from stock
            stock_ref.delete()
            
            # Add to hold
            user_data = get_user_data(buyer_id)
            new_hold = user_data.get('hold', 0) + price
            update_user_data(buyer_id, {'hold': new_hold})
            
            bot.edit_message_text("✅ Submitted! Waiting for admin approval.", chat_id, message_id)
            bot.send_message(ADMIN_ID, f"🔔 New Gmail Submission\nUser: {buyer_id}\nEmail: {email}\nPrice: {price}")
            
        elif data.startswith('submit_old_'):
            temp = user_temp.get(user_id, {})
            email = temp.get('old_email')
            password = temp.get('old_pass')
            price = temp.get('old_price', 6)
            
            if not email or not password:
                bot.answer_callback_query(call.id, "❌ Data expired.")
                return
            
            pid = str(uuid.uuid4())[:8]
            pending_data = {
                'id': pid,
                'user_id': user_id,
                'email': email,
                'pass': password,
                'price': price,
                'type': 'old',
                'timestamp': datetime.datetime.utcnow().isoformat()
            }
            db.collection('pending').document(pid).set(pending_data)
            
            user_data = get_user_data(user_id)
            new_hold = user_data.get('hold', 0) + price
            update_user_data(user_id, {'hold': new_hold})
            
            bot.edit_message_text("✅ Old Gmail submitted! Waiting for admin approval.", chat_id, message_id)
            bot.send_message(ADMIN_ID, f"🔔 Old Gmail Submission\nUser: {user_id}\nEmail: {email}")
            
        elif data == 'add_another':
            clear_user_state(user_id)
            bot.send_message(chat_id, "➕ Add another Gmail - First Name:", reply_markup=create_back_keyboard())
            user_states[user_id] = 'add_first_name'
            
        elif data.startswith('approve_'):
            pid = data.split('_')[1]
            pending_ref = db.collection('pending').document(pid)
            pending = pending_ref.get()
            if not pending.exists:
                return
            
            pdata = pending.to_dict()
            buyer_id = pdata['user_id']
            price = pdata['price']
            
            # Move hold to balance for seller? Wait, according to spec for buyer it is payment hold
            # For simplicity, on approve release hold to main for the user (assuming earning)
            user_data = get_user_data(buyer_id)
            new_hold = max(0, user_data.get('hold', 0) - price)
            new_balance = user_data.get('balance', 0) + price
            new_count = user_data.get('submitted_count', 0) + 1
            
            # Add to accounts
            accounts = user_data.get('accounts', [])
            accounts.append({
                'email': pdata['email'],
                'price': price,
                'status': 'Approved',
                'type': pdata.get('type', 'new')
            })
            
            update_user_data(buyer_id, {
                'hold': new_hold,
                'balance': new_balance,
                'submitted_count': new_count,
                'accounts': accounts
            })
            
            pending_ref.delete()
            bot.edit_message_text("✅ Approved!", chat_id, message_id)
            try:
                bot.send_message(buyer_id, f"🎉 Your Gmail submission approved!\nEmail: {pdata['email']}\n+{price} to balance")
            except:
                pass
            
        elif data.startswith('reject_'):
            pid = data.split('_')[1]
            pending_ref = db.collection('pending').document(pid)
            pending = pending_ref.get()
            if pending.exists:
                pdata = pending.to_dict()
                price = pdata['price']
                buyer_id = pdata['user_id']
                user_data = get_user_data(buyer_id)
                new_hold = max(0, user_data.get('hold', 0) - price)
                update_user_data(buyer_id, {'hold': new_hold})
                pending_ref.delete()
            bot.edit_message_text("❌ Rejected.", chat_id, message_id)
            
        elif data.startswith('paid_'):
            wid = data.split('_')[1]
            wref = db.collection('withdraws').document(wid)
            wref.update({'status': 'Paid'})
            bot.edit_message_text("✅ Marked as Paid.", chat_id, message_id)
            
        elif data.startswith('change_curr_'):
            user_states[user_id] = 'change_currency'
            bot.send_message(chat_id, "💱 Send new currency (BDT/USD/INR):", reply_markup=create_back_keyboard())
            
    except Exception as e:
        print(f"Callback error: {e}")
        bot.answer_callback_query(call.id, "Error occurred.")

# Admin specific handlers
@bot.message_handler(func=lambda m: True)
def admin_handlers(message):
    if not is_admin(message.from_user.id):
        return
    text = message.text
    user_id = message.from_user.id
    
    if text == '➕ Add Gmail Stock':
        clear_user_state(user_id)
        user_states[user_id] = 'add_first_name'
        bot.reply_to(message, "1️⃣ First Name:", reply_markup=create_back_keyboard())
        
    elif text == '📋 Stock List':
        stocks = list(db.collection('gmail_stock').stream())
        if not stocks:
            bot.reply_to(message, "No stock.")
            return
        text_out = "📋 Stock List:\n\n"
        for i, s in enumerate(stocks, 1):
            d = s.to_dict()
            text_out += f"{i}. {d.get('first_name')} {d.get('last_name')} | {s.id} | {d.get('pass')} | {d.get('price')}\n"
        bot.reply_to(message, text_out)
        
    elif text == '📧 Pending Gmail':
        pendings = list(db.collection('pending').stream())
        if not pendings:
            bot.reply_to(message, "No pending.")
            return
        for p in pendings:
            d = p.to_dict()
            markup = types.InlineKeyboardMarkup()
            markup.row(
                types.InlineKeyboardButton('✅ Approve', callback_data=f'approve_{p.id}'),
                types.InlineKeyboardButton('❌ Reject', callback_data=f'reject_{p.id}')
            )
            bot.send_message(message.chat.id, f"Pending ID: {p.id}\nUser: {d['user_id']}\nEmail: {d['email']}\nType: {d.get('type')}\nPrice: {d['price']}", reply_markup=markup)
            
    elif text == '💸 Pending Withdraw':
        withdraws = list(db.collection('withdraws').where('status', '==', 'Pending').stream())
        if not withdraws:
            bot.reply_to(message, "No pending withdraws.")
            return
        for w in withdraws:
            d = w.to_dict()
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton('✅ Paid', callback_data=f'paid_{w.id}'))
            bot.send_message(message.chat.id, f"WD ID: {w.id}\nUser: {d['user_id']}\nAmount: {d['amount']}\nMethod: {d['method']}\nNumber: {d['number']}", reply_markup=markup)
            
    elif text == '👥 All Users':
        users = list(db.collection('users').stream())
        bot.reply_to(message, f"Total Users: {len(users)}")
        
    elif text == '🚫 Block User':
        user_states[user_id] = 'block_user'
        bot.reply_to(message, "Enter User ID to block:", reply_markup=create_back_keyboard())
        
    elif text == '💰 Set New Gmail Price':
        user_states[user_id] = 'set_new_price'
        bot.reply_to(message, "Enter new price for New Gmail:", reply_markup=create_back_keyboard())
        
    elif text == '📦 Set Old Gmail Price':
        user_states[user_id] = 'set_old_price'
        bot.reply_to(message, "Enter new price for Old Gmail:", reply_markup=create_back_keyboard())
        
    elif text == '📢 Send Notification':
        user_states[user_id] = 'broadcast'
        bot.reply_to(message, "Write message to broadcast:", reply_markup=create_back_keyboard())
        
    elif text == '⚙️ Set Min Withdraw':
        user_states[user_id] = 'set_min_withdraw'
        bot.reply_to(message, "Enter new min withdraw amount:", reply_markup=create_back_keyboard())
        
    elif text == '📊 Stats':
        settings = get_settings()
        total_users = len(list(db.collection('users').stream()))
        stock_count = len(list(db.collection('gmail_stock').stream()))
        pending_count = len(list(db.collection('pending').stream()))
        text = f"📊 Stats\n\nUsers: {total_users}\nStock: {stock_count}\nPending: {pending_count}\nNew Price: {settings.get('new_gmail_price')}\nOld Price: {settings.get('old_gmail_price')}\nMin WD: {settings.get('min_withdraw')}"
        bot.reply_to(message, text)
        
    elif text == '🔙 Back':
        clear_user_state(user_id)
        markup = create_main_keyboard(True)
        bot.reply_to(message, "Back to main.", reply_markup=markup)

# Polling
if __name__ == '__main__':
    print("Bot started...")
    bot.infinity_polling()
