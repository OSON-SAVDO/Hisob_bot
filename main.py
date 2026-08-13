import asyncio
import datetime
import os
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiohttp import web

# Переменныйҳои муҳит (ба ҷои инҳо дар Render Environment Variables мегузоред)
TOKEN = os.getenv("TOKEN", "8560757080:AAGb9WJWfo3R9RsAA1CY37L-zmrcluov3xY")
YOUR_TELEGRAM_ID = int(os.getenv("YOUR_TELEGRAM_ID", "6900346716"))

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Базаи маълумот
conn = sqlite3.connect("expenses.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute(
    "CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " user_id INTEGER, amount REAL, category TEXT, date TIMESTAMP DEFAULT"
    " CURRENT_TIMESTAMP)"
)
conn.commit()


# Тугмаҳо
def main_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📈 Ҳисоботи ҳафта", callback_data="stats_week"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💰 Ҳамаи хароҷот", callback_data="stats_all"
                )
            ],
        ]
    )


# Командаи /start
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "Салом! Хароҷоти худро нависед (мисол: 500 такси).",
        reply_markup=main_menu(),
    )


# Ҳисоботи ҳафтаина
@dp.callback_query(F.data == "stats_week")
async def send_stats_week(callback: types.CallbackQuery):
    cursor.execute(
        "SELECT category, SUM(amount) FROM expenses WHERE date >= date('now',"
        " '-7 days') GROUP BY category"
    )
    data = cursor.fetchall()
    msg = "📊 **Хароҷоти 7 рӯзи охир:**\n\n"
    if not data:
        msg += "Ҳеҷ хароҷоте сабт нашудааст."
    for row in data:
        msg += f"• {row[0]}: {row[1]} рубл\n"
    await callback.message.answer(msg, parse_mode="Markdown")


# Ҳамаи хароҷотҳо
@dp.callback_query(F.data == "stats_all")
async def send_stats_all(callback: types.CallbackQuery):
    cursor.execute(
        "SELECT category, SUM(amount) FROM expenses GROUP BY category"
    )
    data = cursor.fetchall()
    msg = "💰 **Ҳамаи хароҷот аз рӯзи оғоз:**\n\n"
    if not data:
        msg += "Ҳеҷ хароҷоте сабт нашудааст."
    for row in data:
        msg += f"• {row[0]}: {row[1]} рубл\n"
    await callback.message.answer(msg, parse_mode="Markdown")


# Сабти хароҷоти нав
@dp.message()
async def add_expense(message: types.Message):
    try:
        parts = message.text.split(maxsplit=1)
        amount = float(parts[0])
        category = parts[1] if len(parts) > 1 else "Дигар"
        cursor.execute(
            "INSERT INTO expenses (user_id, amount, category) VALUES (?, ?,"
            " ?)",
            (message.from_user.id, amount, category),
        )
        conn.commit()
        await message.answer(
            f"✅ {amount} рубл сабт шуд: {category}", reply_markup=main_menu()
        )
    except Exception:
        await message.answer(
            "Хатогӣ! Лутфан аввал рақамро нависед (мисол: 300 хӯрок)."
        )


# Функсияи фиристодан ва нест кардани смс
async def send_and_delete_msg():
    try:
        msg = await bot.send_message(
            YOUR_TELEGRAM_ID,
            "⏰ Салом! Фаромӯш накунед, ки хароҷоти имрӯзаро сабт кунед.",
        )
        await asyncio.sleep(20 * 60)  # 20 дақиқа интизор шудан
        await bot.delete_message(
            chat_id=YOUR_TELEGRAM_ID, message_id=msg.message_id
        )
    except Exception as e:
        print(f"Хатогӣ: {e}")


# Нақшакаши ёдраскунӣ (5 маротиба дар як рӯз)
async def daily_reminder_scheduler():
    reminder_times = ["09:00", "12:00", "15:00", "18:00", "21:00"]
    while True:
        now = datetime.datetime.now().strftime("%H:%M")
        if now in reminder_times:
            asyncio.create_task(send_and_delete_msg())
            await asyncio.sleep(60)
        await asyncio.sleep(20)


# Веб-сервери содда барои он ки Render хатогии Port бидуни пардохт надиҳад
async def handle(request):
    return web.Response(text="Bot is running!")


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
