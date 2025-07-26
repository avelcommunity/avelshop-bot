from flask import Flask, request
import telebot
import psycopg2
import os

TOKEN = "7901522397:AAGtp5KPLlUDtAy7FPxoFpOX9uj0SYVL-gQ"
WEBHOOK_URL = "https://avelshop-bot.onrender.com/"

ADMIN_IDS = [6425403420, 333849950]

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Подключение к PostgreSQL
conn = psycopg2.connect(
    host=os.environ["PGHOST"],
    database=os.environ["PGDATABASE"],
    user=os.environ["PGUSER"],
    password=os.environ["PGPASSWORD"],
    port=os.environ.get("PGPORT", 5432)
)
c = conn.cursor()

# Таблицы
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,
    username TEXT,
    balance INTEGER DEFAULT 0
)
""")
c.execute("""
CREATE TABLE IF NOT EXISTS inventory (
    user_id BIGINT,
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

def get_rank(balance):
    if balance >= 10000:
        return "Генерал (S)"
    elif balance >= 3000:
        return "Полковник (AA)"
    elif balance >= 1801:
        return "Майор (A)"
    elif balance >= 1001:
        return "Капитан (B)"
    elif balance >= 501:
        return "Лейтенант (C)"
    elif balance >= 201:
        return "Сержант (D)"
    elif balance >= 35:
        return "Капрал (E)"
    else:
        return "Новобранец"

def main_menu():
    markup = telebot.types.InlineKeyboardMarkup()
    markup.row(
        telebot.types.InlineKeyboardButton("🛒 Магазин", callback_data="shop"),
        telebot.types.InlineKeyboardButton("🎒 Инвентарь", callback_data="inventory")
    )
    markup.row(
        telebot.types.InlineKeyboardButton("💰 Баланс", callback_data="balance"),
        telebot.types.InlineKeyboardButton("📊 Топ 10", callback_data="top")
    )
    markup.row(
        telebot.types.InlineKeyboardButton("📖 Инструкция", callback_data="help")
    )
    return markup

@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username or "unknown"
    c.execute("SELECT id FROM users WHERE id = %s", (user_id,))
    if not c.fetchone():
        c.execute("INSERT INTO users (id, username, balance) VALUES (%s, %s, %s)", (user_id, username, 0))
        conn.commit()
    greeting = (
        "Добро пожаловать в AvelShop!\n"
        "За Кепы вы можете приобрести:\n\n"
        " • 🎮 бонусы и скидки на участие\n"
        " • 🎁 эксклюзивные скины CS2\n"
        " • 👕 продукцию AVEL\n"
        " • 🎫 доступ к платным шоу-матчам\n"
        " • 👑 льготы и особые привилегии в комьюнити\n"
    )
    bot.send_message(user_id, greeting)
    bot.send_message(user_id, "📍 Главное меню:", reply_markup=main_menu())

@bot.message_handler(commands=["menu"])
def show_menu(message):
    bot.send_message(message.chat.id, "📍 Главное меню:", reply_markup=main_menu())

@bot.message_handler(commands=["admin"])
def show_admin_panel(message):
    user_id = message.from_user.id
    if user_id in ADMIN_IDS:
        bot.send_message(user_id, "🔧 Команды:\n/addskin <название> <цена>\n/removeskin <название>\n/add <id> <сумма>\n/remove <id> <сумма>\n/users — список пользователей")
    else:
        bot.send_message(user_id, "⛔ Доступ запрещён.")

shop_cache = {}

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    user_id = call.from_user.id

    if call.data == "balance":
        c.execute("SELECT balance FROM users WHERE id = %s", (user_id,))
        balance = c.fetchone()[0]
        rank = get_rank(balance)
        bot.answer_callback_query(call.id)
        bot.send_message(user_id, f"💰 У вас {balance} Кэпов 🎖\n🎖 Звание: {rank}")

    elif call.data == "inventory":
        c.execute("SELECT item FROM inventory WHERE user_id = %s", (user_id,))
        items = c.fetchall()
        if items:
            inv = "\n".join([f"• {item[0]}" for item in items])
            bot.send_message(user_id, f"🎒 Ваши скины:\n{inv}")
        else:
            bot.send_message(user_id, "🎒 Ваш инвентарь пуст.")

    elif call.data == "shop":
        c.execute("DELETE FROM shop WHERE name IS NULL OR price IS NULL")
        conn.commit()

        c.execute("SELECT name, price FROM shop ORDER BY price DESC")
        skins = c.fetchall()

        if not skins:
            bot.send_message(user_id, "⛔ Магазин временно пуст.")
            return

        msg = "🎁 Доступные скины:\n\n"
        markup = telebot.types.InlineKeyboardMarkup(row_width=1)
        shop_cache[user_id] = {}

        for idx, (name, price) in enumerate(skins):
            shop_cache[user_id][str(idx)] = name
            msg += f"• {name}\nЦена: {price} Кэпов 🎖\n\n"
            markup.add(telebot.types.InlineKeyboardButton(f"Купить: {name[:50]}", callback_data=f"buyid|{idx}"))

        bot.send_message(user_id, msg.strip(), reply_markup=markup)

    elif call.data.startswith("buyid|"):
        idx = call.data.split("|", 1)[1]
        item = shop_cache.get(user_id, {}).get(idx)

        if not item:
            bot.send_message(user_id, "❌ Не удалось определить скин.")
            return

        c.execute("SELECT price FROM shop WHERE name = %s", (item,))
        result = c.fetchone()
        if not result:
            bot.send_message(user_id, "❌ Скин не найден.")
            return

        price = result[0]
        c.execute("SELECT balance FROM users WHERE id = %s", (user_id,))
        balance_result = c.fetchone()
        if not balance_result:
            bot.send_message(user_id, "❌ Пользователь не найден.")
            return

        balance = balance_result[0]
        if balance < price:
            bot.send_message(user_id, "⛔ Недостаточно Кэпов.")
            return

        c.execute("SELECT 1 FROM inventory WHERE user_id = %s AND item = %s", (user_id, item))
        if c.fetchone():
            bot.send_message(user_id, "📦 У вас уже есть этот скин.")
            return

        c.execute("UPDATE users SET balance = balance - %s WHERE id = %s", (price, user_id))
        c.execute("INSERT INTO inventory (user_id, item) VALUES (%s, %s)", (user_id, item))
        c.execute("DELETE FROM shop WHERE name = %s", (item,))
        conn.commit()
        bot.send_message(user_id, f"✅ Вы успешно приобрели: {item}")

    elif call.data == "top":
        c.execute("SELECT id, username, balance FROM users ORDER BY balance DESC")
        users = c.fetchall()
        msg = "🏆 Топ 10 по КЭПам:\n"
        for i, (uid, uname, bal) in enumerate(users[:10], 1):
            msg += f"{i}. @{uname or 'unknown'} - {bal} 🎖 ({get_rank(bal)})\n"
        user_place = next((i+1 for i, (uid, _, _) in enumerate(users) if uid == user_id), None)
        msg += f"\nВы на {user_place} месте."
        bot.send_message(user_id, msg)

    elif call.data == "help":
        help_msg = (
            "КЕП — это внутренняя система рейтинга активности игроков в комьюнити AVEL.\n"
            "Участники зарабатывают КЕПЫ за участие в турнирах, победы, вклад в развитие и поддержку комьюнити.\n\n"
            "🔒 КЕПЫ нельзя купить. Их можно только заработать.\n"
            "🎖 Как заработать КЕПЫ?\n\n"
            "Участие в турнире +5\nВыход в полуфинал +5\nВыход в финал +10\nПобеда в турнире +25\nMVP турнира +10\n"
            "Привёл нового участника +10\nПомощь организатору/стримеру +5–10\nКапитан команды +10\n"
            "Помощь в развитии комьюнити +5–10\nДонат +5–35\nСпонсорство +10\nШоу-матч +5\n"
            "2000+ ELO (+20 после 10 lvl) +20 (единожды)\n\n"
            "🚫 Штрафы:\nНе пришёл -50\nОпоздание -10\nТоксичность -10\nБан -30\nОтмена без причины -10\n"
            "⚠️ Применяются после 3 турниров подряд.\n\n"
            "🧱 Ранги:\n35–200 Капрал (E)\n201–500 Сержант (D)\n501–1000 Лейтенант (C)\n1001–1800 Капитан (B)\n"
            "1801–3000 Майор (A)\n3000–9999 Полковник (AA)\n10000+ Генерал (S)"
        )
        bot.send_message(user_id, help_msg)

@bot.message_handler(commands=["addskin", "removeskin", "add", "remove", "users"])
def admin_commands(message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        return
    cmd = message.text.split()

    if message.text.startswith("/addskin") and len(cmd) >= 3:
        name, price = " ".join(cmd[1:-1]), int(cmd[-1])
        c.execute("INSERT INTO shop (name, price) VALUES (%s, %s)", (name, price))
        conn.commit()
        bot.reply_to(message, "✅ Скин добавлен.")

    elif message.text.startswith("/removeskin") and len(cmd) >= 2:
        name = " ".join(cmd[1:])
        c.execute("DELETE FROM shop WHERE name = %s", (name,))
        conn.commit()
        bot.reply_to(message, "✅ Скин удалён.")

    elif message.text.startswith("/add") and len(cmd) == 3:
        target_id, amount = int(cmd[1]), int(cmd[2])
        c.execute("SELECT id FROM users WHERE id = %s", (target_id,))
        if not c.fetchone():
            bot.reply_to(message, "❌ Пользователь не найден.")
        else:
            c.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (amount, target_id))
            conn.commit()
            bot.reply_to(message, "✅ Кэпы добавлены.")

    elif message.text.startswith("/remove") and len(cmd) == 3:
        target_id, amount = int(cmd[1]), int(cmd[2])
        c.execute("SELECT id FROM users WHERE id = %s", (target_id,))
        if not c.fetchone():
            bot.reply_to(message, "❌ Пользователь не найден.")
        else:
            c.execute("UPDATE users SET balance = balance - %s WHERE id = %s", (amount, target_id))
            conn.commit()
            bot.reply_to(message, "✅ Кэпы удалены.")

    elif message.text.startswith("/users"):
        c.execute("SELECT username, id, balance FROM users ORDER BY balance DESC")
        users = c.fetchall()
        msg = "📋 Зарегистрированные пользователи:\n"
        for username, uid, balance in users:
            msg += f"@{username or 'unknown'} — {uid} — {balance} КЭПов 🎖\n"
        bot.send_message(user_id, msg)

@app.route("/", methods=["POST"])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "", 200

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    from waitress import serve
    serve(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
