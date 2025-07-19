from flask import Flask, request
import telebot
import sqlite3
import os

TOKEN = "7901522397:AAGtp5KPLlUDtAy7FPxoFpOX9uj0SYVL-gQ"
WEBHOOK_URL = "https://avelshop-bot.onrender.com/"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --- DB SETUP ---
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

# --- Меню ---
def main_menu():
    markup = telebot.types.InlineKeyboardMarkup()
    markup.row(
        telebot.types.InlineKeyboardButton("🛒 Магазин", callback_data="shop"),
        telebot.types.InlineKeyboardButton("🎒 Инвентарь", callback_data="inventory")
    )
    markup.row(
        telebot.types.InlineKeyboardButton("💰 Баланс", callback_data="balance"),
        telebot.types.InlineKeyboardButton("🛠 Админка", callback_data="admin")
    )
    return markup

# --- Старт ---
@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.from_user.id
    c.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if not c.fetchone():
        c.execute("INSERT INTO users (id, balance) VALUES (?, ?)", (user_id, 0))
        conn.commit()
    bot.send_message(user_id, "\ud83d\udccd Главное меню:", reply_markup=main_menu())

# --- Обработка кнопок ---
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    user_id = call.from_user.id

    if call.data == "balance":
        c.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
        balance = c.fetchone()[0]
        bot.answer_callback_query(call.id)
        bot.send_message(user_id, f"\ud83d\udcb0 У вас {balance} Кэпов.")

    elif call.data == "inventory":
        c.execute("SELECT item FROM inventory WHERE user_id = ?", (user_id,))
        items = c.fetchall()
        if items:
            inv = "\n".join([f"• {item[0]}" for item in items])
            bot.send_message(user_id, f"\ud83c\udf92 Ваши скины:\n{inv}")
        else:
            bot.send_message(user_id, "\ud83c\udf92 Ваш инвентарь пуст.")

    elif call.data == "shop":
        c.execute("SELECT name, price FROM shop")
        skins = c.fetchall()
        if not skins:
            bot.send_message(user_id, "\u26d4 Магазин пуст.")
            return
        msg = "\ud83c\udf81 Доступные скины:\n"
        markup = telebot.types.InlineKeyboardMarkup()
        for name, price in skins:
            msg += f"{name} - {price} Кэпов\n"
            markup.add(telebot.types.InlineKeyboardButton(f"Купить: {name}", callback_data=f"buy|{name}"))
        bot.send_message(user_id, msg, reply_markup=markup)

    elif call.data.startswith("buy|"):
        item = call.data.split("|", 1)[1]
        c.execute("SELECT price FROM shop WHERE name = ?", (item,))
        result = c.fetchone()
        if not result:
            bot.send_message(user_id, "\u274c Скин не найден.")
            return
        price = result[0]
        c.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
        balance = c.fetchone()[0]
        if balance < price:
            bot.send_message(user_id, "\u26d4 Недостаточно Кэпов.")
            return
        c.execute("SELECT item FROM inventory WHERE user_id = ? AND item = ?", (user_id, item))
        if c.fetchone():
            bot.send_message(user_id, "\ud83d\udce6 У вас уже есть этот скин.")
            return
        c.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (price, user_id))
        c.execute("INSERT INTO inventory (user_id, item) VALUES (?, ?)", (user_id, item))
        conn.commit()
        bot.send_message(user_id, f"\u2705 Покупка прошла успешно!\nВы приобрели: {item}")

    elif call.data == "admin":
        bot.send_message(user_id, "\ud83d\udd27 Команды:\n/addskin <название> <цена>\n/removeskin <название>\n/add <id> <сумма>\n/remove <id> <сумма>")

# --- Команды админа ---
@bot.message_handler(commands=["addskin", "removeskin", "add", "remove"])
def admin_commands(message):
    user_id = message.from_user.id
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
        if not c.fetchone():
            bot.reply_to(message, "❌ Пользователь не найден.")
        else:
            c.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, target_id))
            conn.commit()
            bot.reply_to(message, "✅ Кэпы добавлены.")
    elif message.text.startswith("/remove") and len(cmd) == 3:
        target_id, amount = int(cmd[1]), int(cmd[2])
        c.execute("SELECT id FROM users WHERE id = ?", (target_id,))
        if not c.fetchone():
            bot.reply_to(message, "❌ Пользователь не найден.")
        else:
            c.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (amount, target_id))
            conn.commit()
            bot.reply_to(message, "✅ Кэпы удалены.")

# --- Flask endpoint для webhook ---
@app.route("/", methods=["POST"])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "", 200

# --- Запуск локально (не используется на Render) ---
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
