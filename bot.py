import os
import sqlite3
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = os.getenv("TOKEN")

conn = sqlite3.connect("bot.db", check_same_thread=False)
cur = conn.cursor()

# USERS
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    name TEXT
)
""")

# VIOLATIONS
cur.execute("""
CREATE TABLE IF NOT EXISTS violations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    type TEXT,
    reason TEXT,
    created_at TEXT
)
""")

conn.commit()


# ---------------- HELPERS ----------------

async def is_admin(update: Update):
    chat = update.effective_chat
    user_id = update.effective_user.id

    admins = await chat.get_administrators()
    return any(a.user.id == user_id for a in admins)


def add_violation(uid, vtype, reason):
    cur.execute(
        "INSERT INTO violations(user_id,type,reason,created_at) VALUES (?,?,?,?)",
        (uid, vtype, reason, datetime.now().isoformat())
    )
    conn.commit()


def get_user_violations(uid, vtype=None):
    if vtype:
        cur.execute("SELECT id, reason FROM violations WHERE user_id=? AND type=?", (uid, vtype))
    else:
        cur.execute("SELECT id, type, reason FROM violations WHERE user_id=?", (uid,))
    return cur.fetchall()


def delete_violation(vid):
    cur.execute("DELETE FROM violations WHERE id=?", (vid,))
    conn.commit()


def delete_user(uid):
    cur.execute("DELETE FROM users WHERE user_id=?", (uid,))
    cur.execute("DELETE FROM violations WHERE user_id=?", (uid,))
    conn.commit()


def cleanup_old():
    limit = datetime.now() - timedelta(days=30)
    cur.execute("DELETE FROM violations WHERE datetime(created_at) < ?", (limit.isoformat(),))
    conn.commit()


# ---------------- COMMANDS ----------------

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = context.args[0]
    name = context.args[1]

    cur.execute("INSERT OR REPLACE INTO users VALUES (?,?)", (uid, name))
    conn.commit()

    await update.message.reply_text("Пользователь добавлен")


async def del_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = context.args[0]
    delete_user(uid)

    await update.message.reply_text("Пользователь удалён")


async def pred(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = context.args[0]
    reason = " ".join(context.args[1:])

    add_violation(uid, "warn", reason)

    await update.message.reply_text(f"@{uid} ⚠️ Предупреждение\nПричина:\n{reason}")


async def proeb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = context.args[0]
    reason = " ".join(context.args[1:])

    add_violation(uid, "proeb", reason)

    count = len(get_user_violations(uid, "proeb"))

    await update.message.reply_text(f"@{uid} ⛔ Проеб\nПричина:\n{reason}")

    if count >= 3:
        await update.message.reply_text(f"Пользователь @{uid} достиг максимального числа проебов.")


async def unpred(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = context.args[0]
    vid = int(context.args[1])

    delete_violation(vid)
    await update.message.reply_text("Предупреждение снято")


async def unpreds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = context.args[0]
    cur.execute("DELETE FROM violations WHERE user_id=? AND type='warn'", (uid,))
    conn.commit()

    await update.message.reply_text("Все предупреждения сняты")


async def unproeb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = context.args[0]
    vid = int(context.args[1])

    delete_violation(vid)
    await update.message.reply_text("Проеб снят")


async def unproebs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = context.args[0]
    cur.execute("DELETE FROM violations WHERE user_id=? AND type='proeb'", (uid,))
    conn.commit()

    await update.message.reply_text("Все проебы сняты")


async def strong(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = context.args[0]
    vid = int(context.args[1])

    cur.execute("SELECT reason FROM violations WHERE id=?", (vid,))
    row = cur.fetchone()

    if not row:
        return

    reason = row[0]

    delete_violation(vid)
    add_violation(uid, "proeb", reason)

    await update.message.reply_text(
        f"@{uid} ⚠️ Предупреждение\nПричина:\n{reason}\n\n"
        f"Теперь ⛔ Проеб\nНе игнорируйте предупреждения"
    )


async def relist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    cur.execute("SELECT * FROM users")
    users = cur.fetchall()

    text = "СПИСОК УЧАСТНИКОВ\n\n"

    for uid, name in users:
        text += f"{name} | @{uid}\n"

    await update.message.reply_text(text)


async def reestr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    cur.execute("SELECT * FROM users")
    users = cur.fetchall()

    text = "РЕЕСТР НАРУШЕНИЙ\n\n"

    for uid, name in users:
        warns = get_user_violations(uid, "warn")
        proebs = get_user_violations(uid, "proeb")

        if not warns and not proebs:
            continue

        text += f"{name} | @{uid}\n\n"

        for i, (_, r) in enumerate(proebs, 1):
            text += f"{i}. ⛔ {r}\n"

        text += "\n"

        for i, (_, r) in enumerate(warns, 1):
            text += f"{i}. ⚠️ {r}\n"

        text += "\n"

    await update.message.reply_text(text)


# ---------------- APP ----------------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("add", add))
app.add_handler(CommandHandler("del", del_user))
app.add_handler(CommandHandler("pred", pred))
app.add_handler(CommandHandler("proeb", proeb))
app.add_handler(CommandHandler("unpred", unpred))
app.add_handler(CommandHandler("unpreds", unpreds))
app.add_handler(CommandHandler("unproeb", unproeb))
app.add_handler(CommandHandler("unproebs", unproebs))
app.add_handler(CommandHandler("strong", strong))
app.add_handler(CommandHandler("relist", relist))
app.add_handler(CommandHandler("reestr", reestr))

app.run_polling()
