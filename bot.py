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

TOKEN = os.getenv("TOKEN")

conn = sqlite3.connect("bot.db", check_same_thread=False)
cur = conn.cursor()

# ---------------- DB ----------------

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    tg_id TEXT,
    username TEXT UNIQUE,
    first_name TEXT,
    name TEXT
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

# ДЕФОЛТНЫЕ НАСТРОЙКИ

cur.execute(
    "INSERT OR IGNORE INTO settings VALUES (?, ?)",
    ("relist_mode", "username")
)

cur.execute(
    "INSERT OR IGNORE INTO settings VALUES (?, ?)",
    ("display_mode", "username")
)

conn.commit()

# ---------------- SYNC USER ----------------

def sync_user(user):

    tg_id = str(user.id)
    username = user.username or ""
    first_name = user.first_name or ""

    print(
        f"SYNC | tg_id={tg_id} | "
        f"username='{username}' | "
        f"first_name='{first_name}'"
    )

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

        print("SYNC -> FOUND BY TG_ID")

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

            print("SYNC -> FOUND BY USERNAME")

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

        print("SYNC -> NO USERNAME")

        cur.execute(
            """
            SELECT username
            FROM users
            WHERE tg_id IS NULL
            """
        )

        rows = cur.fetchall()

        print("DB USERS:")

        for row in rows:
            print(f"'{row[0]}'")

        matches = []

        for row in rows:

            stored_username = row[0]

            if not stored_username:
                continue

            if stored_username.lower() == first_name.lower():

                matches.append(stored_username)

        print(f"SYNC -> MATCHES: {matches}")

        if len(matches) == 1:

            print("SYNC -> FOUND BY FIRST_NAME")

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

    print("SYNC -> NO MATCH")

# ---------------- SETTINGS ----------------

def get_setting(key):

    cur.execute(
        "SELECT value FROM settings WHERE key=?",
        (key,)
    )

    row = cur.fetchone()

    if row:
        return row[0]

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

# ---------------- DISPLAY NAME ----------------

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

# ---------------- HELPERS ----------------

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

# ---------------- FORMAT ----------------

def fmt_warn(warns):
    if not warns:
        return ""
    return "\n".join([f"{i+1}. ⚠️ {r}" for i, (_, r) in enumerate(warns)])

def fmt_proeb(proebs):
    if not proebs:
        return ""
    return "\n".join([f"{i+1}. ⛔ {r}" for i, (_, r) in enumerate(proebs)])

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

# ---------------- TEXT COMMANDS ----------------

async def text_commands(update, context: ContextTypes.DEFAULT_TYPE):

    sync_user(update.effective_user)

    text = update.message.text.strip()
    lower = text.lower()

    # ПРИПИСКА

    if lower == "приписка":
        return await pripiska(update, context)

    # АД

    if lower.startswith("ад "):
        parts = text.split(maxsplit=1)

        if len(parts) > 1:
            context.args = parts[1].split()
        else:
            context.args = []

        return await add(update, context)

    # АДМИ

    if lower == "адми" or lower.startswith("адми "):
        parts = text.split(maxsplit=1)

        if len(parts) > 1:
            context.args = [parts[1]]
        else:
            context.args = []

        return await adme(update, context)

    # РЕНЕЙМ

    if lower == "ренейм" or lower.startswith("ренейм "):
        parts = text.split(maxsplit=1)

        if len(parts) > 1:
            context.args = parts[1].split()
        else:
            context.args = []

        return await rename(update, context)

    # РЕМИ

    if lower == "реми" or lower.startswith("реми "):
        parts = text.split(maxsplit=1)

        if len(parts) > 1:
            context.args = [parts[1]]
        else:
            context.args = []

        return await reme(update, context)

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

    # РЕЛИСТ

    if lower == "релист":
        return await relist(update, context)

    # РЕЕСТР

    if lower == "реестр":
        return await reestr(update, context)

    # КОМ

    if lower == "ком":
        return await comm(update, context)

# ---------------- COMMANDS ----------------

# ---------------- TEST SETTINGS ----------------

async def testset(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        f"relist_mode = {get_setting('relist_mode')}\n"
        f"display_mode = {get_setting('display_mode')}"
    )

# ---------------- PRIPISKA ----------------

async def pripiska(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("『乃ｙ")

# ---------------- ADD ----------------

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    # через реплай
    if update.message.reply_to_message:

        if not context.args:
            await update.message.reply_text(
                "Укажи ник."
            )
            return

        user = update.message.reply_to_message.from_user

        tg_id = str(user.id)
        username = user.username or ""
        first_name = user.first_name or ""

        name = " ".join(context.args)

        cur.execute(
            """
            INSERT OR REPLACE INTO users
            (
                tg_id,
                username,
                first_name,
                name
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                tg_id,
                username,
                first_name,
                name
            )
        )

        conn.commit()

        await update.message.reply_text(
            "<b>👤 Пользователь добавлен</b>",
            parse_mode="HTML"
        )

        return

    # через @username

    if len(context.args) < 2:
        await update.message.reply_text(
            "Использование:\nАд @user Ник"
        )
        return

    username = clean(context.args[0])

    name = " ".join(context.args[1:])

    cur.execute(
        """
        INSERT OR REPLACE INTO users
        (
            tg_id,
            username,
            first_name,
            name
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            None,
            username,
            None,
            name
        )
    )

    conn.commit()

    await update.message.reply_text(
        "<b>👤 Пользователь добавлен</b>",
        parse_mode="HTML"
    )

# ---------------- ADME ----------------

async def adme(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not context.args:
        await update.message.reply_text(
            "Укажи ник.\nПример: Адми Иван"
        )
        return

    user = update.effective_user

    tg_id = str(user.id)
    username = user.username or ""
    first_name = user.first_name or ""

    name = " ".join(context.args)

    cur.execute(
        """
        INSERT OR REPLACE INTO users
        (
            tg_id,
            username,
            first_name,
            name
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            tg_id,
            username,
            first_name,
            name
        )
    )

    conn.commit()

    await update.message.reply_text(
        "<b>👤 Пользователь добавлен</b>",
        parse_mode="HTML"
    )
# ---------------- RENAME ----------------

async def rename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("☝️Ты не админ !")
        return

    if len(context.args) < 2:
        return

    uid = clean(context.args[0])
    new_name = " ".join(context.args[1:])

    cur.execute(
        "UPDATE users SET name=? WHERE username=?",
        (new_name, uid)
    )

    conn.commit()

    await update.message.reply_text(
        "<b>✏️ Пользователь переименован</b>",
        parse_mode="HTML"
    )

# ---------------- REME ----------------

async def reme(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.username

    if not uid:
        await update.message.reply_text(
            "У тебя отсутствует username Telegram."
        )
        return

    cur.execute(
        "SELECT 1 FROM users WHERE username=?",
        (uid,)
    )

    if not cur.fetchone():
        await update.message.reply_text(
            "Сначала добавь себя через команду Адми."
        )
        return

    if not context.args:
        await update.message.reply_text(
            "Укажи новый ник.\nПример: реми Вася"
        )
        return

    new_name = " ".join(context.args)

    cur.execute(
        "UPDATE users SET name=? WHERE username=?",
        (new_name, uid)
    )

    conn.commit()

    await update.message.reply_text(
        "<b>✏️ Ник изменён</b>",
        parse_mode="HTML"
    )

# ---------------- DEL ----------------

async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    if not context.args:
        return

    uid = clean(context.args[0])

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

    if not uid:
        await update.message.reply_text(
            "Укажи пользователя или ответь на сообщение."
        )
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

    await update.message.reply_text(
        f"DEBUG\n"
        f"uid = {uid}\n"
        f"type = warn"
    )

    text = f"""❗@{uid} получает ⚠️ Предупреждение
⏳Будет снято когда исправишься
👺Модератор: {mod}"""

    if reason:
        text += f"\n💬Причина: {reason}"

    await update.message.reply_text(text)


# ---------------- PROEB ----------------

async def proeb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = get_target(update, context)

    if not uid:
        await update.message.reply_text(
            "Укажи пользователя или ответь на сообщение."
        )
        return

    if update.message.reply_to_message:
        reason = " ".join(context.args)
    else:
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else ""

    mod = f"@{update.effective_user.username}" if update.effective_user.username else str(update.effective_user.id)

    add_v(uid, "proeb", reason, mod)

    count = len(get(uid, "proeb"))

    text = f"""❗{uid} получает ⛔ Проеб ({count}/3)
⏳Будет снято через 30 дней
👺Модератор: {mod}"""

    if reason:
        text += f"\n💬Причина: {reason}"

    await update.message.reply_text(text)

    if count >= 3:
        await update.message.reply_text(f"🚨 {uid} достиг максимального числа ⛔Проебов (3/3) !")


# ---------------- UNPRED ----------------

async def unpred(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = get_target(update, context)

    if not uid:
        await update.message.reply_text(
            "Укажи пользователя или ответь на сообщение."
        )
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
        f"✅ С пользователя @{uid} снято предупреждение"
    )

# ---------------- UNPRPROEB ----------------

async def unproeb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = get_target(update, context)

    if not uid:
        await update.message.reply_text(
            "Укажи пользователя или ответь на сообщение."
        )
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
        f"✅ С пользователя @{uid} снят проеб"
    )

# ---------------- ALL REMOVE ----------------

async def unpreds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = clean(context.args[0])
    cnt = len(get(uid, "warn"))

    delete_all(uid, "warn")

    await update.message.reply_text(
        f"С пользователя {uid} были сняты все ⚠️предупреждения ({cnt}/{cnt})"
    )


async def unproebs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("☝️Ты не админ !")
        return

    uid = clean(context.args[0])
    cnt = len(get(uid, "proeb"))

    delete_all(uid, "proeb")

    await update.message.reply_text(
        f"С пользователя {uid} были сняты все ⛔проебы ({cnt}/{cnt})"
    )

# ---------------- STRONG ----------------

async def strong(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = get_target(update, context)

    if not uid:
        await update.message.reply_text(
            "Укажи пользователя или ответь на сообщение."
        )
        return

    warns = get(uid, "warn")

    await update.message.reply_text(
        f"DEBUG\nuid={uid}\nwarns={len(warns)}"
    )

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
        f"⚠️ Предупреждение пользователя @{uid} "
        f"преобразовано в ⛔ Проеб\n"
        f"Не игнорируй предупреждения!"
    )

# ---------------- MYR ----------------

async def myr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = clean(context.args[0]) if context.args else str(update.effective_user.username)

    warns = get_full(uid, "warn")
    proebs = get_full(uid, "proeb")

    if not warns and not proebs:
        await update.message.reply_text("Замечания отсутствуют 🤗")
        return

    text = f"<b>❕ РЕЕСТР ПОЛЬЗОВАТЕЛЯ</b>\n\n👤 @{uid}\n\n"

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

    if not uid:
        await update.message.reply_text(
            "Укажи пользователя или ответь на сообщение."
        )
        return

    warns = get_full(uid, "warn")
    proebs = get_full(uid, "proeb")

    if not warns and not proebs:
        await update.message.reply_text("Замечания отсутствуют 🤗")
        return

    text = f"<b>❕ РЕЕСТР ПОЛЬЗОВАТЕЛЯ</b>\n\n👤 @{uid}\n\n"

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

    for tg_id, username, first_name, name in users:

        if tg_id:

            if username:
                display = (
                    f'<a href="tg://user?id={tg_id}">'
                    f'{username}'
                    f'</a>'
                )
            else:
                display = (
                    f'<a href="tg://user?id={tg_id}">'
                    f'{first_name}'
                    f'</a>'
                )

        elif username:

            display = f"@{username}"

        else:

            display = "Без юза"

        text += f"{name} | {display}\n"

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

    for tg_id, username, first_name, name in users:

        uid = username if username else tg_id

        warns = get(uid, "warn")
        proebs = get(uid, "proeb")

        if not warns and not proebs:
            continue

        if username:
            text += f"{name} | @{username}\n"
        else:
            text += f"{name} | Без юза\n"

        if proebs:
            text += fmt_proeb(proebs) + "\n"

        if warns:
            text += fmt_warn(warns) + "\n"

        text += "\n"

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )
# ---------------- COMM ----------------

async def comm(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if await is_admin(update):

        text = """
<b>📖 СПРАВКА АДМИНИСТРАТОРА</b>

<b>💡 Важно</b>

Большинство команд работают двумя способами:

• Через ник пользователя

<code>Пред @user Причина</code>

• Ответом на сообщение пользователя

<code>Пред Причина</code>

──────────────

<b>Пред</b>
Выдать предупреждение.

Примеры:

<code>Пред @user Флуд</code>

или ответом:

<code>Пред Флуд</code>

──────────────

<b>Проеб</b>
Выдать проеб.

Примеры:

<code>Проеб @user Оскорбление</code>

или ответом:

<code>Проеб Оскорбление</code>

──────────────

<b>Снять пред</b>
Снять предупреждение.

<code>Снять пред @user</code>

Снимает последнее предупреждение.

<code>Снять пред @user 2</code>

Снимает предупреждение №2.

Ответом:

<code>Снять пред</code>

или

<code>Снять пред 2</code>

──────────────

<b>Снять проеб</b>
Работает аналогично предупреждениям.

<code>Снять проеб @user</code>

<code>Снять проеб @user 2</code>

──────────────

<b>Снять преды</b>
Снять все предупреждения пользователя.

<code>Снять преды @user</code>

──────────────

<b>Снять проебы</b>
Снять все проебы пользователя.

<code>Снять проебы @user</code>

──────────────

<b>Стронг</b>
Преобразовать предупреждение в проеб.

<code>Стронг @user</code>

Последнее предупреждение.

<code>Стронг @user 2</code>

Предупреждение №2.

Ответом:

<code>Стронг</code>

или

<code>Стронг 2</code>

──────────────

<b>Ад</b>
Добавить пользователя.

<code>Ад @user Имя</code>

──────────────

<b>Дел</b>
Удалить пользователя.

<code>Дел @user</code>

──────────────

<b>Ренейм / Рен</b>
Изменить имя пользователя.

<code>Ренейм @user Новое Имя</code>

──────────────

<b>Релист</b>
Показать список участников.

<b>Реестр</b>
Показать общий реестр нарушений.

<b>Рее</b>
Показать реестр конкретного пользователя.

──────────────

<b>Пользовательские команды</b>

Адми — добавить себя в список

Реми — изменить своё имя

Мур — открыть свой реестр

Приписка — показать приписку

Ком — открыть справку
"""

    else:

        text = """
<b>📖 СПРАВКА ПОЛЬЗОВАТЕЛЯ</b>

<b>Адми</b>
Добавить себя в список участников.

Пример:

<code>Адми Starfly</code>

──────────────

<b>Реми</b>
Изменить своё имя в списке.

Пример:

<code>Реми Starfly</code>

──────────────

<b>Мур</b>
Показать свой реестр нарушений.

Пример:

<code>Мур</code>

──────────────

<b>Рее</b>
Показать реестр другого участника.

Примеры:

<code>Рее @user</code>

или ответом на сообщение:

<code>Рее</code>

──────────────

<b>Приписка</b>
Показать приписку.

Пример:

<code>Приписка</code>

──────────────

<b>Ком</b>
Показать эту справку.
"""

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )

# ---------------- APP ----------------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("testset", testset))
app.add_handler(CommandHandler("pripiska", pripiska))
app.add_handler(CommandHandler("add", add))
app.add_handler(CommandHandler("adme", adme))
app.add_handler(CommandHandler("rename", rename))
app.add_handler(CommandHandler("reme", reme))
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
app.add_handler(CommandHandler("comm", comm))

app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        text_commands
    )
)

app.run_polling()
