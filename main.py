from flask import Flask, request
import telebot
import sqlite3
import os
from waitress import serve

TOKEN = "7901522397:AAGtp5KPLlUDtAy7FPxoFpOX9uj0SYVL-gQ"
WEBHOOK_URL = "https://avelshop-bot.onrender.com/"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --- База данных ---
conn = sqlite3.connect("avelshop.db", check_same_thread=False)
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0
)
""")
c.execute("""
CREATE TABLE IF NOT EXISTS inventory (
    user_id INTEGER,
    item TEXT
)
""")
c.execute("""
CREATE TABLE IF NOT EXISTS shop (
    name TEXT,
    price INTEGER
)
""")
conn.commit()

# --- Главное меню ---
def main_menu():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("💰 Баланс", "🛒 Магазин")
    markup.row("🎒 Инвентарь", "🛠 Админка")
    return markup

# --- Стартовая команда ---
@bot.message_handler(commands=["start"])
def handle_start(message):
    user_id = message.from_user.id
    c.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if not c.fetchone():
        c.execute("INSERT INTO users (id, balance) VALUES (?, ?)", (user_id, 0))
        conn.commit()
    bot.send_message(user_id, "📍 Главное меню:", reply_markup=main_menu())

# --- Обработка текста кнопок ---
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    user_id = message.from_user.id
    text = message.text

    if text == "💰 Баланс":
        c.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
        balance = c.fetchone()[0]
        bot.send_message(user_id, f"💰 У вас {balance} Кэпов.")

    elif text == "🎒 Инвентарь":
        c.execute("SELECT item FROM inventory WHERE user_id = ?", (user_id,))
        items = c.fetchall()
        if items:
            inv = "\n".join([f"• {item[0]}" for item in items])
            bot.send_message(user_id, f"🎒 Ваши скины:\n{inv}")
        else:
            bot.send_message(user_id, "🎒 Ваш инвентарь пуст.")

    elif text == "🛒 Магазин":
        c.execute("SELECT name, price FROM shop")
        skins = c.fetchall()
        if not skins:
            bot.send_message(user_id, "⛔ Магазин пуст.")
            return
        msg = "🛍️ Доступные скины:\n"
        markup = telebot.types.InlineKeyboardMarkup()
        for name, price in skins:
            msg += f"{name} — {price} Кэпов\n"
            markup.add(telebot.types.InlineKeyboardButton(f"Купить: {name}", callback_data=f"buy|{name}"))
        bot.send_message(user_id, msg, reply_markup=markup)

    elif text == "🛠 Админка":
        bot.send_message(user_id, "🔧 Команды:\n"
                                  "/addskin <название> <цена>\n"
                                  "/removeskin <название>\n"
                                  "/add <id> <сумма>\n"
                                  "/remove <id> <сумма>\n"
                                  "/users")

# --- Inline-кнопки (покупка) ---
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    user_id = call.from_user.id

    if call.data.startswith("buy|"):
        item = call.data.split("|", 1)[1]
        c.execute("SELECT price FROM shop WHERE name = ?", (item,))
        result = c.fetchone()
        if not result:
            bot.send_message(user_id, "❌ Скин не найден.")
            return
        price = result[0]
        c.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
        balance = c.fetchone()[0]
        if balance < price:
            bot.send_message(user_id, "⛔ Недостаточно Кэпов.")
            return
        c.execute("SELECT item FROM inventory WHERE user_id = ? AND item = ?", (user_id, item))
        if c.fetchone():
            bot.send_message(user_id, "📦 У вас уже есть этот скин.")
            return
        c.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (price, user_id))
        c.execute("INSERT INTO inventory (user_id, item) VALUES (?, ?)", (user_id, item))
        conn.commit()
        bot.send_message(user_id, f"✅ Покупка прошла успешно!\nВы приобрели: {item}")

# --- Команды администратора ---
@bot.message_handler(commands=["addskin", "removeskin", "add", "remove", "users"])
def admin_commands(message):
    cmd = message.text.split()
    if message.text.startswith("/addskin") and len(cmd) >= 3:
        name, price = " ".join(cmd[1:-1]), int(cmd[-1])
        c.execute("INSERT INTO shop (name, price) VALUES (?, ?)", (name, price))
        conn.commit()
        bot.reply_to(message, "✅ Скин добавлен.")
    elif message.text.startswith("/removeskin") and len(cmd) >= 2:
        name = " ".join(cmd[1:])
        c.execute("DELETE FROM shop WHERE name = ?", (name,))
        conn.commit()
        bot.reply_to(message, "✅ Скин удалён.")
    elif message.text.startswith("/add") and len(cmd) == 3:
        target_id, amount = int(cmd[1]), int(cmd[2])
        c.execute("SELECT id FROM users WHERE id = ?", (target_id,))
        if c.fetchone():
            c.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, target_id))
            conn.commit()
            bot.reply_to(message, "✅ Кэпы добавлены.")
        else:
            bot.reply_to(message, "❌ Пользователь не найден.")
    elif message.text.startswith("/remove") and len(cmd) == 3:
        target_id, amount = int(cmd[1]), int(cmd[2])
        c.execute("SELECT id FROM users WHERE id = ?", (target_id,))
        if c.fetchone():
            c.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (amount, target_id))
            conn.commit()
            bot.reply_to(message, "✅ Кэпы удалены.")
        else:
            bot.reply_to(message, "❌ Пользователь не найден.")
    elif message.text.startswith("/users"):
        c.execute("SELECT id, balance FROM users")
        data = c.fetchall()
        if not data:
            bot.reply_to(message, "Нет зарегистрированных пользователей.")
            return
        out = "\n".join([f"👤 {user[0]} — {user[1]} Кэпов" for user in data])
        bot.reply_to(message, f"👥 Пользователи:\n{out}")

# --- Вебхук для Render ---
@app.route("/", methods=["POST"])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "", 200

# --- Запуск через waitress ---
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    serve(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
