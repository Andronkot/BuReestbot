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
    tg_id TEXT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    name TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS violations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id TEXT,
    type TEXT,
    reason TEXT,
    created_at TEXT,
    moderator TEXT
)
""")
conn.commit()

# ---------------- HELPERS ----------------

def clean(u):
    return u.replace("@", "").strip()

def display_user(user):
    if user.username:
        return user.username

    return user.first_name

def sync_user(user):
    tg_id = str(user.id)

    username = user.username
    first_name = user.first_name

    cur.execute(
        """
        UPDATE users
        SET username=?,
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

def get_target(update, context):
    if update.message.reply_to_message:
        return str(
            update.message.reply_to_message.from_user.id
        )

    if context.args:
        target = clean(context.args[0])

        cur.execute(
            """
            SELECT tg_id
            FROM users
            WHERE username=?
            """,
            (target,)
        )

        row = cur.fetchone()

        if row:
            return row[0]

    return None

async def is_admin(update: Update):
    admins = await update.effective_chat.get_administrators()
    return any(a.user.id == update.effective_user.id for a in admins)

def add_v(uid, t, r, mod):
    cur.execute(
        """
        INSERT INTO violations
        (tg_id, type, reason, created_at, moderator)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            uid,
            t,
            r,
            datetime.now().isoformat(),
            mod
        )
    )

    conn.commit()

def get(uid, t):
    cur.execute(
        """
        SELECT id, reason
        FROM violations
        WHERE tg_id=? AND type=?
        ORDER BY id ASC
        """,
        (uid, t)
    )

    return cur.fetchall()

def get_full(uid, t):
    cur.execute(
        """
        SELECT id, reason, created_at
        FROM violations
        WHERE tg_id=? AND type=?
        ORDER BY id ASC
        """,
        (uid, t)
    )

    return cur.fetchall()

def get_display(uid):
    cur.execute(
        """
        SELECT username, first_name
        FROM users
        WHERE tg_id=?
        """,
        (uid,)
    )

    row = cur.fetchone()

    if not row:
        return str(uid)

    username, first_name = row

    if username:
        return username

    return first_name or str(uid)

def delete_by_id(i):
    cur.execute("DELETE FROM violations WHERE id=?", (i,))
    conn.commit()

def delete_all(uid, t):
    cur.execute("DELETE FROM violations WHERE user_id=? AND type=?", (uid, t))
    conn.commit()

async def auto_cleanup(update, context):
    cleanup_proebs()

    if update.effective_user:
        sync_user(update.effective_user)

def cleanup_proebs():
    limit = datetime.now() - timedelta(days=30)

    cur.execute(
        """
        DELETE FROM violations
        WHERE type='proeb'
        AND created_at < ?
        """,
        (limit.isoformat(),)
    )

    conn.commit()

def sort_users(users):
    def sort_key(user):

        tg_id, username, first_name, name = user

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

    return sorted(users, key=sort_key)
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

async def text_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    # РЕН

    if lower == "рен" or lower.startswith("рен "):
        parts = text.split(maxsplit=1)

        if len(parts) > 1:
            context.args = parts[1].split()
        else:
            context.args = []

        return await ren(update, context)

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

# ---------------- PRIPISKA ----------------

async def pripiska(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("『乃ｙ")

# ---------------- ADD ----------------

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    # ВАРИАНТ ЧЕРЕЗ РЕПЛАЙ

    if update.message.reply_to_message:

        if not context.args:
            await update.message.reply_text(
                "Укажи ник.\nПример: Ад 『乃ｙStarfly"
            )
            return

        user = update.message.reply_to_message.from_user

        tg_id = str(user.id)
        username = user.username
        first_name = user.first_name
        name = " ".join(context.args)

        cur.execute(
            """
            INSERT OR REPLACE INTO users
            (tg_id, username, first_name, name)
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

    # ВАРИАНТ ЧЕРЕЗ @USERNAME

    if len(context.args) < 2:
        await update.message.reply_text(
            "Использование:\n"
            "Ад @user Ник\n"
            "или реплай + Ад Ник"
        )
        return

    username = clean(context.args[0])
    name = " ".join(context.args[1:])

    cur.execute(
        """
        INSERT OR REPLACE INTO users
        (tg_id, username, first_name, name)
        VALUES (?, ?, ?, ?)
        """,
        (
            username,
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

    tg_id = str(update.effective_user.id)

    username = update.effective_user.username

    first_name = update.effective_user.first_name

    name = " ".join(context.args)

    cur.execute(
        """
        INSERT OR REPLACE INTO users
        (tg_id, username, first_name, name)
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

async def reme(update: Update, context: ContextTypes.DEFAULT_TYPE):

    tg_id = str(update.effective_user.id)

    cur.execute(
        "SELECT 1 FROM users WHERE tg_id=?",
        (tg_id,)
    )

    if not cur.fetchone():
        await update.message.reply_text(
            "Сначала добавь себя через команду Адми."
        )
        return

    if not context.args:
        await update.message.reply_text(
            "Укажи новый ник.\nПример: Реми 『乃ｙStarfly"
        )
        return

    new_name = " ".join(context.args)

    cur.execute(
        """
        UPDATE users
        SET name=?
        WHERE tg_id=?
        """,
        (
            new_name,
            tg_id
        )
    )

    conn.commit()

    await update.message.reply_text(
        "<b>✏️ Ник изменён</b>",
        parse_mode="HTML"
    )

# ---------------- REME ----------------

async def reme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)

    cur.execute(
        "SELECT 1 FROM users WHERE tg_id=?",
        (tg_id,)
    )

    if not cur.fetchone():
        await update.message.reply_text(
            "Сначала добавь себя через команду Адми."
        )
        return

    if not context.args:
        await update.message.reply_text(
            "Укажи новый ник.\nПример: Реми 『乃ｙStarfly"
        )
        return

    new_name = " ".join(context.args)

    cur.execute(
        "UPDATE users SET name=? WHERE tg_id=?",
        (new_name, tg_id)
    )
    conn.commit()

    await update.message.reply_text(
        f"<b>✏️ Ник изменён</b>\n\n",
        parse_mode="HTML"
    )

# ---------------- DEL ----------------

async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = clean(context.args[0])

    cur.execute("DELETE FROM users WHERE user_id=?", (uid,))
    cur.execute("DELETE FROM violations WHERE user_id=?", (uid,))
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
        reason = (
            " ".join(context.args[1:])
            if len(context.args) > 1
            else ""
        )

    mod = (
        f"@{update.effective_user.username}"
        if update.effective_user.username
        else str(update.effective_user.id)
    )

    add_v(uid, "warn", reason, mod)

    display = get_display(uid)

    text = (
        f"❗{display} получает ⚠️ Предупреждение\n"
        f"⏳Будет снято когда исправишься\n"
        f"👺Модератор: {mod}"
    )

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
        reason = (
            " ".join(context.args[1:])
            if len(context.args) > 1
            else ""
        )

    mod = (
        f"@{update.effective_user.username}"
        if update.effective_user.username
        else str(update.effective_user.id)
    )

    add_v(uid, "proeb", reason, mod)

    count = len(get(uid, "proeb"))

    display = get_display(uid)

    text = (
        f"❗{display} получает ⛔ Проеб ({count}/3)\n"
        f"⏳Будет снято через 30 дней\n"
        f"👺Модератор: {mod}"
    )

    if reason:
        text += f"\n💬Причина: {reason}"

    await update.message.reply_text(text)

    if count >= 3:
        await update.message.reply_text(
            f"🚨 {display} достиг максимального числа ⛔Проебов (3/3) !"
        )

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

    display = get_display(uid)

    await update.message.reply_text(
        f"✅ С пользователя {display} снято предупреждение"
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

    display = get_display(uid)

    await update.message.reply_text(
        f"✅ С пользователя {display} снят проеб"
    )

# ---------------- UNPREDS ----------------

async def unpreds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = get_target(update, context)

    if not uid:
        await update.message.reply_text(
            "Укажи пользователя или ответь на сообщение."
        )
        return

    cnt = len(get(uid, "warn"))

    delete_all(uid, "warn")

    display = get_display(uid)

    await update.message.reply_text(
        f"С пользователя {display} были сняты все ⚠️предупреждения ({cnt}/{cnt})"
    )

# ---------------- UNPROEBS ----------------

async def unproebs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text(
            "☝️Ты не админ !"
        )
        return

    uid = get_target(update, context)

    if not uid:
        await update.message.reply_text(
            "Укажи пользователя или ответь на сообщение."
        )
        return

    cnt = len(get(uid, "proeb"))

    delete_all(uid, "proeb")

    display = get_display(uid)

    await update.message.reply_text(
        f"С пользователя {display} были сняты все ⛔проебы ({cnt}/{cnt})"
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

    count = len(get(uid, "proeb"))

    display = get_display(uid)

    await update.message.reply_text(
        f"{display} ⚠️ Предупреждение теперь ⛔ Проеб ({count}/3)\n"
        f"Не игнорируй предупреждения !"
    )

    if count >= 3:
        await update.message.reply_text(
            f"🚨 {display} достиг максимального числа ⛔Проебов (3/3) !"
        )

# ---------------- MYR ----------------

async def myr(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = str(update.effective_user.id)

    warns = get_full(uid, "warn")
    proebs = get_full(uid, "proeb")

    if not warns and not proebs:
        await update.message.reply_text(
            "Замечания отсутствуют 🤗"
        )
        return

    display = get_display(uid)

    text = (
        f"<b>❕ РЕЕСТР ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        f"👤 {display}\n\n"
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

    if not uid:
        await update.message.reply_text(
            "Укажи пользователя или ответь на сообщение."
        )
        return

    warns = get_full(uid, "warn")
    proebs = get_full(uid, "proeb")

    if not warns and not proebs:
        await update.message.reply_text(
            "Замечания отсутствуют 🤗"
        )
        return

    display = get_display(uid)

    text = (
        f"<b>❕ РЕЕСТР ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        f"👤 {display}\n\n"
    )

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

    cur.execute(
        """
        SELECT tg_id, username, name
        FROM users
        """
    )

    users = sort_users(cur.fetchall())

    text = "<b>📋 СПИСОК УЧАСТНИКОВ 📋</b>\n\n"

    for tg_id, username, name in users:

        display = username if username else first_name

        text += f"{name} | {display}\n"

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )


# ---------------- REESTR ----------------

async def reestr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    cur.execute(
        """
        SELECT tg_id, username, name
        FROM users
        """
    )

    users = sort_users(cur.fetchall())

    text = "<b>📛 РЕЕСТР НАРУШЕНИЙ 📛</b>\n\n"

    for tg_id, username, name in users:

        warns = get(tg_id, "warn")
        proebs = get(tg_id, "proeb")

        if not warns and not proebs:
            continue

        if username:
            text += f"{name} | {username}\n"
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

# ТРИГГЕР АВТОПРОВЕРКИ ПРОЕБОВ
app.add_handler(
    MessageHandler(filters.ALL, auto_cleanup),
    group=0
)

# ---------------- APP ----------------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("pripiska", pripiska))
app.add_handler(CommandHandler("add", add))
app.add_handler(CommandHandler("adme", adme))
app.add_handler(CommandHandler("rename", rename))
app.add_handler(CommandHandler("ren", ren))
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
