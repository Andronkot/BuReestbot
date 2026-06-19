import os
import sqlite3
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

TOKEN = os.getenv("TOKEN")

conn = sqlite3.connect("bot.db", check_same_thread=False)
cur = conn.cursor()

# ---------------- DB ----------------

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    tg_id TEXT,
    username TEXT UNIQUE,
    first_name TEXT,
    name TEXT,
    nick TEXT,
    game_id TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS violations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    type TEXT,
    reason TEXT,
    created_at TEXT,
    moderator TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")

#БД НАПОМИНАЛКИ
cur.execute("""
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    period TEXT,
    time TEXT,
    text TEXT,
    next_run INTEGER,
    created_by TEXT,
    last_sent TEXT
)
""")

# ДЕФ НАСТРОЙКИ ОТОБРАЖЕНИЯ

cur.execute(
    "INSERT OR IGNORE INTO settings VALUES (?, ?)",
    ("relist_mode", "username")
)

cur.execute(
    "INSERT OR IGNORE INTO settings VALUES (?, ?)",
    ("display_mode", "username")
)

conn.commit()

# ЧАСОВОЙ ПОЯС
KYIV_TZ = ZoneInfo("Europe/Kyiv")

REMINDER_DAYS = {
    "понедельник": 0,
    "вторник": 1,
    "среда": 2,
    "четверг": 3,
    "пятница": 4,
    "суббота": 5,
    "воскресенье": 6
}

# ---------------- HELPERS ----------------

# ЧЕККЕР ДОБАВЛЕНИЯ ПОЛЬЗОВАТЕЛЯ В БД
def user_exists(uid):

    cur.execute(
        """
        SELECT 1
        FROM users
        WHERE username=? OR tg_id=?
        """,
        (uid, uid)
    )

    return cur.fetchone() is not None

# SYNC USER

def sync_user(user):

    tg_id = str(user.id)
    username = user.username or ""
    first_name = user.first_name or ""

    # ИЩЕМ ПО TG_ID

    cur.execute(
        """
        SELECT username
        FROM users
        WHERE tg_id=?
        """,
        (tg_id,)
    )

    row = cur.fetchone()

    if row:

        cur.execute(
            """
            UPDATE users
            SET
                username=?,
                first_name=?
            WHERE tg_id=?
            """,
            (
                username,
                first_name,
                tg_id
            )
        )

        conn.commit()
        return

    # ИЩЕМ ПО USERNAME

    if username:

        cur.execute(
            """
            SELECT username
            FROM users
            WHERE username=?
            """,
            (username,)
        )

        row = cur.fetchone()

        if row:

            cur.execute(
                """
                UPDATE users
                SET
                    tg_id=?,
                    first_name=?
                WHERE username=?
                """,
                (
                    tg_id,
                    first_name,
                    username
                )
            )

            conn.commit()
            return

    # ПОЛЬЗОВАТЕЛЬ БЕЗ USERNAME

    if not username and first_name:

        cur.execute(
            """
            SELECT username
            FROM users
            WHERE tg_id IS NULL
            """
        )

        rows = cur.fetchall()

        matches = []

        for row in rows:

            stored_username = row[0]

            if not stored_username:
                continue

            if stored_username.lower() == first_name.lower():

                matches.append(stored_username)

        if len(matches) == 1:

            cur.execute(
                """
                UPDATE users
                SET
                    tg_id=?,
                    first_name=?
                WHERE username=?
                """,
                (
                    tg_id,
                    first_name,
                    matches[0]
                )
            )

            conn.commit()
            return

# SETTINGS

def get_setting(key):

    cur.execute(
        "SELECT value FROM settings WHERE key=?",
        (key,)
    )

    row = cur.fetchone()

    if row:
        return row[0]

    # значения по умолчанию

    if key == "os":
        set_setting("os", "username")
        return "username"

    if key == "ok":
        set_setting("ok", "username")
        return "username"

    return None


def set_setting(key, value):

    cur.execute(
        """
        INSERT OR REPLACE INTO settings
        VALUES (?, ?)
        """,
        (key, value)
    )

    conn.commit()

# DISPLAY NAME

def get_display_name(
    tg_id,
    username,
    first_name,
    name,
    mode
):

    if mode == "reestr":
        return name

    if mode == "firstname":
        return first_name or username or name

    return username or first_name or name

def get_display_user(uid, mode):

    cur.execute("""
        SELECT tg_id, username, first_name, name
        FROM users
        WHERE username=? OR tg_id=?
    """, (uid, uid))

    row = cur.fetchone()

    if not row:
        return uid

    tg_id, username, first_name, name = row

    if mode == "firstname":
        return first_name or username or name or uid

    if mode == "reestr":
        return name or username or first_name or uid

    return username or first_name or name or uid


def show_user(uid):

    return get_display_user(
        uid,
        get_setting("display_mode")
    )

def show_user_html(uid):

    cur.execute("""
        SELECT tg_id, username, first_name, name
        FROM users
        WHERE username=? OR tg_id=?
    """, (uid, uid))

    row = cur.fetchone()

    if not row:
        return uid

    tg_id, username, first_name, name = row

    shown = show_user(uid)

    if tg_id:

        return (
            f'<a href="tg://user?id={tg_id}">'
            f'{shown}'
            f'</a>'
        )

    if username:
        return f"@{username}"

    return name or shown

def clean(u):
    return u.replace("@", "").strip()

def get_target(update, context):

    if update.message.reply_to_message:

        user = update.message.reply_to_message.from_user

        tg_id = str(user.id)

        cur.execute(
            """
            SELECT username
            FROM users
            WHERE tg_id=?
            """,
            (tg_id,)
        )

        row = cur.fetchone()

        if row and row[0]:
            return row[0]

        if user.username:
            return user.username

        return tg_id

    if context.args:
        return clean(context.args[0])

    return None

async def is_admin(update: Update):
    admins = await update.effective_chat.get_administrators()
    return any(a.user.id == update.effective_user.id for a in admins)

def add_v(uid, t, r, mod):
    cur.execute(
        "INSERT INTO violations(user_id,type,reason,created_at,moderator) VALUES (?,?,?,?,?)",
        (uid, t, r, datetime.now().isoformat(), mod)
    )
    conn.commit()

def get(uid, t):
    cur.execute(
        "SELECT id, reason FROM violations WHERE user_id=? AND type=? ORDER BY id ASC",
        (uid, t)
    )
    return cur.fetchall()

def get_full(uid, t):
    cur.execute(
        """
        SELECT id, reason, created_at
        FROM violations
        WHERE user_id=? AND type=?
        ORDER BY id ASC
        """,
        (uid, t)
    )
    return cur.fetchall()

def delete_by_id(i):
    cur.execute("DELETE FROM violations WHERE id=?", (i,))
    conn.commit()

def delete_all(uid, t):
    cur.execute("DELETE FROM violations WHERE user_id=? AND type=?", (uid, t))
    conn.commit()

def sort_users(users):

    def sort_key(user):

        tg_id, username, first_name, name = user

        if not name:
            return (9, "")

        pos = name.find("ｙ")

        if pos != -1 and pos + 1 < len(name):

            ch = name[pos + 1]

            if (
                ("a" <= ch.lower() <= "z")
                or
                ("а" <= ch.lower() <= "я")
            ):
                return (
                    0,
                    ch.lower(),
                    name.lower()
                )

            return (
                1,
                name.lower()
            )

        return (
            2,
            name.lower()
        )

    return sorted(
        users,
        key=sort_key
    )

# DISPLAY USER

def display_user(username, tg_id, name):

    if tg_id:

        return (
            f'<a href="tg://user?id={tg_id}">'
            f'{name}'
            f'</a>'
        )

    if username:

        return f"@{username}"

    return name

# REMINDER WORKER

async def reminder_worker(app):

    while True:

        try:

            now = datetime.now(KYIV_TZ)

            current_time = now.strftime("%H:%M")
            current_date = now.strftime("%Y-%m-%d")
            current_weekday = now.weekday()

            cur.execute("""
                SELECT
                    id,
                    chat_id,
                    period,
                    time,
                    text,
                    last_sent
                FROM reminders
            """)

            rows = cur.fetchall()

            for rid, chat_id, period, time_str, text, last_sent in rows:

                if time_str != current_time:
                    continue

                if last_sent == current_date:
                    continue

                send = False

                if period in REMINDER_DAYS:

                    if REMINDER_DAYS[period] == current_weekday:
                        send = True

                elif period == "день":
                    send = True

                elif period == "месяц":

                    if now.day == 1:
                        send = True

                if not send:
                    continue

                await app.bot.send_message(
                    chat_id=chat_id,
                    text=f"<b>⏰ НАПОМИНАНИЕ</b>\n\n{text}",
                    parse_mode="HTML"
                )

                cur.execute("""
                    UPDATE reminders
                    SET last_sent=?
                    WHERE id=?
                """, (
                    current_date,
                    rid
                ))

                conn.commit()

        except Exception as e:
            print("REMINDER ERROR:", e)

        await asyncio.sleep(30)

# ---------------- FORMAT ----------------

#ОТОБРАЖЕНИЕ ПРЕДОВ В РЕЕСТРЕ
def fmt_warn(warns):

    if not warns:
        return ""

    return " | ".join(
        [
            f"{i+1}. ⚠️ {r}"
            for i, (_, r) in enumerate(warns)
        ]
    )

#ОТОБРАЖЕНИЕ ПРОЕБОВ В РЕЕСТРЕ
def fmt_proeb(proebs):

    if not proebs:
        return ""

    return " | ".join(
        [
            f"{i+1}. ⛔ {r}"
            for i, (_, r) in enumerate(proebs)
        ]
    )

def fmt_warn_full(warns):
    if not warns:
        return ""

    text = ""

    for i, (_, reason, created_at) in enumerate(warns):
        date = datetime.fromisoformat(created_at)

        text += (
            f"{i+1}. ⚠️ {reason}\n"
            f"📅 {date.strftime('%d.%m.%Y')}\n\n"
        )

    return text


def fmt_proeb_full(proebs):
    if not proebs:
        return ""

    text = ""

    for i, (_, reason, created_at) in enumerate(proebs):
        date = datetime.fromisoformat(created_at)

        text += (
            f"{i+1}. ⛔ {reason}\n"
            f"📅 {date.strftime('%d.%m.%Y')}\n\n"
        )

    return text

# ЧЕККЕР УКАЗАН ИЛИ ИМЕЕТСЯ В БАЗЕ ПОЛЬЗОВАТЕЛЬ
async def check_target(update, uid):

    if not uid:
        await update.message.reply_text(
            "👤 Укажи пользователя или ответь на его сообщение."
        )
        return False

    if not user_exists(uid):
        await update.message.reply_text(
            "❌ Пользователь не найден в реестре."
        )
        return False

    return True

# REMINDER DAYS
DAYS = {
    "понедельник": 0,
    "вторник": 1,
    "среда": 2,
    "четверг": 3,
    "пятница": 4,
    "суббота": 5,
    "воскресенье": 6
}

# ---------------- TEXT COMMANDS ----------------

async def text_commands(update, context: ContextTypes.DEFAULT_TYPE):

    sync_user(update.effective_user)

    text = update.message.text.strip()
    lower = text.lower()

    # +НИК

    if lower.startswith("+ник"):

        parts = text.split(maxsplit=1)

        if len(parts) > 1:
            context.args = parts[1].split()
        else:
            context.args = []

        return await plus_nick(update, context)

    # +АЙДИ

    if lower.startswith("+айди"):

        parts = text.split(maxsplit=1)

        if len(parts) > 1:
            context.args = parts[1].split()
        else:
            context.args = []

        return await plus_id(update, context)

    # НИК

    if lower == "ник" or lower.startswith("ник "):

        parts = text.split(maxsplit=1)

        if len(parts) > 1:
            context.args = [parts[1]]
        else:
            context.args = []

        return await nick(update, context)

    # АЙДИ

    if lower == "айди" or lower.startswith("айди "):

        parts = text.split(maxsplit=1)

        if len(parts) > 1:
            context.args = [parts[1]]
        else:
            context.args = []

        return await game_id(update, context)

    # СОСТАВ

    if lower == "состав":
        return await sostav(update, context)



    # ПРИПИСКА
    if lower == "приписка":
        return await pripiska(update, context)

    # АД

    if lower == "ад" or lower.startswith("ад "):
        return await add(update, context)

    # АДМИ

    if lower == "адми" or lower.startswith("адми"):
        return await adme(update, context)

    # ДЕЛ
    if lower.startswith("дел "):
        parts = text.split(maxsplit=1)

        if len(parts) > 1:
            context.args = parts[1].split()
        else:
            context.args = []

        return await delete(update, context)

    # ПРЕД
    if lower == "пред" or lower.startswith("пред "):
        parts = text.split(maxsplit=1)

        if len(parts) > 1:
            context.args = parts[1].split()
        else:
            context.args = []

        return await pred(update, context)

    # ПРОЕБ
    if lower == "проеб" or lower.startswith("проеб "):
        parts = text.split(maxsplit=1)

        if len(parts) > 1:
            context.args = parts[1].split()
        else:
            context.args = []

        return await proeb(update, context)

    # СНЯТЬ ПРЕДЫ
    if lower == "снять преды" or lower.startswith("снять преды "):
        parts = text.split(maxsplit=2)

        if len(parts) > 2:
            context.args = parts[2].split()
        else:
            context.args = []

        return await unpreds(update, context)

    # СНЯТЬ ПРЕД
    if lower == "снять пред" or lower.startswith("снять пред "):
        parts = text.split(maxsplit=2)

        if len(parts) > 2:
            context.args = parts[2].split()
        else:
            context.args = []

        return await unpred(update, context)

    # СНЯТЬ ПРОЕБЫ
    if lower == "снять проебы" or lower.startswith("снять проебы "):
        parts = text.split(maxsplit=2)

        if len(parts) > 2:
            context.args = parts[2].split()
        else:
            context.args = []

        return await unproebs(update, context)

    # СНЯТЬ ПРОЕБ
    if lower == "снять проеб" or lower.startswith("снять проеб "):
        parts = text.split(maxsplit=2)

        if len(parts) > 2:
            context.args = parts[2].split()
        else:
            context.args = []

        return await unproeb(update, context)

    # СТРОНГ
    if lower == "стронг" or lower.startswith("стронг "):
        parts = text.split(maxsplit=1)

        if len(parts) > 1:
            context.args = parts[1].split()
        else:
            context.args = []

        return await strong(update, context)

    # МУР
    if lower == "мур":
        context.args = []
        return await myr(update, context)

    # РЕЕ
    if lower == "рее" or lower.startswith("рее "):
        parts = text.split(maxsplit=1)

        if len(parts) > 1:
            context.args = [parts[1]]
        else:
            context.args = []

        return await ree(update, context)

    # НИК
    if lower == "ник" or lower.startswith("ник "):

    # АЙДИ
    if lower == "айди" or lower.startswith("айди "):

    #СОСТАВ
    if lower == "состав":

    # РЕЛИСТ
    if lower == "релист":
        return await relist(update, context)

    # РЕЕСТР
    if lower == "реестр":
        return await reestr(update, context)

    # НАПОМИНАЛКА
    if lower == "напоминалка" or lower.startswith("напоминалка "):

        first_line = text.splitlines()[0]

        parts = first_line.split()

        if len(parts) >= 3:
            context.args = [parts[1], parts[2]]
        else:
            context.args = []

        return await reminder(update, context)

    # НАПОМИНАЛКИ
    if lower == "напоминалки":
        return await reminders(update, context)

    # УДАЛИТЬ НАП
    if lower.startswith("удалить нап "):

        parts = text.split(maxsplit=2)

        if len(parts) > 2:
            context.args = [parts[2]]
        else:
            context.args = []

        return await del_reminder(update, context)

    # ИЗМЕНИТЬ НАП
    if lower == "изменить нап" or lower.startswith("изменить нап "):
        return await edit_reminder(update, context)

    # ПЕРИОД НАП
    if lower.startswith("период нап "):
        return await period_reminder(update, context)

    # ВРЕМЯ НАП
    if lower.startswith("время нап "):
        return await time_reminder(update, context)

    # СЕТ
    if lower == "сет" or lower.startswith("сет "):
        parts = text.split(maxsplit=1)

        if len(parts) > 1:
            context.args = parts[1].split()
        else:
            context.args = []

        return await set_cmd(update, context)

    # СЕТТ
    if lower == "сетт":
        context.args = []
        return await setting(update, context)

    # КОМ
    if lower == "ком":
        return await comm(update, context)

# ---------------- COMMANDS ----------------

# ---------------- PLUS NICK ----------------

async def plus_nick(update, context):

    if not context.args:
        await update.message.reply_text(
            "❌ Укажи ник."
        )
        return

    nick = " ".join(context.args)

    if await is_admin(update):

        uid = get_target(update, context)

        if uid:

            cur.execute(
                """
                UPDATE users
                SET nick=?
                WHERE username=?
                """,
                (nick, uid)
            )

            conn.commit()

            await update.message.reply_text(
                "✅ Ник изменён"
            )

            return

    username = update.effective_user.username

    cur.execute(
        """
        UPDATE users
        SET nick=?
        WHERE username=?
        """,
        (nick, username)
    )

    conn.commit()

    await update.message.reply_text(
        "✅ Ник сохранён"
    )

# ---------------- PLUS ID ----------------

async def plus_id(update, context):

    if not context.args:
        await update.message.reply_text(
            "❌ Укажи айди."
        )
        return

    gid = context.args[-1]

    if await is_admin(update):

        uid = get_target(update, context)

        if uid:

            cur.execute(
                """
                UPDATE users
                SET game_id=?
                WHERE username=?
                """,
                (gid, uid)
            )

            conn.commit()

            await update.message.reply_text(
                "✅ Айди изменён"
            )

            return

    username = update.effective_user.username

    cur.execute(
        """
        UPDATE users
        SET game_id=?
        WHERE username=?
        """,
        (gid, username)
    )

    conn.commit()

    await update.message.reply_text(
        "✅ Айди сохранён"
    )

# ---------------- PRIPISKA ----------------

async def pripiska(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("『乃ｙ")

# ---------------- ADME ----------------

async def adme(update: Update, context: ContextTypes.DEFAULT_TYPE):

    parts = update.message.text.splitlines()

    if len(parts) < 3:
        await update.message.reply_text(
            "❌ Формат:\n\n"
            "Адми\n"
            "Ник\n"
            "Айди"
        )
        return

    nick = parts[1].strip()
    game_id = parts[2].strip()

    user = update.effective_user

    cur.execute(
        """
        INSERT OR REPLACE INTO users
        (
            tg_id,
            username,
            first_name,
            name,
            nick,
            game_id
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            str(user.id),
            user.username or "",
            user.first_name or "",
            nick,
            nick,
            game_id
        )
    )

    conn.commit()

    await update.message.reply_text(
        f"✅ Добавлен\n\n"
        f"🎮 {nick}\n"
        f"🆔 {game_id}"
    )

# ---------------- ADD ----------------

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await is_admin(update):
        return

    target = None

    if update.message.reply_to_message:

        target = update.message.reply_to_message.from_user

        parts = update.message.text.splitlines()

    else:

        parts = update.message.text.splitlines()

        if len(parts) < 4:
            await update.message.reply_text(
                "❌ Формат:\n\n"
                "Ад @user\n"
                "Ник\n"
                "Айди"
            )
            return

        username = parts[0].split(maxsplit=1)[1].replace("@", "")

        target = None

        try:
            target_user = await context.bot.get_chat(
                f"@{username}"
            )
            target = target_user
        except:
            pass

    if not target:
        await update.message.reply_text(
            "❌ Пользователь не найден."
        )
        return

    if update.message.reply_to_message:

        if len(parts) < 3:
            await update.message.reply_text(
                "❌ Формат:\n\n"
                "Ад\n"
                "Ник\n"
                "Айди"
            )
            return

        nick = parts[1].strip()
        game_id = parts[2].strip()

    else:

        nick = parts[1].strip()
        game_id = parts[2].strip()

    tg_id = str(target.id)
    username = target.username or ""
    first_name = target.first_name or ""

    cur.execute(
        """
        INSERT OR REPLACE INTO users
        (
            tg_id,
            username,
            first_name,
            name,
            nick,
            game_id
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            tg_id,
            username,
            first_name,
            nick,
            nick,
            game_id
        )
    )

    conn.commit()

    await update.message.reply_text(
        f"✅ Пользователь добавлен\n\n"
        f"🎮 {nick}\n"
        f"🆔 {game_id}"
    )

# ---------------- DEL ----------------

async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    if not context.args:
        return

    uid = clean(context.args[0])
    if not user_exists(uid):
        await update.message.reply_text(
            "❌ Пользователь не найден в реестре"
        )
        return

    cur.execute(
        "DELETE FROM users WHERE username=?",
        (uid,)
    )

    cur.execute(
        "DELETE FROM violations WHERE user_id=?",
        (uid,)
    )

    conn.commit()

    await update.message.reply_text(
        "<b>❌ Пользователь удалён</b>",
        parse_mode="HTML"
    )


# ---------------- PRED ----------------

async def pred(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = get_target(update, context)

    if not await check_target(update, uid):
        return

    if update.message.reply_to_message:
        reason = " ".join(context.args)
    else:
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else ""

    mod = (
        f"@{update.effective_user.username}"
        if update.effective_user.username
        else str(update.effective_user.id)
    )

    add_v(uid, "warn", reason, mod)

    text = f"""❗{show_user_html(uid)} получает ⚠️ Предупреждение
⏳Будет снято когда исправишься
👺Модератор: {mod}"""

    if reason:
        text += f"\n💬Причина: {reason}"

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )

# ---------------- PROEB ----------------

async def proeb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = get_target(update, context)

    if not await check_target(update, uid):
        return

    if update.message.reply_to_message:
        reason = " ".join(context.args)
    else:
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else ""

    mod = f"@{update.effective_user.username}" if update.effective_user.username else str(update.effective_user.id)

    add_v(uid, "proeb", reason, mod)

    count = len(get(uid, "proeb"))

    text = f"""❗{show_user_html(uid)} получает ⛔ Проеб ({count}/3)
⏳Будет снято через 30 дней
👺Модератор: {mod}"""

    if reason:
        text += f"\n💬Причина: {reason}"

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )

    if count >= 3:
        await update.message.reply_text(f"🚨 {show_user(uid)} достиг максимального числа ⛔Проебов (3/3) !")


# ---------------- UNPRED ----------------

async def unpred(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = get_target(update, context)

    if not await check_target(update, uid):
        return

    warns = get(uid, "warn")

    if not warns:
        await update.message.reply_text(
            "⚠️ У пользователя нет предупреждений"
        )
        return

    arg_pos = 0 if update.message.reply_to_message else 1

    if len(context.args) <= arg_pos:
        vid = warns[-1][0]
    else:
        try:
            idx = int(context.args[arg_pos]) - 1

            if idx < 0 or idx >= len(warns):
                await update.message.reply_text(
                    "❌ Неверный номер предупреждения"
                )
                return

            vid = warns[idx][0]

        except ValueError:
            await update.message.reply_text(
                "❌ Номер должен быть числом"
            )
            return

    delete_by_id(vid)

    await update.message.reply_text(
        f"✅ С пользователя {show_user_html(uid)} снято предупреждение",
        parse_mode="HTML"
    )

# ---------------- UNPRPROEB ----------------

async def unproeb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = get_target(update, context)

    if not await check_target(update, uid):
        return

    proebs = get(uid, "proeb")

    if not proebs:
        await update.message.reply_text(
            "⛔ У пользователя нет проебов"
        )
        return

    arg_pos = 0 if update.message.reply_to_message else 1

    if len(context.args) <= arg_pos:
        vid = proebs[-1][0]
    else:
        try:
            idx = int(context.args[arg_pos]) - 1

            if idx < 0 or idx >= len(proebs):
                await update.message.reply_text(
                    "❌ Неверный номер проеба"
                )
                return

            vid = proebs[idx][0]

        except ValueError:
            await update.message.reply_text(
                "❌ Номер должен быть числом"
            )
            return

    delete_by_id(vid)

    await update.message.reply_text(
        f"✅ С пользователя {show_user_html(uid)} снят проеб",
        parse_mode="HTML"
    )

# ---------------- ALL REMOVE ----------------

async def unpreds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = clean(context.args[0])
    cnt = len(get(uid, "warn"))

    delete_all(uid, "warn")

    await update.message.reply_text(
        f"С пользователя {show_user_html(uid)} были сняты все ⚠️предупреждения ({cnt}/{cnt})",
        parse_mode="HTML"
    )


async def unproebs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("☝️Ты не админ !")
        return

    uid = clean(context.args[0])
    cnt = len(get(uid, "proeb"))

    delete_all(uid, "proeb")

    await update.message.reply_text(
        f"С пользователя {show_user_html(uid)} были сняты все ⛔проебы ({cnt}/{cnt})",
        parse_mode="HTML"
    )

# ---------------- STRONG ----------------

async def strong(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = get_target(update, context)

    if not await check_target(update, uid):
        return

    warns = get(uid, "warn")

    if not warns:
        await update.message.reply_text(
            "⚠️ У пользователя нет предупреждений"
        )
        return

    arg_pos = 0 if update.message.reply_to_message else 1

    if len(context.args) <= arg_pos:
        idx = len(warns) - 1
    else:
        try:
            idx = int(context.args[arg_pos]) - 1

            if idx < 0 or idx >= len(warns):
                await update.message.reply_text(
                    "❌ Неверный номер предупреждения"
                )
                return

        except ValueError:
            await update.message.reply_text(
                "❌ Номер должен быть числом"
            )
            return

    vid, reason = warns[idx]

    delete_by_id(vid)

    mod = (
        f"@{update.effective_user.username}"
        if update.effective_user.username
        else str(update.effective_user.id)
    )

    add_v(uid, "proeb", reason, mod)

    await update.message.reply_text(
        f"⚠️ Предупреждение пользователя {show_user_html(uid)} "
        f"преобразовано в ⛔ Проеб\n"
        f"Не игнорируй предупреждения!",
        parse_mode="HTML"
    )

# ---------------- MYR ----------------

async def myr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = clean(context.args[0]) if context.args else str(update.effective_user.username)

    if not user_exists(uid):
        await update.message.reply_text("Тебя нету в базе. \nИди нахуй !")
        await asyncio.sleep(2)
        await msg.edit_text("Тебя нету в базе. \nДобавь себя: Адми Ник")
        return

    warns = get_full(uid, "warn")
    proebs = get_full(uid, "proeb")

    if not warns and not proebs:
        await update.message.reply_text("Замечания отсутствуют 🤗")
        return

    text = f"<b>❕ РЕЕСТР ПОЛЬЗОВАТЕЛЯ</b>\n\n👤 {show_user_html(uid)}\n\n"

    if proebs:
        text += fmt_proeb_full(proebs)

    if warns:
        text += fmt_warn_full(warns)

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )

# ---------------- REE ----------------

async def ree(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = get_target(update, context)

    if not await check_target(update, uid):
        return

    warns = get_full(uid, "warn")
    proebs = get_full(uid, "proeb")

    if not warns and not proebs:
        await update.message.reply_text("Замечания отсутствуют 🤗")
        return

    text = f"<b>❕ РЕЕСТР ПОЛЬЗОВАТЕЛЯ</b>\n\n👤 {show_user_html(uid)}\n\n"

    if proebs:
        text += fmt_proeb_full(proebs)

    if warns:
        text += fmt_warn_full(warns)

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )


# ---------------- RELIST ----------------

async def relist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    cur.execute("""
        SELECT tg_id, username, first_name, name
        FROM users
    """)

    users = sort_users(cur.fetchall())

    text = "<b>📋 СПИСОК УЧАСТНИКОВ 📋</b>\n\n"

    mode = get_setting("relist_mode")

    for tg_id, username, first_name, name in users:

        shown = get_display_name(
            tg_id,
            username,
            first_name,
            name,
            mode
        )

        if tg_id:

            display = (
                f'<a href="tg://user?id={tg_id}">'
                f'{shown}'
                f'</a>'
            )

        elif username:

            display = f"@{username}"

        else:

            display = shown

        text += f"{name} | {display}\n"

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )

# ---------------- NICK ----------------

async def nick(update, context):

    uid = get_target(update, context)

    if not uid:
        uid = update.effective_user.username

    cur.execute(
        """
        SELECT nick
        FROM users
        WHERE username=?
        """,
        (uid,)
    )

    row = cur.fetchone()

    await update.message.reply_text(
        row[0] if row and row[0] else "Не указан"
    )

# ---------------- ID ----------------

async def game_id(update, context):

    uid = get_target(update, context)

    if not uid:
        uid = update.effective_user.username

    cur.execute(
        """
        SELECT game_id
        FROM users
        WHERE username=?
        """,
        (uid,)
    )

    row = cur.fetchone()

    await update.message.reply_text(
        row[0] if row and row[0] else "Не указан"
    )

# ---------------- SOSTAV ----------------

async def sostav(update, context):

    cur.execute(
        """
        SELECT
            username,
            first_name,
            name,
            nick,
            game_id
        FROM users
        ORDER BY name COLLATE NOCASE
        """
    )

    rows = cur.fetchall()

    if not rows:
        await update.message.reply_text(
            "Состав пуст."
        )
        return

    mode = get_setting("os") or "reestr"

    text = "<b>📋 СОСТАВ</b>\n\n"

    for username, first_name, name, nick, gid in rows:

        if mode == "username":
            left = (
                f"@{username}"
                if username
                else name
            )

        elif mode == "firstname":
            left = first_name

        else:
            left = name

        text += (
            f"{left} | "
            f"{nick or '—'} | "
            f"{gid or '—'}\n"
        )

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )

# ---------------- REESTR ----------------

async def reestr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    cur.execute("""
        SELECT tg_id, username, first_name, name
        FROM users
    """)

    users = sort_users(cur.fetchall())

    text = "<b>📛 РЕЕСТР НАРУШЕНИЙ 📛</b>\n\n"

    mode = get_setting("relist_mode")

    for tg_id, username, first_name, name in users:

        uid = username if username else tg_id

        warns = get(uid, "warn")
        proebs = get(uid, "proeb")

        if not warns and not proebs:
            continue

        shown = get_display_name(
            tg_id,
            username,
            first_name,
            name,
            mode
        )

        if tg_id:

            display = (
                f'<a href="tg://user?id={tg_id}">'
                f'{shown}'
                f'</a>'
            )

        elif username:

            display = f"@{username}"

        else:

            display = shown

        text += f"{name} | {display}\n"

        if proebs:
            text += fmt_proeb(proebs) + "\n"

        if warns:
            text += fmt_warn(warns) + "\n"

        text += "\n"

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )

# ---------------- REMINDER ----------------

async def reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await is_admin(update):
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Использование:\n\n"
            "Напоминалка пятница 12:00\n"
            "Текст напоминания"
        )
        return

    period = context.args[0].lower()
    time_str = context.args[1]

    hh, mm = time_str.split(":")
    time_str = f"{int(hh):02d}:{int(mm):02d}"

    if period not in [
        "день",
        "месяц",
        "понедельник",
        "вторник",
        "среда",
        "четверг",
        "пятница",
        "суббота",
        "воскресенье"
    ]:
        await update.message.reply_text(
            "❌ Неверный период."
        )
        return

    parts = update.message.text.split("\n", 1)

    if len(parts) < 2:
        await update.message.reply_text(
            "❌ Укажи текст напоминания."
        )
        return

    reminder_text = parts[1].strip()

    cur.execute(
        """
        INSERT INTO reminders
        (
            chat_id,
            period,
            time,
            text,
            next_run,
            created_by
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            update.effective_chat.id,
            period,
            time_str,
            reminder_text,
            0,
            str(update.effective_user.id)
        )
    )

    conn.commit()

    rid = cur.lastrowid

    await update.message.reply_text(
        f"✅ Напоминалка создана\n\n"
        f"🆔 {rid}\n"
        f"📅 {period}\n"
        f"⏰ {time_str}\n\n"
        f"💬 {reminder_text}"
    )

# ---------------- REMINDERS ----------------

async def reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await is_admin(update):
        return

    cur.execute("""
        SELECT id, period, time, text
        FROM reminders
        WHERE chat_id=?
        ORDER BY id
    """, (update.effective_chat.id,))

    rows = cur.fetchall()

    if not rows:
        await update.message.reply_text(
            "📭 Напоминалок нет."
        )
        return

    text = "<b>⏰ НАПОМИНАЛКИ</b>\n\n"

    for rid, period, time_str, reminder_text in rows:

        short_text = reminder_text

        if len(short_text) > 50:
            short_text = short_text[:50] + "..."

        text += (
            f"🆔 {rid}\n"
            f"📅 {period}\n"
            f"⏰ {time_str}\n\n"
            f"💬 {short_text}\n\n"
        )

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )

# ---------------- DELETE REMINDER ----------------

async def del_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await is_admin(update):
        return

    if not context.args:
        await update.message.reply_text(
            "❌ Укажи ID напоминалки."
        )
        return

    try:
        rid = int(context.args[0])
    except:
        await update.message.reply_text(
            "❌ Неверный ID."
        )
        return

    cur.execute(
        """
        SELECT id
        FROM reminders
        WHERE id=? AND chat_id=?
        """,
        (
            rid,
            update.effective_chat.id
        )
    )

    row = cur.fetchone()

    if not row:
        await update.message.reply_text(
            "❌ Напоминалка не найдена."
        )
        return

    cur.execute(
        """
        DELETE FROM reminders
        WHERE id=?
        """,
        (rid,)
    )

    conn.commit()

    await update.message.reply_text(
        f"🗑 Напоминалка #{rid} удалена."
    )

# ---------------- EDIT REMINDER ----------------

async def edit_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await is_admin(update):
        return

    first_line = update.message.text.splitlines()[0]

    parts = first_line.split()

    if len(parts) < 3:
        await update.message.reply_text(
            "❌ Укажи ID напоминалки."
        )
        return

    try:
        rid = int(parts[2])
    except:
        await update.message.reply_text(
            "❌ Неверный ID."
        )
        return

    lines = update.message.text.split("\n", 1)

    if len(lines) < 2:
        await update.message.reply_text(
            "❌ Укажи новый текст."
        )
        return

    new_text = lines[1].strip()

    cur.execute(
        """
        SELECT id
        FROM reminders
        WHERE id=? AND chat_id=?
        """,
        (
            rid,
            update.effective_chat.id
        )
    )

    if not cur.fetchone():
        await update.message.reply_text(
            "❌ Напоминалка не найдена."
        )
        return

    cur.execute(
        """
        UPDATE reminders
        SET text=?
        WHERE id=?
        """,
        (
            new_text,
            rid
        )
    )

    conn.commit()

    await update.message.reply_text(
        f"✏️ Напоминалка #{rid} изменена."
    )

# ---------------- PERIOD REMINDER ----------------

async def period_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await is_admin(update):
        return

    parts = update.message.text.split()

    if len(parts) < 4:
        await update.message.reply_text(
            "❌ Использование:\nПериод нап ID период"
        )
        return

    try:
        rid = int(parts[2])
    except:
        await update.message.reply_text(
            "❌ Неверный ID."
        )
        return

    new_period = parts[3].lower()

    valid_periods = [
        "день",
        "месяц",
        "понедельник",
        "вторник",
        "среда",
        "четверг",
        "пятница",
        "суббота",
        "воскресенье"
    ]

    if new_period not in valid_periods:
        await update.message.reply_text(
            "❌ Неверный период."
        )
        return

    cur.execute(
        """
        SELECT id
        FROM reminders
        WHERE id=? AND chat_id=?
        """,
        (
            rid,
            update.effective_chat.id
        )
    )

    if not cur.fetchone():
        await update.message.reply_text(
            "❌ Напоминалка не найдена."
        )
        return

    cur.execute(
        """
        UPDATE reminders
        SET period=?
        WHERE id=?
        """,
        (
            new_period,
            rid
        )
    )

    conn.commit()

    await update.message.reply_text(
        f"📅 Период напоминалки #{rid} изменён на: {new_period}"
    )

# ---------------- TIME REMINDER ----------------

async def time_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await is_admin(update):
        return

    parts = update.message.text.split()

    if len(parts) < 4:
        await update.message.reply_text(
            "❌ Использование:\nВремя нап ID ЧЧ:ММ"
        )
        return

    try:
        rid = int(parts[2])
    except:
        await update.message.reply_text(
            "❌ Неверный ID."
        )
        return

    new_time = parts[3]

    try:
        hh, mm = new_time.split(":")
        hh = int(hh)
        mm = int(mm)

        if hh < 0 or hh > 23 or mm < 0 or mm > 59:
            raise ValueError

    except:
        await update.message.reply_text(
            "❌ Время должно быть в формате ЧЧ:ММ"
        )
        return

    cur.execute(
        """
        SELECT id
        FROM reminders
        WHERE id=? AND chat_id=?
        """,
        (
            rid,
            update.effective_chat.id
        )
    )

    if not cur.fetchone():
        await update.message.reply_text(
            "❌ Напоминалка не найдена."
        )
        return

    new_time = f"{hh:02d}:{mm:02d}"

    cur.execute(
        """
        UPDATE reminders
        SET time=?
        WHERE id=?
        """,
        (
            new_time,
            rid
        )
    )

    conn.commit()

    await update.message.reply_text(
        f"⏰ Время напоминалки #{rid} изменено на: {new_time}"
    )

# ---------------- SET ----------------

async def set_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await is_admin(update):
        return

    if len(context.args) != 2:
        return

    section = context.args[0].lower()
    value = context.args[1]

    modes = {
        "1": "username",
        "2": "firstname",
        "3": "reestr"
    }

    if value not in modes:
        return

    if section == "ос":
        set_setting(
            "os",
            modes[value]
        )

    elif section == "ок":
        set_setting(
            "ok",
            modes[value]
        )

    else:
        return

    await update.message.reply_text(
        "✅ Настройки изменены"
    )

# ---------------- SETTING ----------------

async def setting(update: Update, context: ContextTypes.DEFAULT_TYPE):

    os_mode = get_setting("os")
    ok_mode = get_setting("ok")

    os1 = "➤ " if os_mode == "username" else ""
    os2 = "➤ " if os_mode == "firstname" else ""
    os3 = "➤ " if os_mode == "reestr" else ""

    ok1 = "➤ " if ok_mode == "username" else ""
    ok2 = "➤ " if ok_mode == "firstname" else ""
    ok3 = "➤ " if ok_mode == "reestr" else ""

    text = f"""<b>⚙️ НАСТРОЙКИ ⚙️</b>
--------------------------------

<b>📋 Отображение в списках</b>
<i>Релист • Реестр</i>

{os1}<code>1️⃣ Username</code>
『乃ｙStarfly | @Bystarfly

{os2}<code>2️⃣ Имя Telegram</code>
『乃ｙStarfly | Ваня

{os3}<code>3️⃣ Ник реестра</code>
『乃ｙStarfly | 『乃ｙStarfly

✍️ Изменить:
Сет ос [Номер]

--------------------------------

<b>🔗 Отображение в командах</b>
<i>Пред • Проеб • Мур • Рее</i>

{ok1}<code>1️⃣ Username</code>
❗@Bystarfly получает пред

{ok2}<code>2️⃣ Имя Telegram</code>
❗Ваня получает пред

{ok3}<code>3️⃣ Ник реестра</code>
❗『乃ｙStarfly получает пред

✍️ Изменить:
Сет ок [Номер]
"""

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )

# ---------------- COMM ----------------

async def comm(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if await is_admin(update):

        text = """
<b>📚 СПИСОК КОМАНД 📚</b>

<i>💬 Большинство команд поддерживают ответ на сообщение (реплай).</i>

<i>↩️ При использовании реплая указывать @user не нужно.</i>

<i>🔢 Если у команды есть номер — используется выбранное предупреждение или проеб.</i>

<i>🆓 Если номер не указан — используется последнее замечание.</i>

--------------------------------

<b>👤 Пользователи</b>

<code>Адми Ник</code>
Добавить себя

<code>Реми @user</code>
Удалить Telegram привязку

<code>Мур</code>
Показать свой реестр

--------------------------------

<b>👥 Управление пользователями</b>

<code>Ад @user Ник</code>
Добавить пользователя

<code>Рен @user Новый ник</code>
Изменить ник реестра

<code>Дел @user</code>
Удалить пользователя

--------------------------------

<b>⚠️ Нарушения</b>

<code>Пред @user [Причина]</code>
Выдать предупреждение

<code>Проеб @user [Причина]</code>
Выдать проеб

<code>Стронг @user [Номер]</code>
Преобразовать предупреждение в проеб

<code>Снять пред @user [Номер]</code>
Снять предупреждение

<code>Снять проеб @user [Номер]</code>
Снять проеб

<code>Снять преды @user</code>
Снять все предупреждения

<code>Снять проебы @user</code>
Снять все проебы

--------------------------------

<b>📋 Реестры</b>

<code>Рее @user</code>
Открыть реестр пользователя

<code>Релист</code>
Список добавленных пользователей

<code>Реестр</code>
Общий реестр нарушений

--------------------------------

<b>⚙️ Настройки</b>

<code>Сетт</code>
Открыть настройки

<code>Сет ос [1-3]</code>
Отображение в списках

<code>Сет ок [1-3]</code>
Отображение в командах

--------------------------------

<b>📖 Прочее</b>

<code>Приписка</code>
Показать приписку

<code>Комм</code>
Показать список команд
"""
    else:

        text = """
<b>📚 СПИСОК КОМАНД 📚</b>

<b>👤 Пользователи</b>

<code>Адми Ник</code>
Добавить себя

<code>Реми Новый ник</code>
Изменить свой ник реестра

<code>Мур</code>
Показать свой реестр

<code>Рее @user</code>
 Открыть реестр пользователя


<code>Приписка</code>
Показать приписку

--------------------------------

<b>📖 Справка</b>

<code>Комм</code>
Показать список команд
"""

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )

# ---------------- APP ----------------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("pripiska", pripiska))
app.add_handler(CommandHandler("add", add))
app.add_handler(CommandHandler("del", delete))
app.add_handler(CommandHandler("pred", pred))
app.add_handler(CommandHandler("proeb", proeb))
app.add_handler(CommandHandler("unpred", unpred))
app.add_handler(CommandHandler("unproeb", unproeb))
app.add_handler(CommandHandler("unpreds", unpreds))
app.add_handler(CommandHandler("unproebs", unproebs))
app.add_handler(CommandHandler("strong", strong))
app.add_handler(CommandHandler("myr", myr))
app.add_handler(CommandHandler("ree", ree))
app.add_handler(CommandHandler("relist", relist))
app.add_handler(CommandHandler("reestr", reestr))
app.add_handler(CommandHandler("set", set_cmd))
app.add_handler(CommandHandler("setting", setting))
app.add_handler(CommandHandler("comm", comm))

app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        text_commands
    )
)

async def on_startup(app):
    app.create_task(
        reminder_worker(app)
    )

app.post_init = on_startup

app.run_polling()
