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
    user_id TEXT PRIMARY KEY,
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

conn.commit()

# ---------------- HELPERS ----------------

def clean(u):
    return u.replace("@", "").strip()

def get_target(update, context):
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user

        if user.username:
            return user.username

        return str(user.id)

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

def delete_by_id(i):
    cur.execute("DELETE FROM violations WHERE id=?", (i,))
    conn.commit()

def delete_all(uid, t):
    cur.execute("DELETE FROM violations WHERE user_id=? AND type=?", (uid, t))
    conn.commit()

# ---------------- FORMAT ----------------

def fmt_warn(warns):
    if not warns:
        return ""
    return "\n".join([f"{i+1}. ⚠️ {r}" for i, (_, r) in enumerate(warns)])

def fmt_proeb(proebs):
    if not proebs:
        return ""
    return "\n".join([f"{i+1}. ⛔ {r}" for i, (_, r) in enumerate(proebs)])

# ---------------- TEXT COMMANDS ----------------

# ---------------- TEXT COMMANDS ----------------

async def text_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    lower = text.lower()

    # ПРИПИСКА

    if lower == "приписка":
        return await pripiska(update, context)

    # МУР

    if lower == "мур":
        context.args = []
        return await myr(update, context)

    # РЕЕ

    if lower.startswith("рее"):
        parts = text.split(maxsplit=1)

        if len(parts) > 1:
            context.args = [parts[1]]
        else:
            context.args = []

        return await ree(update, context)

    # РЕЕСТР

    if lower == "реестр":
        return await reestr(update, context)

    # РЕЛИСТ

    if lower == "релист":
        return await relist(update, context)

    # АД

    if lower.startswith("ад"):
        parts = text.split(maxsplit=1)

        if len(parts) > 1:
            context.args = parts[1].split()
        else:
            context.args = []

        return await add(update, context)

    # ДЕЛ

    if lower.startswith("дел"):
        parts = text.split(maxsplit=1)

        if len(parts) > 1:
            context.args = parts[1].split()
        else:
            context.args = []

        return await delete(update, context)

    # ПРЕД

    if lower.startswith("пред"):
        parts = text.split(maxsplit=1)

        if len(parts) > 1:
            context.args = parts[1].split()
        else:
            context.args = []

        return await pred(update, context)

    # ПРОЕБ

    if lower.startswith("проеб"):
        parts = text.split(maxsplit=1)

        if len(parts) > 1:
            context.args = parts[1].split()
        else:
            context.args = []

        return await proeb(update, context)

    # СНЯТЬ ПРЕДЫ

    if lower.startswith("снять преды"):
        parts = text.split(maxsplit=2)

        if len(parts) > 2:
            context.args = parts[2].split()
        else:
            context.args = []

        return await unpreds(update, context)

    # СНЯТЬ ПРЕД

    if lower.startswith("снять пред"):
        parts = text.split(maxsplit=2)

        if len(parts) > 2:
            context.args = parts[2].split()
        else:
            context.args = []

        return await unpred(update, context)

    # СНЯТЬ ПРОЕБЫ

    if lower.startswith("снять проебы"):
        parts = text.split(maxsplit=2)

        if len(parts) > 2:
            context.args = parts[2].split()
        else:
            context.args = []

        return await unproebs(update, context)

    # СНЯТЬ ПРОЕБ

    if lower.startswith("снять проеб"):
        parts = text.split(maxsplit=2)

        if len(parts) > 2:
            context.args = parts[2].split()
        else:
            context.args = []

        return await unproeb(update, context)

    # СТРОНГ

    if lower.startswith("стронг"):
        parts = text.split(maxsplit=1)

        if len(parts) > 1:
            context.args = parts[1].split()
        else:
            context.args = []

        return await strong(update, context)

    # РЕНЕЙМ

    if lower.startswith("ренейм"):
        parts = text.split(maxsplit=1)

        if len(parts) > 1:
            context.args = parts[1].split()
        else:
            context.args = []

        return await rename(update, context)

    # РЕН

    if lower.startswith("рен"):
        parts = text.split(maxsplit=1)

        if len(parts) > 1:
            context.args = parts[1].split()
        else:
            context.args = []

        return await ren(update, context)

# ---------------- COMMANDS ----------------

# ---------------- PRIPISKA ----------------

async def pripiska(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("『乃ｙ")

# ---------------- ADD ----------------
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = clean(context.args[0])
    name = " ".join(context.args[1:])

    cur.execute(
        "INSERT OR REPLACE INTO users VALUES (?,?)",
        (uid, name)
    )
    conn.commit()

    await update.message.reply_text(
        "<b>👤 Пользователь добавлен</b>",
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
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else ""

    mod = (
        f"@{update.effective_user.username}"
        if update.effective_user.username
        else str(update.effective_user.id)
    )

    add_v(uid, "warn", reason, mod)

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

    if len(context.args) < 1:
        await update.message.reply_text("Использование: /strong @user [номер]")
        return

    uid = get_target(update, context)

    if not uid:
        await update.message.reply_text(
            "Укажи пользователя или ответь на сообщение."
        )
        return
    warns = get(uid, "warn")

    if not warns:
        await update.message.reply_text("⚠️ У пользователя нет предупреждений")
        return

    if len(context.args) == 1:
        idx = len(warns) - 1
    else:
        try:
            idx = int(context.args[1]) - 1

            if idx < 0 or idx >= len(warns):
                await update.message.reply_text("❌ Неверный номер предупреждения")
                return

        except ValueError:
            await update.message.reply_text("❌ Номер должен быть числом")
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
        f"<b>⚠️ Предупреждение пользователя @{uid} заменено на ⛔ Проеб</b>\n\n"
        "Не игнорируй предупреждения!",
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

    cur.execute("UPDATE users SET name=? WHERE user_id=?", (new_name, uid))
    conn.commit()

    await update.message.reply_text(
        "<b>✏️ Пользователь переименован</b>",
        parse_mode="HTML"
    )


async def ren(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await rename(update, context)

# ---------------- MYR ----------------

async def myr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = clean(context.args[0]) if context.args else str(update.effective_user.username)

    warns = get(uid, "warn")
    proebs = get(uid, "proeb")

    if not warns and not proebs:
        await update.message.reply_text("Замечания отсутствуют 🤗")
        return

    text = f"<b>❕ РЕЕСТР ПОЛЬЗОВАТЕЛЯ</b>\n\n👤 @{uid}\n\n"

    if proebs:
        text += fmt_proeb(proebs) + "\n\n"

    if warns:
        text += fmt_warn(warns)

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

    warns = get(uid, "warn")
    proebs = get(uid, "proeb")

    if not warns and not proebs:
        await update.message.reply_text("Замечания отсутствуют 🤗")
        return

    text = f"<b>❕ РЕЕСТР ПОЛЬЗОВАТЕЛЯ</b>\n\n👤 @{uid}\n\n"

    if proebs:
        text += fmt_proeb(proebs) + "\n\n"

    if warns:
        text += fmt_warn(warns)

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )


# ---------------- RELIST ----------------

async def relist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    cur.execute("SELECT * FROM users")
    users = cur.fetchall()

    text = "<b>📋 СПИСОК УЧАСТНИКОВ 📋</b>\n\n"

    for uid, name in users:
        text += f"{name} | @{uid}\n"

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )


# ---------------- REESTR ----------------

async def reestr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    cur.execute("SELECT * FROM users")
    users = cur.fetchall()

    text = "<b>📛 РЕЕСТР НАРУШЕНИЙ 📛</b>\n\n"

    for uid, name in users:
        warns = get(uid, "warn")
        proebs = get(uid, "proeb")

        if not warns and not proebs:
            continue

        text += f"{name} | @{uid}\n"

        if proebs:
            text += fmt_proeb(proebs) + "\n"

        if warns:
            text += fmt_warn(warns) + "\n"

        text += "\n"

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
app.add_handler(CommandHandler("rename", rename))
app.add_handler(CommandHandler("ren", ren))

app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        text_commands
    )
)

app.run_polling()
