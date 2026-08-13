import asyncio
import datetime
import os
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiohttp import web

# --- ТАНЗИМОТ ---
TOKEN = os.getenv("TOKEN", "8560757080:AAGb9WJWfo3R9RsAA1CY37L-zmrcluov3xY")
YOUR_TELEGRAM_ID = int(
    os.getenv("YOUR_TELEGRAM_ID", "6900346716")
)  # ID-и худро аз @userinfobot гиред

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- БАЗАИ МАЪЛУМОТ ---
conn = sqlite3.connect("expenses.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute(
    """
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    type TEXT,
    amount REAL,
    category TEXT,
    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""
)

cursor.execute(
    """
CREATE TABLE IF NOT EXISTS active_shifts (
    user_id INTEGER PRIMARY KEY,
    start_time TIMESTAMP
)
"""
)
conn.commit()


# --- МУҲОФИЗАТ (БАРДОШТАНИ ДАСТРАСӢ БАРОИ БЕГОНАҲО) ---
@dp.message(F.from_user.id != YOUR_TELEGRAM_ID)
async def block_unauthorized_messages(message: types.Message):
    return  # Ба одамони бегона ҳеҷ ҷавоб намедиҳад


@dp.callback_query(F.from_user.id != YOUR_TELEGRAM_ID)
async def block_unauthorized_callbacks(callback: types.CallbackQuery):
    await callback.answer("Дастрасӣ манъ аст!", show_alert=True)


# --- ТУГМАҲОИ МАҲФӢ ---
def work_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🛠 Кор", callback_data="work_start"),
                InlineKeyboardButton(text="🏁 Рафтам", callback_data="work_end"),
                InlineKeyboardButton(
                    text="❌ Наомадам", callback_data="work_skip"
                ),
            ]
        ]
    )


def finance_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💰 Баланс ва Омор", callback_data="show_balance"
                ),
                InlineKeyboardButton(
                    text="📈 Омори ҳафта", callback_data="stats_week"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Сабти охиринро нест кардан",
                    callback_data="delete_last",
                )
            ],
        ]
    )


def get_msk_time():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=3)


# --- ФАРМОНҲО ВА КАЛИМАҲОИ МАҲФӢ ---
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "👋 Салом Админ!\n\n"
        "🔑 **Калимаҳои махфӣ:**\n"
        "• Нависед **`кор`** — барои кушодани тугмаҳои корӣ\n"
        "• Нависед **`хароҷот`** ё **`баланс`** — барои тугмаҳои молиявӣ\n\n"
        "✍️ **Сабтҳо:**\n"
        "• `300 такси` (хароҷот)\n"
        "• `+2000 аванс` (даромад)",
        parse_mode="Markdown",
    )


@dp.message(F.text.lower().in_(["кор", "work", "табел"]))
async def show_work_menu(message: types.Message):
    await message.answer(
        "🛠 **Панели корӣ:**", reply_markup=work_menu(), parse_mode="Markdown"
    )


@dp.message(
    F.text.lower().in_(["хароҷот", "харочот", "баланс", "омор", "пул"])
)
async def show_finance_menu(message: types.Message):
    await message.answer(
        "💰 **Панели молиявӣ:**",
        reply_markup=finance_menu(),
        parse_mode="Markdown",
    )


# --- ФУНКСИЯҲОИ ТАБЕЛИ КОРӢ (ҲИСОБИ 10 СОАТ ВА ОБЕД) ---
@dp.callback_query(F.data == "work_start")
async def work_start(callback: types.CallbackQuery):
    now = get_msk_time()
    cursor.execute(
        "INSERT OR REPLACE INTO active_shifts (user_id, start_time) VALUES"
        " (?, ?)",
        (callback.from_user.id, now.strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    await callback.message.answer(
        f"🛠 **Кор оғоз шуд!**\nСоати баромад: **{now.strftime('%H:%M')}**\nКорхотон"
        " омад кунад!",
        parse_mode="Markdown",
    )


@dp.callback_query(F.data == "work_end")
async def work_end(callback: types.CallbackQuery):
    cursor.execute(
        "SELECT start_time FROM active_shifts WHERE user_id = ?",
        (callback.from_user.id,),
    )
    row = cursor.fetchone()

    if not row:
        await callback.message.answer(
            "⚠️ Шумо аввал тугмаи **🛠 Кор**-ро пахш накардаед!"
        )
        return

    start_time = datetime.datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
    now = get_msk_time()

    # Ҳисоби вақт
    duration = now - start_time
    total_minutes = int(duration.total_seconds() / 60)

    full_hours = total_minutes // 60
    remaining_mins = total_minutes % 60

    # Округление: Агар дақиқа аз 45 боло бошад (мисол: 18:56), ба соати пурра гузаронида мешавад
    if remaining_mins >= 45:
        full_hours += 1

    # Минус 1 соат обед (агар кор аз 4 соат бештар бошад)
    if full_hours >= 4:
        work_hours = full_hours - 1
    else:
        work_hours = max(0, full_hours)

    earned_rubles = round(work_hours * 500, 2)  # 500 рубл/соат

    # Сабт ба даромадҳо
    cursor.execute(
        "INSERT INTO transactions (user_id, type, amount, category) VALUES (?, "
        "'income', ?, ?)",
        (
            callback.from_user.id,
            earned_rubles,
            f"Кор ({work_hours} соат, 1 соат обед минус шуд)",
        ),
    )
    cursor.execute(
        "DELETE FROM active_shifts WHERE user_id = ?", (callback.from_user.id,)
    )
    conn.commit()

    await callback.message.answer(
        f"🏁 **Кор ба охир расид!**\n\n"
        f"⏱ Соати кори соф: **{work_hours} соат** (1 соат обед тарҳ шуд)\n"
        f"💵 Маоши ҳисобшуда: **{earned_rubles} рубл**\n"
        f"✅ Маблағ ба баланс илова карда шуд!",
        parse_mode="Markdown",
    )


@dp.callback_query(F.data == "work_skip")
async def work_skip(callback: types.CallbackQuery):
    cursor.execute(
        "DELETE FROM active_shifts WHERE user_id = ?", (callback.from_user.id,)
    )
    conn.commit()
    await callback.message.answer("❌ Имрӯз истироҳат сабт шуд.")


# --- БАЛАНС ВА ОМОР ---
@dp.callback_query(F.data == "show_balance")
async def show_balance(callback: types.CallbackQuery):
    cursor.execute(
        "SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type ="
        " 'income'",
        (callback.from_user.id,),
    )
    total_income = cursor.fetchone()[0] or 0.0

    cursor.execute(
        "SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type ="
        " 'expense'",
        (callback.from_user.id,),
    )
    total_expense = cursor.fetchone()[0] or 0.0

    balance = total_income - total_expense

    msg = (
        f"💰 **Ҳолати Молиявӣ:**\n\n"
        f"📥 Даромади умумӣ: **{total_income} рубл**\n"
        f"📤 Хароҷоти умумӣ: **{total_expense} рубл**\n"
        f"-----------------------------\n"
        f"💵 **Боқимонда (Баланс): {balance} рубл**"
    )
    await callback.message.answer(msg, parse_mode="Markdown")


@dp.callback_query(F.data == "stats_week")
async def send_stats_week(callback: types.CallbackQuery):
    cursor.execute(
        "SELECT category, SUM(amount) FROM transactions WHERE type = 'expense'"
        " AND date >= date('now', '-7 days') GROUP BY category"
    )
    data = cursor.fetchall()
    msg = "📊 **Хароҷоти 7 рӯзи охир:**\n\n"
    if not data:
        msg += "Ҳеҷ хароҷоте сабт نشده аст."
    for row in data:
        msg += f"• {row[0]}: {row[1]} рубл\n"
    await callback.message.answer(msg, parse_mode="Markdown")


@dp.callback_query(F.data == "delete_last")
async def delete_last(callback: types.CallbackQuery):
    cursor.execute(
        "SELECT id, amount, category FROM transactions WHERE user_id = ?"
        " ORDER BY id DESC LIMIT 1",
        (callback.from_user.id,),
    )
    row = cursor.fetchone()
    if row:
        cursor.execute("DELETE FROM transactions WHERE id = ?", (row[0],))
        conn.commit()
        await callback.message.answer(
            f"🗑 Сабти охирин нест карда шуд: {row[1]} рубл - {row[2]}"
        )
    else:
        await callback.message.answer("⚠️ Ҳеҷ сабте ёфт нашуд.")


# --- САБТИ ТЕКСТИИ ХАРОҶОТ ВА ДАРОМАД ---
@dp.message()
async def add_transaction(message: types.Message):
    text = message.text.strip()
    try:
        if text.startswith("+"):
            clean_text = text[1:].strip()
            parts = clean_text.split(maxsplit=1)
            amount = float(parts[0])
            category = parts[1] if len(parts) > 1 else "Даромади иловагӣ"

            cursor.execute(
                "INSERT INTO transactions (user_id, type, amount, category)"
                " VALUES (?, 'income', ?, ?)",
                (message.from_user.id, amount, category),
            )
            conn.commit()
            await message.answer(
                f"📥 Даромад сабт шуд: **+{amount} рубл** ({category})",
                parse_mode="Markdown",
            )
        else:
            parts = text.split(maxsplit=1)
            amount = float(parts[0])
            category = parts[1] if len(parts) > 1 else "Дигар"

            cursor.execute(
                "INSERT INTO transactions (user_id, type, amount, category)"
                " VALUES (?, 'expense', ?, ?)",
                (message.from_user.id, amount, category),
            )
            conn.commit()
            await message.answer(
                f"📤 Хароҷот сабт шуд: **-{amount} рубл** ({category})",
                parse_mode="Markdown",
            )
    except Exception:
        await message.answer(
            "⚠️ Фармони номаълум.\n"
            "• Нависед **`кор`** ё **`хароҷот`** барои тугмаҳо\n"
            "• Ё нависед: `300 такси`, `+2000 аванс`"
        )


# --- СМС ЁДРАСКУНИИ СУБҲОНА (СОАТИ 08:00) ---
async def send_and_delete_msg(text, reply_markup=None):
    try:
        msg = await bot.send_message(
            YOUR_TELEGRAM_ID, text, reply_markup=reply_markup
        )
        await asyncio.sleep(20 * 60)
        await bot.delete_message(
            chat_id=YOUR_TELEGRAM_ID, message_id=msg.message_id
        )
    except Exception as e:
        print(f"Хатогии смс: {e}")


async def daily_reminder_scheduler():
    while True:
        now_str = get_msk_time().strftime("%H:%M")
        if now_str == "08:00":
            asyncio.create_task(
                send_and_delete_msg(
                    "☀️ Салом! Хайрли субҳ!\nБа кор баромадед? Тугмаи 🛠"
                    " **Кор**-ро зер кунед.",
                    reply_markup=work_menu(),
                )
            )
            await asyncio.sleep(60)
        await asyncio.sleep(20)


# --- ВЕБ-СЕРВЕР БАРОИ RENDER (FREE WEB SERVICE) ---
async def handle(request):
    return web.Response(text="Bot is running 24/7!")


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()


async def main():
    await start_web_server()
    asyncio.create_task(daily_reminder_scheduler())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
