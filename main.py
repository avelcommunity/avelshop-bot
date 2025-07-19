import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
from flask import Flask, request

API_TOKEN = "7901522397:AAGtp5KPLlUDtAy7FPxoFpOX9uj0SYVL-gQ"  # ЗАМЕНИ сюда свой токен

WEBHOOK_URL = "https://avelshop-bot.onrender.com/"  # не забудь слэш в конце!

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

# ─── Инициализация БД ──────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect("avelshop.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    caps INTEGER DEFAULT 0
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (
                    user_id INTEGER,
                    skin TEXT
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS shop (
                    name TEXT PRIMARY KEY,
                    price INTEGER
                )''')
    # Примеры скинов
    c.execute("INSERT OR IGNORE INTO shop VALUES ('AK-47 | Redline', 1000)")
    c.execute("INSERT OR IGNORE INTO shop VALUES ('AWP | Asiimov', 1800)")
    conn.commit()
    conn.close()

init_db()

# ─── Команда /start ────────────────────────────────────────────────────────
@bot.message_handler(commands=["start"])
def start(msg):
    conn = sqlite3.connect("avelshop.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (msg.from_user.id,))
    conn.commit()
    conn.close()
    bot.send_message(msg.chat.id, "📍 Главное меню:", reply_markup=main_menu())

# ─── Главное меню ──────────────────────────────────────────────────────────
def main_menu():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🛒 Магазин", callback_data="shop"))
    kb.add(InlineKeyboardButton("🎒 Инвентарь", callback_data="inv"))
    kb.add(InlineKeyboardButton("💰 Баланс", callback_data="bal"))
    kb.add(InlineKeyboardButton("🛠 Админка", callback_data="admin"))
    return kb

# ─── Обработка кнопок ──────────────────────────────────────────────────────
@bot.callback_query_handler(func=lambda c: True)
def handle_callback(call):
    user_id = call.from_user.id
    conn = sqlite3.connect("avelshop.db")
    c = conn.cursor()

    if call.data == "shop":
        c.execute("SELECT * FROM shop")
        items = c.fetchall()
        if not items:
            bot.answer_callback_query(call.id, "Скины не найдены.")
            return
        kb = InlineKeyboardMarkup()
        for name, price in items:
            kb.add(InlineKeyboardButton(f"{name} - {price} Кэпов", callback_data=f"buy|{name}"))
        bot.edit_message_text("🛍️ Доступные скины:", call.message.chat.id, call.message.message_id, reply_markup=kb)

    elif call.data.startswith("buy|"):
        item = call.data.split("|")[1]
        c.execute("SELECT price FROM shop WHERE name=?", (item,))
        row = c.fetchone()
        if not row:
            bot.answer_callback_query(call.id, "Скин не найден.")
            return
        price = row[0]
        c.execute("SELECT caps FROM users WHERE user_id=?", (user_id,))
        balance = c.fetchone()[0]

        c.execute("SELECT skin FROM inventory WHERE user_id=? AND skin=?", (user_id, item))
        if c.fetchone():
            bot.answer_callback_query(call.id, "📦 У вас уже есть этот скин.")
            return

        if balance < price:
            bot.answer_callback_query(call.id, "⛔ Недостаточно Кэпов.")
        else:
            c.execute("UPDATE users SET caps = caps - ? WHERE user_id=?", (price, user_id))
            c.execute("INSERT INTO inventory VALUES (?, ?)", (user_id, item))
            conn.commit()
            bot.answer_callback_query(call.id, f"✅ Покупка прошла успешно!\nВы приобрели: {item}")
            bot.edit_message_text("📍 Главное меню:", call.message.chat.id, call.message.message_id, reply_markup=main_menu())

    elif call.data == "inv":
        c.execute("SELECT skin FROM inventory WHERE user_id=?", (user_id,))
        inv = c.fetchall()
        if inv:
            skins = "\n".join(f"• {i[0]}" for i in inv)
            bot.edit_message_text(f"🎒 Ваши скины:\n{skins}", call.message.chat.id, call.message.message_id, reply_markup=main_menu())
        else:
            bot.edit_message_text("🎒 Ваш инвентарь пуст.", call.message.chat.id, call.message.message_id, reply_markup=main_menu())

    elif call.data == "bal":
        c.execute("SELECT caps FROM users WHERE user_id=?", (user_id,))
        bal = c.fetchone()[0]
        bot.edit_message_text(f"💰 У вас {bal} Кэпов.", call.message.chat.id, call.message.message_id, reply_markup=main_menu())

    elif call.data == "admin":
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("/addskin <название> <цена>", callback_data="none"))
        kb.add(InlineKeyboardButton("/removeskin <название>", callback_data="none"))
        kb.add(InlineKeyboardButton("/add <id> <сумма>", callback_data="none"))
        kb.add(InlineKeyboardButton("/remove <id> <сумма>", callback_data="none"))
        bot.edit_message_text("🔧 Команды:", call.message.chat.id, call.message.message_id, reply_markup=kb)

    conn.close()

# ─── Админ команды ─────────────────────────────────────────────────────────
@bot.message_handler(commands=["add", "remove", "addskin", "removeskin"])
def admin_commands(msg):
    user_id = msg.from_user.id
    args = msg.text.split()
    conn = sqlite3.connect("avelshop.db")
    c = conn.cursor()

    if msg.text.startswith("/addskin") and len(args) >= 3:
        name = " ".join(args[1:-1])
        price = int(args[-1])
        c.execute("INSERT OR REPLACE INTO shop VALUES (?, ?)", (name, price))
        conn.commit()
        bot.reply_to(msg, "✅ Скин добавлен.")
    elif msg.text.startswith("/removeskin") and len(args) >= 2:
        name = " ".join(args[1:])
        c.execute("DELETE FROM shop WHERE name=?", (name,))
        conn.commit()
        bot.reply_to(msg, "✅ Скин удалён.")
    elif msg.text.startswith("/add") and len(args) == 3:
        target_id, amount = int(args[1]), int(args[2])
        c.execute("SELECT user_id FROM users WHERE user_id=?", (target_id,))
        if c.fetchone():
            c.execute("UPDATE users SET caps = caps + ? WHERE user_id=?", (amount, target_id))
            conn.commit()
            bot.reply_to(msg, "✅ Кэпы добавлены.")
        else:
            bot.reply_to(msg, "❌ Пользователь не найден.")
    elif msg.text.startswith("/remove") and len(args) == 3:
        target_id, amount = int(args[1]), int(args[2])
        c.execute("UPDATE users SET caps = caps - ? WHERE user_id=?", (amount, target_id))
        conn.commit()
        bot.reply_to(msg, "✅ Кэпы убавлены.")
    else:
        bot.reply_to(msg, "❗ Неверный формат команды.")
    conn.close()

# ─── Flask для Render ──────────────────────────────────────────────────────
@app.route("/", methods=["POST"])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200

@app.route("/", methods=["GET"])
def index():
    return "AvelShop Bot работает!", 200

# ─── Установка вебхука ─────────────────────────────────────────────────────
bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)

# ─── Запуск Flask ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
