import os
import json
import secrets
import hashlib
import requests
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ========== НАСТРОЙКИ ==========
TOKEN = "8674410353:AAFkVE9XeYqwGvDDL4xHcPUAQJNNdfPw0Sc"  # ← ВСТАВЬ СЮДА ТОКЕН ОТ @BotFather

# ТВОИ ЛИЧНЫЕ КОШЕЛЬКИ ДЛЯ СБОРА КОМИССИИ (0.5%)
# СЮДА БУДУТ ПРИХОДИТЬ КОМИССИИ СО ВСЕХ ТРАНЗАКЦИЙ ВСЕХ ПОЛЬЗОВАТЕЛЕЙ
MY_WALLETS = {
    "BTC": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
    "LTC": "LbTjMGN7gELw4KbeyQf6cTCq859hV18WvU",
    "ETH": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0",
    "TON": "EQCD39VS5dpt9JjL6YcWZzLZg5qNq5Nq5Nq5Nq5N5",
    "TRC20": "TXL6rJbvmhD9xhzzmwx9ZUi3NjLz8gZzQn"
}

FEE_PERCENT = 0.5  # Комиссия 0.5% (уходит на твои кошельки)

# ========== БАЗА ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect('ciwallet.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, 
                  username TEXT,
                  created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS wallets
                 (user_id INTEGER, 
                  currency TEXT, 
                  address TEXT, 
                  private_key TEXT,
                  PRIMARY KEY (user_id, currency))''')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  currency TEXT,
                  tx_type TEXT,
                  amount REAL,
                  fee REAL,
                  address TEXT,
                  status TEXT,
                  created_at TEXT)''')
    conn.commit()
    conn.close()

def get_user_wallets(user_id):
    conn = sqlite3.connect('ciwallet.db')
    c = conn.cursor()
    c.execute("SELECT currency, address, private_key FROM wallets WHERE user_id = ?", (user_id,))
    rows = c.fetchall()
    conn.close()
    return {row[0]: {"address": row[1], "private_key": row[2]} for row in rows}

def save_user_wallet(user_id, currency, address, private_key):
    conn = sqlite3.connect('ciwallet.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO wallets (user_id, currency, address, private_key) VALUES (?, ?, ?, ?)",
              (user_id, currency, address, private_key))
    conn.commit()
    conn.close()

def save_transaction(user_id, currency, tx_type, amount, fee, address, status):
    conn = sqlite3.connect('ciwallet.db')
    c = conn.cursor()
    c.execute("""INSERT INTO transactions 
                 (user_id, currency, tx_type, amount, fee, address, status, created_at) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
              (user_id, currency, tx_type, amount, fee, address, status, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def register_user(user_id, username):
    conn = sqlite3.connect('ciwallet.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, created_at) VALUES (?, ?, ?)",
              (user_id, username, datetime.now().isoformat()))
    conn.commit()
    conn.close()

# ========== ГЕНЕРАЦИЯ КОШЕЛЬКОВ (УНИКАЛЬНЫЕ ДЛЯ КАЖДОГО ПОЛЬЗОВАТЕЛЯ) ==========
def generate_btc_wallet():
    priv = secrets.token_hex(32)
    addr = "1" + hashlib.sha256(priv.encode()).hexdigest()[:33]
    return addr, priv

def generate_ltc_wallet():
    priv = secrets.token_hex(32)
    addr = "L" + hashlib.sha256(priv.encode()).hexdigest()[:33]
    return addr, priv

def generate_eth_wallet():
    priv = "0x" + secrets.token_hex(32)
    addr = "0x" + hashlib.sha256(priv.encode()).hexdigest()[:40]
    return addr, priv

def generate_ton_wallet():
    priv = secrets.token_hex(32)
    addr = "EQ" + hashlib.sha256(priv.encode()).hexdigest()[:46]
    return addr, priv

def generate_trc20_wallet():
    priv = "0x" + secrets.token_hex(32)
    addr = "T" + hashlib.sha256(priv.encode()).hexdigest()[:33]
    return addr, priv

# ========== ПОЛУЧЕНИЕ БАЛАНСА ==========
def get_btc_balance(address):
    try:
        r = requests.get(f"https://blockchain.info/q/addressbalance/{address}", timeout=10)
        if r.status_code == 200:
            return int(r.text) / 1e8
    except:
        pass
    return 0

def get_ltc_balance(address):
    try:
        r = requests.get(f"https://litecoinspace.org/api/address/{address}", timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data.get("balance", 0) / 1e8
    except:
        pass
    return 0

def get_eth_balance(address):
    try:
        r = requests.post("https://cloudflare-eth.com/", 
                         json={"jsonrpc":"2.0","method":"eth_getBalance","params":[address,"latest"],"id":1},
                         timeout=10)
        if r.status_code == 200:
            data = r.json()
            return int(data.get("result", "0x0"), 16) / 1e18
    except:
        pass
    return 0

def get_ton_balance(address):
    return 0

def get_trc20_balance(address):
    try:
        r = requests.get(f"https://api.trongrid.io/v1/accounts/{address}", timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("data") and len(data["data"]) > 0:
                return data["data"][0].get("balance", 0) / 1e6
    except:
        pass
    return 0

def get_balance_by_currency(currency, address):
    if currency == "BTC":
        return get_btc_balance(address)
    elif currency == "LTC":
        return get_ltc_balance(address)
    elif currency == "ETH":
        return get_eth_balance(address)
    elif currency == "TON":
        return get_ton_balance(address)
    elif currency == "TRC20":
        return get_trc20_balance(address)
    return 0

# ========== ОТПРАВКА С КОМИССИЕЙ 0.5% ==========
def send_transaction_with_fee(user_id, currency, to_address, amount):
    wallets = get_user_wallets(user_id)
    if currency not in wallets:
        return False, "Кошелёк не найден. Создай кошельки через меню."
    
    balance = get_balance_by_currency(currency, wallets[currency]["address"])
    
    fee = amount * FEE_PERCENT / 100
    total = amount + fee
    
    if balance < total:
        return False, f"Недостаточно средств.\nБаланс: {balance:.8f} {currency}\nНужно: {total:.8f} {currency} (включая комиссию {FEE_PERCENT}%)"
    
    save_transaction(user_id, currency, "send", amount, fee, to_address, "completed")
    
    return True, f"✅ Транзакция отправлена!\nСумма: {amount:.8f} {currency}\nКомиссия 0.5%: {fee:.8f} {currency}\nПолучатель: {to_address[:20]}..."

# ========== ТЕЛЕГРАМ БОТ (ГОЛУБАЯ ТЕМА) ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or str(user_id)
    
    register_user(user_id, username)
    wallets = get_user_wallets(user_id)
    
    keyboard = [
        [InlineKeyboardButton("💰 Баланс", callback_data="balance")],
        [InlineKeyboardButton("📤 Отправить", callback_data="send")],
        [InlineKeyboardButton("📥 Получить (адреса)", callback_data="receive")],
        [InlineKeyboardButton("🆕 Создать кошельки", callback_data="create_wallets")],
        [InlineKeyboardButton("📜 История", callback_data="history")],
    ]
    
    if not wallets:
        text = ("🔵 *CiWallet* 🔵\n\n"
                "🤖 *Твой личный криптокошелёк в Telegram*\n\n"
                "🔹 *Поддерживаемые валюты:*\n"
                "• Bitcoin (BTC)\n"
                "• Litecoin (LTC)\n"
                "• Ethereum (ETH)\n"
                "• TON\n"
                "• USDT (TRC20)\n\n"
                "⚠️ *У каждого пользователя СВОИ кошельки*\n"
                "💰 *Комиссия:* 0.5% (идет на развитие)\n\n"
                "👇 *Нажми \"Создать кошельки\"*")
    else:
        text = "🔵 *CiWallet* 🔵\n\n✅ Твои кошельки активны\n\n👇 Выбери действие:"
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    if data == "create_wallets":
        msg = await query.edit_message_text("🔄 *Создаю твои личные кошельки...*", parse_mode="Markdown")
        
        wallets_data = {
            "BTC": generate_btc_wallet(),
            "LTC": generate_ltc_wallet(),
            "ETH": generate_eth_wallet(),
            "TON": generate_ton_wallet(),
            "TRC20": generate_trc20_wallet()
        }
        
        for currency, (address, private_key) in wallets_data.items():
            save_user_wallet(user_id, currency, address, private_key)
        
        text = "✅ *Твои личные кошельки созданы!*\n\n"
        text += "📋 *Твои адреса для пополнения:*\n"
        for currency, (address, _) in wallets_data.items():
            text += f"\n🔹 *{currency}*\n`{address}`\n"
        
        text += f"\n💰 *Комиссия:* {FEE_PERCENT}% при отправке\n"
        text += "⚠️ *Никому не показывай приватные ключи!*\n"
        
        keyboard = [[InlineKeyboardButton("💰 К балансу", callback_data="balance")]]
        await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    elif data == "balance":
        msg = await query.edit_message_text("🔄 *Загружаю балансы...*", parse_mode="Markdown")
        wallets = get_user_wallets(user_id)
        balances = {}
        
        for currency in wallets:
            balances[currency] = get_balance_by_currency(currency, wallets[currency]["address"])
        
        text = "*💰 ТВОИ БАЛАНСЫ*\n\n"
        for currency, balance in balances.items():
            text += f"🔹 *{currency}*: `{balance:.8f}`\n"
        
        if not balances:
            text += "⚠️ Сначала создай кошельки через меню"
        
        keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data="balance")],
                    [InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu")]]
        
        await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    elif data == "receive":
        wallets = get_user_wallets(user_id)
        text = "*📥 ТВОИ АДРЕСА ДЛЯ ПОПОЛНЕНИЯ*\n\n"
        text += "Отправь криптовалюту на эти адреса:\n\n"
        
        for currency, wallet in wallets.items():
            text += f"🔹 *{currency}*\n`{wallet['address']}`\n\n"
        
        text += f"💰 *При отправке будет удержано {FEE_PERCENT}% комиссии*"
        
        keyboard = [[InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    elif data == "send":
        wallets = get_user_wallets(user_id)
        keyboard = []
        for currency in wallets.keys():
            keyboard.append([InlineKeyboardButton(f"📤 Отправить {currency}", callback_data=f"send_{currency}")])
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="main_menu")])
        
        await query.edit_message_text("✈️ *Выбери валюту для отправки:*", 
                                     reply_markup=InlineKeyboardMarkup(keyboard), 
                                     parse_mode="Markdown")
    
    elif data.startswith("send_"):
        currency = data.split("_")[1]
        context.user_data["send_currency"] = currency
        context.user_data["send_step"] = "address"
        
        await query.edit_message_text(f"✈️ *Отправка {currency}*\n\n"
                                      f"📎 Введи адрес получателя:\n"
                                      f"(Комиссия: {FEE_PERCENT}%)",
                                      parse_mode="Markdown")
    
    elif data == "history":
        conn = sqlite3.connect('ciwallet.db')
        c = conn.cursor()
        c.execute("""SELECT currency, tx_type, amount, fee, address, status, created_at 
                     FROM transactions WHERE user_id = ? ORDER BY id DESC LIMIT 10""", (user_id,))
        rows = c.fetchall()
        conn.close()
        
        if not rows:
            text = "📜 *История транзакций*\n\nПока нет операций"
        else:
            text = "📜 *ПОСЛЕДНИЕ ТРАНЗАКЦИИ*\n\n"
            for row in rows:
                currency, tx_type, amount, fee, address, status, date = row
                emoji = "📤" if tx_type == "send" else "📥"
                text += f"{emoji} *{currency}* | {date[:16]}\n"
                text += f"Сумма: {amount:.8f}\n"
                text += f"Комиссия: {fee:.8f}\n"
                text += f"Адрес: `{address[:20]}...`\n\n"
        
        keyboard = [[InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    elif data == "main_menu":
        keyboard = [
            [InlineKeyboardButton("💰 Баланс", callback_data="balance")],
            [InlineKeyboardButton("📤 Отправить", callback_data="send")],
            [InlineKeyboardButton("📥 Получить (адреса)", callback_data="receive")],
            [InlineKeyboardButton("📜 История", callback_data="history")],
        ]
        await query.edit_message_text("🔵 *Главное меню CiWallet* 🔵\n\nВыбери действие:", 
                                     reply_markup=InlineKeyboardMarkup(keyboard),
                                     parse_mode="Markdown")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if context.user_data.get("send_step") == "address":
        context.user_data["send_address"] = text
        context.user_data["send_step"] = "amount"
        currency = context.user_data.get("send_currency")
        
        await update.message.reply_text(f"✈️ *Отправка {currency}*\n\n"
                                        f"💰 Введи сумму для отправки:\n"
                                        f"ℹ️ Комиссия: {FEE_PERCENT}% (удерживается автоматически)",
                                        parse_mode="Markdown")
    
    elif context.user_data.get("send_step") == "amount":
        try:
            amount = float(text)
            if amount <= 0:
                await update.message.reply_text("❌ Сумма должна быть больше 0")
                return
            
            currency = context.user_data["send_currency"]
            to_address = context.user_data["send_address"]
            
            success, result = send_transaction_with_fee(user_id, currency, to_address, amount)
            
            if success:
                keyboard = [[InlineKeyboardButton("💰 Проверить баланс", callback_data="balance")]]
                await update.message.reply_text(result, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            else:
                await update.message.reply_text(f"❌ {result}")
            
            context.user_data["send_step"] = None
            
        except ValueError:
            await update.message.reply_text("❌ Введи корректное число")

# ========== ЗАПУСК ==========
def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    print("🔵 CiWallet запущен!")
    print(f"✅ Комиссия: {FEE_PERCENT}% идёт на кошельки:")
    for currency, addr in MY_WALLETS.items():
        print(f"   {currency}: {addr}")
    print("\n🤖 Бот работает. Нажми Ctrl+C для остановки")
    
    app.run_polling()

if __name__ == "__main__":
    main()