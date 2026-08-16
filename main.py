import asyncio
import datetime
import os
import sqlite3

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from aiohttp import web
from weasyprint import HTML

# --- ТАНЗИМОТ ---
TOKEN = os.getenv("TOKEN", "8560757080:AAGb9WJWfo3R9RsAA1CY37L-zmrcluov3xY")
YOUR_TELEGRAM_ID = int(os.getenv("YOUR_TELEGRAM_ID", "6900346716"))

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- БАЗАИ МАЪЛУМОТ ---
conn = sqlite3.connect("expenses.db", check_same_thread=False)
cursor = conn.cursor()

# 1. Табели корӣ (+ / - / соат / маблағ)
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

# 2. Рӯйхати Қарзҳо
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

# 3. Рӯйхати Хароҷот
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
            ],
            [
                InlineKeyboardButton(
                    text="📋 PDF Табели Кор", callback_data="export_tabel_pdf"
                )
            ],
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
                    text="📄 Пурра PDF Ҳисобот", callback_data="export_pdf"
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


# --- ФАРМОНҲО ---
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "👋 Салом Админ!\n\n"
        "🔑 **Калимаҳои махфӣ:**\n"
        "• Нависед **`кор`** — тугмаҳои табели корӣ ва генерацияи PDF\n"
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
        "🛠 **Панели кори ва Табел:**",
        reply_markup=work_menu(),
        parse_mode="Markdown",
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


# --- ГЕНЕРАЦИЯИ PDF ТАБЕЛИ КОР ---
@dp.callback_query(F.data == "export_tabel_pdf")
async def export_tabel_pdf(callback: types.CallbackQuery):
    await callback.message.answer("🔄 PDF Табели корӣ сохта шуда истодааст...")

    cursor.execute(
        "SELECT date, status, hours, amount FROM work_log WHERE user_id = ? ORDER BY id ASC",
        (callback.from_user.id,),
    )
    rows = cursor.fetchall()

    total_days = len(rows)
    worked_days = sum(1 for r in rows if r[1] == "+")
    skipped_days = sum(1 for r in rows if r[1] == "-")
    total_hours = sum(r[2] for r in rows)
    total_amount = sum(r[3] for r in rows)

    table_rows_html = ""
    for idx, r in enumerate(rows, 1):
        date_str = str(r[0])[:10]
        status_badge = (
            '<span class="badge badge-success">+ Омад</span>'
            if r[1] == "+"
            else '<span class="badge badge-danger">- Наомад</span>'
        )
        table_rows_html += f"""
        <tr>
            <td>{idx}</td>
            <td>{date_str}</td>
            <td>{status_badge}</td>
            <td>{r[2]} соат</td>
            <td>{r[3]:,.2f} ₽</td>
        </tr>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            @page {{
                size: A4;
                margin: 15mm;
                background-color: #f8fafc;
            }}
            body {{
                font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
                color: #1e293b;
                margin: 0;
                padding: 0;
            }}
            .header {{
                background: linear-gradient(135deg, #1e3a8a, #3b82f6);
                color: #ffffff;
                padding: 24px;
                border-radius: 12px;
                margin-bottom: 24px;
            }}
            .header h1 {{
                margin: 0 0 6px 0;
                font-size: 22pt;
            }}
            .stats-grid {{
                display: table;
                width: 100%;
                margin-bottom: 24px;
            }}
            .stat-card {{
                display: table-cell;
                width: 25%;
                background: #ffffff;
                padding: 14px;
                border-radius: 8px;
                border: 1px solid #e2e8f0;
                text-align: center;
            }}
            .stat-value {{
                font-size: 16pt;
                font-weight: bold;
                color: #0f172a;
            }}
            .stat-label {{
                font-size: 9pt;
                color: #64748b;
                margin-top: 4px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                background: #ffffff;
                border-radius: 8px;
                overflow: hidden;
                border: 1px solid #e2e8f0;
            }}
            th {{
                background-color: #f1f5f9;
                color: #334155;
                font-weight: bold;
                text-align: left;
                padding: 10px 12px;
                font-size: 10pt;
                border-bottom: 2px solid #cbd5e1;
            }}
            td {{
                padding: 10px 12px;
                font-size: 10pt;
                border-bottom: 1px solid #e2e8f0;
            }}
            .badge {{
                padding: 4px 8px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 8pt;
            }}
            .badge-success {{ background-color: #dcfce7; color: #166534; }}
            .badge-danger {{ background-color: #fee2e2; color: #991b1b; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📋 Табели Кори ва Маош</h1>
            <p style="margin:0; opacity:0.9;">Ҳисоботи соатҳои корӣ ва маблағи ҳисобшуда</p>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{worked_days} / {total_days}</div>
                <div class="stat-label">Рӯзҳои корӣ</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{skipped_days}</div>
                <div class="stat-label">Наомада</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{total_hours} соат</div>
                <div class="stat-label">Ҷамъи соат</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" style="color:#16a34a;">{total_amount:,.2f} ₽</div>
                <div class="stat-label">Ҷамъи маош</div>
            </div>
        </div>

        <table>
            <thead>
                <tr>
                    <th>№</th>
                    <th>Таърих</th>
                    <th>Статус</th>
                    <th>Соати корӣ</th>
                    <th>Маблағи корӣ</th>
                </tr>
            </thead>
            <tbody>
                {table_rows_html}
            </tbody>
        </table>
    </body>
    </html>
    """

    pdf_bytes = HTML(string=html_content).write_pdf()
    pdf_file = BufferedInputFile(pdf_bytes, filename="Tabel_Kori.pdf")
    await callback.message.answer_document(
        pdf_file, caption="📋 Табели кории шумо дар формати PDF"
    )


# --- САБТИ ТЕКСТИИ ХАРОҶОТ, ҚАРЗ ВА ДАРОМАД ---
@dp.message()
async def add_transaction(message: types.Message):
    text = message.text.strip()
    try:
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
            "• Нависед **`кор`** барои табел ва PDF\n"
            "• Хароҷот: `300 такси`\n"
            "• Қарз: `қарз Али 500`"
        )


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
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
