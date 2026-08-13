import asyncio
import datetime
import os
import sqlite3
from io import BytesIO

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from aiohttp import web

# Библиотекаҳо барои эҷоди PDF
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# --- ТАНЗИМОТ ---
TOKEN = os.getenv("TOKEN", "8560757080:AAGb9WJWfo3R9RsAA1CY37L-zmrcluov3xY")
YOUR_TELEGRAM_ID = int(os.getenv("YOUR_TELEGRAM_ID", "6900346716"))

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- БАЗАИ МАЪЛУМОТ (3 РӮЙХАТИ АЛОҲИДА) ---
conn = sqlite3.connect("expenses.db", check_same_thread=False)
cursor = conn.cursor()

# 1. Рӯйхати Кор (+ / - / соат / маблағ)
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS work_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    status TEXT, -- '+' ё '-'
    hours REAL,
    amount REAL,
    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""
)

# 2. Рӯйхати Қарзҳо (ба ки қарз додед)
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS debts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    person TEXT,
    amount REAL,
    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""
)

# 3. Рӯйхати Хароҷоти ҳаррӯза
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    category TEXT,
    amount REAL,
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


# --- МУҲОФИЗАТ ---
@dp.message(F.from_user.id != YOUR_TELEGRAM_ID)
async def block_unauthorized_messages(message: types.Message):
    return


@dp.callback_query(F.from_user.id != YOUR_TELEGRAM_ID)
async def block_unauthorized_callbacks(callback: types.CallbackQuery):
    await callback.answer("Дастрасӣ манъ аст!", show_alert=True)


# --- ТУГМАҲО ---
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
                    text="📄 PDF Ҳисобот", callback_data="export_pdf"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Сабти охирини хароҷотро нест кардан",
                    callback_data="delete_last",
                )
            ],
        ]
    )


def get_msk_time():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=3)


# --- ФАРМОНҲО ---
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "👋 Салом Админ!\n\n"
        "🔑 **Калимаҳои махфӣ:**\n"
        "• Нависед **`кор`** — тугмаҳои табели корӣ\n"
        "• Нависед **`хароҷот`** ё **`баланс`** — тугмаҳои молиявӣ\n\n"
        "✍️ **Намунаи сабтҳо:**\n"
        "• `300 такси` — Хароҷоти ҳаррӯза\n"
        "• `қарз Али 500` — Қарз додам ба Али\n"
        "• `+2000 аванс` — Даромади иловагӣ",
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


# --- ТАБЕЛИ КОРӢ ---
@dp.callback_query(F.data == "work_start")
async def work_start(callback: types.CallbackQuery):
    now = get_msk_time()
    cursor.execute(
        "INSERT OR REPLACE INTO active_shifts (user_id, start_time) VALUES (?, ?)",
        (callback.from_user.id, now.strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    await callback.message.answer(
        f"🛠 **Кор оғоз шуд!**\nСоати баромад: **{now.strftime('%H:%M')}**",
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

    duration = now - start_time
    total_minutes = int(duration.total_seconds() / 60)
    full_hours = total_minutes // 60
    remaining_mins = total_minutes % 60

    if remaining_mins >= 45:
        full_hours += 1

    if full_hours >= 4:
        work_hours = full_hours - 1
    else:
        work_hours = max(0, full_hours)

    earned_rubles = round(work_hours * 500, 2)

    # Сабт ба рӯйхати 1 (Кор)
    cursor.execute(
        "INSERT INTO work_log (user_id, status, hours, amount) VALUES (?, '+', ?, ?)",
        (callback.from_user.id, work_hours, earned_rubles),
    )
    cursor.execute(
        "DELETE FROM active_shifts WHERE user_id = ?", (callback.from_user.id,)
    )
    conn.commit()

    await callback.message.answer(
        f"🏁 **Кор ба охир расид!** (+)\n"
        f"⏱ Соати корӣ: **{work_hours} соат**\n"
        f"💵 Маблағ: **{earned_rubles} рубл**",
        parse_mode="Markdown",
    )


@dp.callback_query(F.data == "work_skip")
async def work_skip(callback: types.CallbackQuery):
    cursor.execute(
        "INSERT INTO work_log (user_id, status, hours, amount) VALUES (?, '-', 0, 0)",
        (callback.from_user.id,),
    )
    cursor.execute(
        "DELETE FROM active_shifts WHERE user_id = ?", (callback.from_user.id,)
    )
    conn.commit()
    await callback.message.answer("❌ Наомадам сабт шуд (-).")


# --- САБТИ ТЕКСТИИ ХАРОҶОТ, ҚАРЗ ВА ДАРОМАД ---
@dp.message()
async def add_transaction(message: types.Message):
    text = message.text.strip()
    try:
        # Сабти Қарз (Масалан: "қарз Али 500" ё "карз Васеъ 1000")
        if text.lower().startswith(("қарз", "карз")):
            parts = text.split(maxsplit=2)
            person = parts[1]
            amount = float(parts[2])
            cursor.execute(
                "INSERT INTO debts (user_id, person, amount) VALUES (?, ?, ?)",
                (message.from_user.id, person, amount),
            )
            conn.commit()
            await message.answer(
                f"🤝 Қарз сабт шуд: **{person}** -> **{amount} рубл**",
                parse_mode="Markdown",
            )

        # Сабти Даромади иловагӣ (Масалан: "+2000 аванс")
        elif text.startswith("+"):
            clean_text = text[1:].strip()
            parts = clean_text.split(maxsplit=1)
            amount = float(parts[0])
            cursor.execute(
                "INSERT INTO work_log (user_id, status, hours, amount) VALUES (?, '+', 0, ?)",
                (message.from_user.id, amount),
            )
            conn.commit()
            await message.answer(
                f"📥 Даромади иловагӣ сабт шуд: **+{amount} рубл**",
                parse_mode="Markdown",
            )

        # Хароҷоти ҳаррӯза (Масалан: "300 такси")
        else:
            parts = text.split(maxsplit=1)
            amount = float(parts[0])
            category = parts[1] if len(parts) > 1 else "Хариди умумӣ"
            cursor.execute(
                "INSERT INTO expenses (user_id, category, amount) VALUES (?, ?, ?)",
                (message.from_user.id, category, amount),
            )
            conn.commit()
            await message.answer(
                f"📤 Хароҷот сабт шуд: **-{amount} рубл** ({category})",
                parse_mode="Markdown",
            )

    except Exception:
        await message.answer(
            "⚠️ Фармони номаълум!\n"
            "• Кор: `кор` ё `хароҷот`\n"
            "• Хароҷот: `300 такси`\n"
            "• Қарз: `қарз Али 500`"
        )


# --- ЭҶОДИ ҲИСОБОТИ PDF (3 РӮЙХАТИ АЛОҲИДА) ---
@dp.callback_query(F.data == "export_pdf")
async def export_pdf(callback: types.CallbackQuery):
    await callback.message.answer("🔄 Файли PDF тайёр шуда истодааст...")

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    # 1. ТАБЛИЦАИ 1: Рӯйхати Соати Корӣ ва Маблағ
    cursor.execute(
        "SELECT date, status, hours, amount FROM work_log WHERE user_id = ? ORDER BY id DESC",
        (callback.from_user.id,),
    )
    work_data = [["Таърих", "Статус", "Соат", "Маблағ (рубл)"]]
    for r in cursor.fetchall():
        work_data.append([str(r[0])[:10], r[1], str(r[2]), str(r[3])])

    elements.append(Paragraph("<b>1. Ruikhati Kori va Mablag</b>", styles["Title"]))
    elements.append(Spacer(1, 10))
    t1 = Table(work_data)
    t1.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4CAF50")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    elements.append(t1)
    elements.append(Spacer(1, 20))

    # 2. ТАБЛИЦАИ 2: Рӯйхати Қарзҳо
    cursor.execute(
        "SELECT date, person, amount FROM debts WHERE user_id = ? ORDER BY id DESC",
        (callback.from_user.id,),
    )
    debt_data = [["Таърих", "Ба ки (Шахс)", "Маблағ (рубл)"]]
    for r in cursor.fetchall():
        debt_data.append([str(r[0])[:10], r[1], str(r[2])])

    elements.append(
        Paragraph("<b>2. Ruikhati Qarzhoi Dodashuda</b>", styles["Title"])
    )
    elements.append(Spacer(1, 10))
    t2 = Table(debt_data)
    t2.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FF9800")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    elements.append(t2)
    elements.append(Spacer(1, 20))

    # 3. ТАБЛИЦАИ 3: Рӯйхати Хароҷот (Харид)
    cursor.execute(
        "SELECT date, category, amount FROM expenses WHERE user_id = ? ORDER BY id DESC",
        (callback.from_user.id,),
    )
    exp_data = [["Таърих", "Категория / Харид", "Маблағ (рубл)"]]
    for r in cursor.fetchall():
        exp_data.append([str(r[0])[:10], r[1], str(r[2])])

    elements.append(
        Paragraph("<b>3. Ruikhati Kharojoti Harruza</b>", styles["Title"])
    )
    elements.append(Spacer(1, 10))
    t3 = Table(exp_data)
    t3.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F44336")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    elements.append(t3)

    # Сохтани PDF
    doc.build(elements)
    buffer.seek(0)

    pdf_file = BufferedInputFile(buffer.read(), filename="Hisobot.pdf")
    await callback.message.answer_document(
        pdf_file, caption="📊 Ҳисоботи пӯрра дар файли PDF"
    )


# --- ОМОР ВА БАЛАНС ---
@dp.callback_query(F.data == "show_balance")
async def show_balance(callback: types.CallbackQuery):
    cursor.execute(
        "SELECT SUM(amount) FROM work_log WHERE user_id = ?",
        (callback.from_user.id,),
    )
    total_income = cursor.fetchone()[0] or 0.0

    cursor.execute(
        "SELECT SUM(amount) FROM expenses WHERE user_id = ?",
        (callback.from_user.id,),
    )
    total_expense = cursor.fetchone()[0] or 0.0

    cursor.execute(
        "SELECT SUM(amount) FROM debts WHERE user_id = ?",
        (callback.from_user.id,),
    )
    total_debts = cursor.fetchone()[0] or 0.0

    balance = total_income - total_expense

    msg = (
        f"💰 **Ҳолати Молиявӣ:**\n\n"
        f"📥 Даромад (Кор): **{total_income} рубл**\n"
        f"📤 Хароҷот (Харид): **{total_expense} рубл**\n"
        f"🤝 Қарзҳои додашуда: **{total_debts} рубл**\n"
        f"-----------------------------\n"
        f"💵 **Боқимонда (Баланс): {balance} рубл**"
    )
    await callback.message.answer(msg, parse_mode="Markdown")


@dp.callback_query(F.data == "delete_last")
async def delete_last(callback: types.CallbackQuery):
    cursor.execute(
        "SELECT id, amount, category FROM expenses WHERE user_id = ? ORDER BY id DESC LIMIT 1",
        (callback.from_user.id,),
    )
    row = cursor.fetchone()
    if row:
        cursor.execute("DELETE FROM expenses WHERE id = ?", (row[0],))
        conn.commit()
        await callback.message.answer(
            f"🗑 Сабти охирини хароҷот нест карда шуд: {row[1]} рубл - {row[2]}"
        )
    else:
        await callback.message.answer("⚠️ Ҳеҷ сабте ёфт нашуд.")


# --- ЁДРАСКУНИИ СУБҲОНА ---
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
                    "☀️ Салом! Ба кор баромадед? Тугмаи 🛠 **Кор**-ро зер кунед.",
                    reply_markup=work_menu(),
                )
            )
            await asyncio.sleep(60)
        await asyncio.sleep(20)


# --- ВЕБ-СЕРВЕР ---
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
