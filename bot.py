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
from html import escape

TOKEN = os.getenv("TOKEN")


BACKUP_PASSWORD = "774847"

os.makedirs("/data", exist_ok=True)

conn = sqlite3.connect(
    "/data/bot.db",
    check_same_thread=False
)

conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")

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

def _user_row(ref):
    if ref is None:
        return None

    ref = str(ref).lstrip("@").strip()
    if not ref:
        return None

    cur.execute(
        """
        SELECT tg_id, username, first_name, name, nick, game_id
        FROM users
        WHERE tg_id=? OR username=?
        """,
        (ref, ref)
    )

    return cur.fetchone()

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


# ---------------- SELF CHECK ----------------

def self_check(app):

    errors = []

    # TOKEN

    if not TOKEN:
        errors.append("TOKEN отсутствует")

    # HELPERS

    required_helpers = [
        "get_target",
        "show_user_html",
        "sort_users",
        "sort_sostav",
        "user_exists",
        "sync_user"
    ]

    for helper in required_helpers:

        if helper not in globals():

            errors.append(
                f"Helper {helper} не найден"
            )

    # TABLES

    try:

        cur.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type='table'
        """)

        tables = {
            row[0]
            for row in cur.fetchall()
        }

        required_tables = {
            "users",
            "violations",
            "settings",
            "reminders"
        }

        for table in required_tables:

            if table not in tables:

                errors.append(
                    f"Таблица {table} отсутствует"
                )

    except Exception as e:

        errors.append(
            f"Ошибка БД: {e}"
        )

    # COMMANDS

    required_commands = [
        "add",
        "adme",
        "pred",
        "proeb",
        "strong",
        "ree",
        "reestr",
        "reminder"
    ]

    for cmd in required_commands:

        if cmd not in globals():

            errors.append(
                f"Команда {cmd} не найдена"
            )

    # RESULT

    if errors:

        print("\n❌ SELF CHECK FAILED\n")

        for err in errors:

            print(f"🚨 {err}")

        print()

    else:

        print("✅ TOKEN исправен")
        print("✅ База данных подключена")
        print("✅ Таблицы проверены")
        print("✅ Хелперы найдены")
        print("✅ Команды найдены")
        print("🤖 Бот полностью готов к работе")

# ---------------- HELPERS ----------------

# USERS

def user_exists(uid):
    cur.execute(
        """
        SELECT 1
        FROM users
        WHERE username = ?
           OR tg_id = ?
        """,
        (uid, uid)
    )

    return cur.fetchone() is not None


def sync_user(user):
    tg_id = str(user.id)
    username = user.username or ""
    first_name = user.first_name or ""

    # ИЩЕМ ПО TG_ID

    cur.execute(
        """
        SELECT username
        FROM users
        WHERE tg_id = ?
        """,
        (tg_id,)
    )

    row = cur.fetchone()

    if row:
        cur.execute(
            """
            UPDATE users
            SET username=?,
                first_name=?
            WHERE tg_id = ?
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
            WHERE username = ?
            """,
            (username,)
        )

        row = cur.fetchone()

        if row:
            cur.execute(
                """
                UPDATE users
                SET tg_id=?,
                    first_name=?
                WHERE username = ?
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
                SET tg_id=?,
                    first_name=?
                WHERE username = ?
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

    if key == "autopripiska":
        set_setting("autopripiska", "он")
        return "он"

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
                WHERE username = ?
                   OR tg_id = ?
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
                WHERE username = ?
                   OR tg_id = ?
                """, (uid, uid))

    row = cur.fetchone()

    if not row:
        uid = str(uid).lstrip("@").strip()
        if uid and not uid.isdigit():
            return f"@{uid}"
        return uid

    tg_id, username, first_name, name = row
    shown = escape(show_user(uid))

    if tg_id:
        return (
            f'<a href="tg://user?id={tg_id}">'
            f'{shown}'
            f'</a>'
        )

    if username:
        return f"@{escape(username)}"

    return escape(name or show_user(uid))


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


# SORT

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


def sort_sostav(rows):
    def sort_key(row):
        tg_id, username, first_name, name, nick, game_id = row
        value = (nick or name or username or "").strip()

        if not value:
            return (9, "")

        pos = value.find("ｙ")

        if pos != -1 and pos + 1 < len(value):
            ch = value[pos + 1]

            if (
                    ("a" <= ch.lower() <= "z")
                    or
                    ("а" <= ch.lower() <= "я")
            ):
                return (0, ch.lower(), value.lower())

            return (1, value.lower())

        return (2, value.lower())

    return sorted(rows, key=sort_key)


# ADMIN

async def is_admin(update: Update):
    admins = await update.effective_chat.get_administrators()
    return any(a.user.id == update.effective_user.id for a in admins)


# TARGET

def get_target(update, context):
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user

        return (
                user.username
                or str(user.id)
        )

    if context.args:
        return context.args[0].replace("@", "")

    return None


# VIOLATIONS

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
        WHERE user_id = ?
          AND type = ?
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


# REMINDERS

async def reminder_worker(app):
    while True:

        try:

            now = datetime.now(KYIV_TZ)

            current_time = now.strftime("%H:%M")
            current_date = now.strftime("%Y-%m-%d")
            current_weekday = now.weekday()

            cur.execute("""
                        SELECT id,
                               chat_id,
                               period, time, text, last_sent
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
                            WHERE id = ?
                            """, (
                                current_date,
                                rid
                            ))

                conn.commit()

        except Exception as e:
            print("REMINDER ERROR:", e)

        await asyncio.sleep(30)


# SECURITY

def german_shepherd_guard():
    required = [
        "get_target",
        "show_user_html",
        "sort_users",
        "sort_sostav"
    ]

    missing = []

    for name in required:

        if name not in globals():
            missing.append(name)

    if missing:

        print(
            "🐕 ГАВ ГАВ ГАВ! СПИЗДИЛИ ХЕЛПЕРЫ:"
        )

        for item in missing:
            print(f"🚨 {item}")


german_shepherd_guard()

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

# ---------------- TEXT COMMANDS ----------------

async def text_commands(update, context: ContextTypes.DEFAULT_TYPE):

    sync_user(update.effective_user)

    text = update.message.text.strip()
    first_line = text.splitlines()[0].strip()
    lower = first_line.lower()

    # ---------------- ПОЛЬЗОВАТЕЛИ ----------------

    # АДМИ

    if lower == "адми" or lower.startswith("адми "):
        return await adme(update, context)

    # АД

    if lower == "ад" or lower.startswith("ад "):
        return await add(update, context)

    # +НИК

    if lower.startswith("+ник"):
        parts = first_line.split(maxsplit=1)

        if len(parts) > 1:
            context.args = parts[1].split()
        else:
            context.args = []

        return await plus_nick(update, context)

    # +АЙДИ

    if lower.startswith("+айди"):
        parts = first_line.split(maxsplit=1)

        if len(parts) > 1:
            context.args = parts[1].split()
        else:
            context.args = []

        return await plus_id(update, context)

    # НИК

    if lower == "ник" or lower.startswith("ник "):
        parts = first_line.split(maxsplit=1)

        if len(parts) > 1:
            context.args = parts[1].split()
        else:
            context.args = []

        return await nick(update, context)

    # АЙДИ

    if lower == "айди" or lower.startswith("айди "):
        parts = first_line.split(maxsplit=1)

        if len(parts) > 1:
            context.args = parts[1].split()
        else:
            context.args = []

        return await game_id(update, context)

    # СОСТАВ

    if lower == "состав":
        return await sostav(update, context)

    # ПРИПИСКА

    if lower == "приписка":
        return await pripiska(update, context)

    # ДЕЛ

    if lower.startswith("дел "):
        parts = first_line.split(maxsplit=1)

        if len(parts) > 1:
            context.args = parts[1].split()
        else:
            context.args = []

        return await delete(update, context)

    # ---------------- НАРУШЕНИЯ ----------------

    # ПРЕД

    if lower == "пред" or lower.startswith("пред "):
        parts = first_line.split(maxsplit=1)

        if len(parts) > 1:
            context.args = parts[1].split()
        else:
            context.args = []

        return await pred(update, context)

    # ПРОЕБ

    if lower == "проеб" or lower.startswith("проеб "):
        parts = first_line.split(maxsplit=1)

        if len(parts) > 1:
            context.args = parts[1].split()
        else:
            context.args = []

        return await proeb(update, context)

    # СТРОНГ

    if lower == "стронг" or lower.startswith("стронг "):
        parts = first_line.split(maxsplit=1)

        if len(parts) > 1:
            context.args = parts[1].split()
        else:
            context.args = []

        return await strong(update, context)

    # СНЯТЬ ПРЕД

    if lower == "снять пред" or lower.startswith("снять пред "):
        parts = first_line.split(maxsplit=2)

        if len(parts) > 2:
            context.args = parts[2].split()
        else:
            context.args = []

        return await unpred(update, context)

    # СНЯТЬ ПРОЕБ

    if lower == "снять проеб" or lower.startswith("снять проеб "):
        parts = first_line.split(maxsplit=2)

        if len(parts) > 2:
            context.args = parts[2].split()
        else:
            context.args = []

        return await unproeb(update, context)

    # СНЯТЬ ПРЕДЫ

    if lower == "снять преды" or lower.startswith("снять преды "):
        parts = first_line.split(maxsplit=2)

        if len(parts) > 2:
            context.args = parts[2].split()
        else:
            context.args = []

        return await unpreds(update, context)

    # СНЯТЬ ПРОЕБЫ

    if lower == "снять проебы" or lower.startswith("снять проебы "):
        parts = first_line.split(maxsplit=2)

        if len(parts) > 2:
            context.args = parts[2].split()
        else:
            context.args = []

        return await unproebs(update, context)

    # ---------------- РЕЕСТРЫ ----------------

    # МУР

    if lower == "мур":
        context.args = []
        return await myr(update, context)

    # РЕЕ

    if lower == "рее" or lower.startswith("рее "):
        parts = first_line.split(maxsplit=1)

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

    # ---------------- НАПОМИНАЛКИ ----------------

    # НАПОМИНАЛКА

    if lower == "напоминалка" or lower.startswith("напоминалка "):

        parts = first_line.split()

        if len(parts) >= 3:
            context.args = [parts[1], parts[2]]
        else:
            context.args = []

        return await reminder(update, context)

    # НАПОМИНАЛКИ

    if lower == "напоминалки":
        return await reminders(update, context)

    # ИЗМЕНИТЬ НАП

    if lower == "изменить нап" or lower.startswith("изменить нап "):
        return await edit_reminder(update, context)

    # ПЕРИОД НАП

    if lower.startswith("период нап "):
        return await period_reminder(update, context)

    # ВРЕМЯ НАП

    if lower.startswith("время нап "):
        return await time_reminder(update, context)

    # УДАЛИТЬ НАП

    if lower.startswith("удалить нап "):

        parts = first_line.split(maxsplit=2)

        if len(parts) > 2:
            context.args = [parts[2]]
        else:
            context.args = []

        return await del_reminder(update, context)

    # ---------------- НАСТРОЙКИ ----------------

    # СЕТ

    if lower == "сет" or lower.startswith("сет "):
        parts = first_line.split(maxsplit=1)

        if len(parts) > 1:
            context.args = parts[1].split()
        else:
            context.args = []

        return await set_cmd(update, context)

    # СЕТТ

    if lower == "сетт":
        context.args = []
        return await setting(update, context)

    # ---------------- СПРАВКА ----------------

    # КОМ

    if lower == "ком":
        return await comm(update, context)

    # ---------------- БЕКАП ----------------

    #БЕКАП

    if lower == "бекап" or lower.startswith("бекап "):

        parts = first_line.split(maxsplit=1)

        if len(parts) > 1:
            context.args = [parts[1]]
        else:
            context.args = []

        return await backup(update, context)

    # АВТОПРИПИСКА

    if get_setting("autopripiska") == "он":

        trigger_words = [
            "приписка",
            "преписка",
            "преписку",
            "приписку",
            "преписку",
            "приписки",
            "преписки",
            "перед ником",
            "для ника",
            "в ник"
        ]

        msg_text = text.lower()

        if any(word in msg_text for word in trigger_words):
            return await pripiska(update, context)

# ---------------- COMMANDS ----------------

# ---------------- PLUS NICK ----------------

async def plus_nick(update, context):

    args = [a.strip() for a in context.args if a.strip()]

    if not args:
        await update.message.reply_text(
            "❌ Укажи ник."
        )
        return

    self_ref = update.effective_user.username or str(update.effective_user.id)

    target_user = None
    explicit_target = False

    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        target_ref = str(target_user.id)
        nick_parts = args

    elif await is_admin(update) and len(args) >= 2 and (
        args[0].startswith("@") or args[0].isdigit()
    ):
        explicit_target = True
        target_ref = args[0].lstrip("@").strip()
        nick_parts = args[1:]

    else:
        target_ref = self_ref
        nick_parts = args

    nick = " ".join(nick_parts).strip()

    if not nick:
        await update.message.reply_text(
            "❌ Укажи ник."
        )
        return

    row = _user_row(target_ref)
    old_display = show_user_html(target_ref)

    if row and (row[4] or "") == nick:
        await update.message.reply_text(
            "📝 Указан тот же самый ник"
        )
        return

    if row:
        cur.execute(
            """
            UPDATE users
            SET nick=?
            WHERE tg_id=? OR username=?
            """,
            (nick, target_ref, target_ref)
        )
    else:
        if target_user:
            tg_id = str(target_user.id)
            username = target_user.username or ""
            first_name = target_user.first_name or ""
            name = target_user.first_name or target_user.username or nick
        elif target_ref.isdigit():
            tg_id = target_ref
            username = ""
            first_name = ""
            name = nick
        else:
            tg_id = str(update.effective_user.id)
            username = update.effective_user.username or ""
            first_name = update.effective_user.first_name or ""
            name = first_name or username or nick

        cur.execute(
            """
            INSERT INTO users
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
                name,
                nick,
                ""
            )
        )

    conn.commit()

    await update.message.reply_text(
        f"✅ Ник {old_display} изменён на «{escape(nick)}»",
        parse_mode="HTML"
    )

# ---------------- PLUS ID ----------------

async def plus_id(update, context):

    args = [a.strip() for a in context.args if a.strip()]

    if not args:
        await update.message.reply_text(
            "❌ Укажи айди."
        )
        return

    self_ref = update.effective_user.username or str(update.effective_user.id)

    target_user = None

    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        target_ref = str(target_user.id)
        id_parts = args

    elif await is_admin(update) and len(args) >= 2 and (
        args[0].startswith("@") or args[0].isdigit()
    ):
        target_ref = args[0].lstrip("@").strip()
        id_parts = args[1:]

    else:
        target_ref = self_ref
        id_parts = args

    gid = " ".join(id_parts).strip()

    if not gid:
        await update.message.reply_text(
            "❌ Укажи айди."
        )
        return

    row = _user_row(target_ref)
    old_display = show_user_html(target_ref)

    if row and (row[5] or "") == gid:
        await update.message.reply_text(
            "📝 Указан тот же самый айди"
        )
        return

    if row:
        cur.execute(
            """
            UPDATE users
            SET game_id=?
            WHERE tg_id=? OR username=?
            """,
            (gid, target_ref, target_ref)
        )
    else:
        if target_user:
            tg_id = str(target_user.id)
            username = target_user.username or ""
            first_name = target_user.first_name or ""
            name = target_user.first_name or target_user.username or ""
        elif target_ref.isdigit():
            tg_id = target_ref
            username = ""
            first_name = ""
            name = ""
        else:
            tg_id = str(update.effective_user.id)
            username = update.effective_user.username or ""
            first_name = update.effective_user.first_name or ""
            name = first_name or username or ""

        cur.execute(
            """
            INSERT INTO users
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
                name,
                "",
                gid
            )
        )

    conn.commit()

    await update.message.reply_text(
        f"✅ Айди {old_display} изменён на «{escape(gid)}»",
        parse_mode="HTML"
    )

# ---------------- PRIPISKA ----------------

async def pripiska(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("『乃ｙ")

# ---------------- ADME ----------------

async def adme(update: Update, context: ContextTypes.DEFAULT_TYPE):

    lines = [line.strip() for line in update.message.text.splitlines() if line.strip()]

    if len(lines) < 3:
        await update.message.reply_text(
            "❌ Формат:\n\n"
            "Адми\n"
            "Ник\n"
            "Айди"
        )
        return

    nick = lines[1].strip()
    game_id = lines[2].strip()

    user = update.effective_user
    self_ref = user.username or str(user.id)

    old_display = show_user_html(self_ref)

    cur.execute(
        "DELETE FROM users WHERE tg_id=? OR username=?",
        (str(user.id), user.username)
    )

    cur.execute(
        """
        INSERT INTO users
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
            user.username,
            user.first_name or "",
            nick,
            nick,
            game_id
        )
    )

    conn.commit()

    await update.message.reply_text(
        f"✅ Пользователь {old_display} добавлен\n\n"
        f"🎮 {escape(nick)}\n"
        f"🆔 {escape(game_id)}",
        parse_mode="HTML"
    )

# ---------------- ADD ----------------

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await is_admin(update):
        return

    lines = [line.strip() for line in update.message.text.splitlines() if line.strip()]

    if len(lines) < 3:
        await update.message.reply_text(
            "❌ Формат:\n\n"
            "Ад @user\n"
            "Ник\n"
            "Айди"
        )
        return

    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        target_ref = str(target_user.id)
        target_tg_id = str(target_user.id)
        target_username = target_user.username
        target_first_name = target_user.first_name or ""
    else:
        first_parts = lines[0].split(maxsplit=1)

        if len(first_parts) < 2:
            await update.message.reply_text(
                "❌ Укажи пользователя или ответь на сообщение."
            )
            return

        target_ref = first_parts[1].lstrip("@").strip()
        row = _user_row(target_ref)

        if row:
            target_tg_id, target_username, target_first_name, _, _, _ = row
        else:
            target_tg_id = target_ref if target_ref.isdigit() else None
            target_username = None if target_ref.isdigit() else target_ref
            target_first_name = ""

    nick = lines[1].strip()
    game_id = lines[2].strip()

    old_display = show_user_html(target_ref)

    cur.execute(
        "DELETE FROM users WHERE tg_id=? OR username=?",
        (target_tg_id, target_username)
    )

    cur.execute(
        """
        INSERT INTO users
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
            target_tg_id,
            target_username,
            target_first_name,
            nick,
            nick,
            game_id
        )
    )

    conn.commit()

    await update.message.reply_text(
        f"✅ Пользователь {old_display} добавлен\n\n"
        f"🎮 {escape(nick)}\n"
        f"🆔 {escape(game_id)}",
        parse_mode="HTML"
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

    if context.args:

        uid = clean(context.args[0])

    else:

        uid = (
            update.effective_user.username
            or str(update.effective_user.id)
        )

    if not user_exists(uid):

        msg = await update.message.reply_text(
            "Тебя нету в базе.\nИди нахуй! 😹"
        )

        await asyncio.sleep(2)

        await msg.edit_text(
            "Тебя нету в базе.\nДобавь себя: Адми Ник "
        )

        return

    # ПАСХАЛКА

    await update.message.reply_text(
        "Мяу блять 😹"
    )

    warns = get_full(uid, "warn")
    proebs = get_full(uid, "proeb")

    if not warns and not proebs:

        await update.message.reply_text(
            "Замечания отсутствуют 🤗"
        )

        return

    text = (
        f"<b>❕ РЕЕСТР ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        f"👤 {show_user_html(uid)}\n\n"
    )

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

    ref = None

    if await is_admin(update):
        ref = get_target(update, context)

    if not ref:
        ref = update.effective_user.username or str(update.effective_user.id)

    row = _user_row(ref)

    if not row:
        await update.message.reply_text(
            "❌ Пользователь не найден в реестре"
        )
        return

    await update.message.reply_text(
        row[4] if row[4] else "Не указан"
    )

# ---------------- GAME ID ----------------

async def game_id(update, context):

    ref = None

    if await is_admin(update):
        ref = get_target(update, context)

    if not ref:
        ref = update.effective_user.username or str(update.effective_user.id)

    row = _user_row(ref)

    if not row:
        await update.message.reply_text(
            "❌ Пользователь не найден в реестре"
        )
        return

    await update.message.reply_text(
        row[5] if row[5] else "Не указан"
    )

# ---------------- SOSTAV ----------------

async def sostav(update, context):

    cur.execute(
        """
        SELECT
            tg_id,
            username,
            first_name,
            name,
            nick,
            game_id
        FROM users
        """
    )

    rows = sort_sostav(cur.fetchall())

    if not rows:
        await update.message.reply_text(
            "Состав пуст."
        )
        return

    text = "<b>📋 СОСТАВ</b>\n\n"

    for tg_id, username, first_name, name, nick, gid in rows:

        uid = username if username else tg_id

        if uid:
            left = show_user_html(uid)
        else:
            left = escape(name or first_name or "—")

        nick = escape(nick or "—")
        gid = escape(gid or "—")

        text += (
            f"{left} | "
            f"{nick} | "
            f"{gid}\n"
        )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        disable_web_page_preview=True
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
            """
📭 Напоминалок нет.

<code>Напоминалка пятница 12:00</code> - ➕ Создать напоминалку
""",
            parse_mode="HTML"
        )

        return

    text = """
<b>⏰ НАПОМИНАЛКИ</b>

<code>Напоминалка пятница 12:00</code> - ➕ Создать напоминалку

--------------------------------

"""

    for rid, period, time_str, reminder_text in rows:

        short_text = reminder_text

        if len(short_text) > 50:
            short_text = short_text[:50] + "..."

        text += (
            f"🆔 {rid}\n"
            f"📅 {period}\n"
            f"⏰ {time_str}\n"
            f"💬 {short_text}\n\n"
        )

    text += """
--------------------------------

<code>Изменить нап ID</code> - ✏️ Изменить текст
<code>Период нап ID период</code> - 📅 Изменить период
<code>Время нап ID время</code> - ⏰ Изменить время
<code>Удалить нап ID</code> - 🗑️ Удалить напоминалку
"""

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

async def set_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await is_admin(update):
        return

    if len(context.args) != 2:
        return

    section = context.args[0].lower()
    value = context.args[1].lower()

    modes = {
        "1": "username",
        "2": "firstname",
        "3": "reestr"
    }

    # АВТОПРИПИСКА

    if section == "ап":

        if value not in ["он", "оф"]:
            await update.message.reply_text(
                "❌ Используй:\nСет ап он\nСет ап оф"
            )
            return

        set_setting(
            "autopripiska",
            value
        )

        await update.message.reply_text(
            f"✅ Автоприписка: {value}"
        )

        return

    # ОС

    if section == "ос":

        if value not in modes:
            return

        set_setting(
            "os",
            modes[value]
        )

    # ОК

    elif section == "ок":

        if value not in modes:
            return

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

    f"Автоприписка: {get_setting('autopripiska')}\n"

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

    --------------------------------

    <b>📎 Автоприписка</b>
    <i>Автоматический ответ на слово "приписка"</i>

    {"🟢 <code>ВКЛ</code>" if get_setting("autopripiska") == "он" else "⚫ <code>ВЫКЛ</code>"}

    ✍️ Изменить:
    Сет ап [он/оф]
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

<code>Адми</code>
Добавить себя в список

<code>Ник</code>
Показать свой ник

<code>Айди</code>
Показать свой айди

<code>Мур</code>
Показать свой реестр

<code>Рее @user</code>
Показать реестр пользователя

<code>Состав</code>
Показать список участников

<code>Приписка</code>
Показать приписку

--------------------------------

<b>👥 Управление пользователями</b>

<code>Ад @user</code>
Добавить пользователя

<code>+Ник @user Ник</code>
Изменить ник

<code>+Айди @user 123</code>
Изменить айди

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

<code>Релист</code>
Список добавленных пользователей

<code>Реестр</code>
Общий реестр нарушений

--------------------------------

<b>⏰ Напоминания</b>

<code>Напоминалка пятница 12:00</code>
Создать напоминалку

<code>Напоминалки</code>
Показать список

<code>Изменить нап 1</code>
Изменить текст

<code>Период нап 1 пятница</code>
Изменить период

<code>Время нап 1 12:00</code>
Изменить время

<code>Удалить нап 1</code>
Удалить напоминалку

--------------------------------

<b>⚙️ Настройки</b>

<code>Сетт</code>
Открыть настройки

<code>Сет ос [1-3]</code>
Отображение в списках

<code>Сет ок [1-3]</code>
Отображение в командах

<code>Сет ап он/оф</code>
Вкл/выкл автоприписка
--------------------------------

<b>📖 Прочее</b>

<code>Комм</code>
Показать список команд
"""

    else:

        text = """
<b>📚 СПИСОК КОМАНД 📚</b>

<b>👤 Пользователи</b>

<code>Адми</code>
Добавить себя в список

<code>Ник</code>
Показать свой ник

<code>Айди</code>
Показать свой айди

<code>Мур</code>
Показать свой реестр

<code>Рее @user</code>
Показать реестр пользователя

<code>Состав</code>
Показать список участников

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

# ---------------- BACKUP ----------------


async def backup(update, context):

    if update.effective_chat.type != "private":
        return

    if not context.args:
        await update.message.reply_text(
            "❌ Укажи пароль"
        )
        return

    password = context.args[0]

    if password != BACKUP_PASSWORD:
        await update.message.reply_text(
            "❌ Неверный пароль"
        )
        return

    await update.message.reply_document(
        document=open("/data/bot.db", "rb"),
        filename="bot.db"
    )

# ---------------- APP ----------------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        text_commands
    )
)

app.add_handler(CommandHandler("comm", comm))

async def on_startup(app):
    asyncio.create_task(reminder_worker(app))

app.post_init = on_startup

self_check(app)

app.run_polling()
