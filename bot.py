import os
import sqlite3
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = os.getenv("TOKEN")

conn = sqlite3.connect("bot.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, name TEXT)""")

cur.execute("""CREATE TABLE IF NOT EXISTS violations (
id INTEGER PRIMARY KEY AUTOINCREMENT,
user_id TEXT,
type TEXT,
reason TEXT,
created_at TEXT
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS admins (user_id TEXT PRIMARY KEY)""")

conn.commit()


def is_admin(uid):
    cur.execute("SELECT 1 FROM admins WHERE user_id=?", (uid,))
    return cur.fetchone() is not None


def add_v(uid, t, r):
    cur.execute("INSERT INTO violations(user_id,type,reason,created_at) VALUES (?,?,?,?)",
                (uid, t, r, datetime.now().isoformat()))
    conn.commit()


def get_v(uid):
    cur.execute("SELECT type, reason FROM violations WHERE user_id=?", (uid,))
    return cur.fetchall()


# --- COMMANDS ---

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid, name = context.args[0], context.args[1]
    cur.execute("INSERT OR REPLACE INTO users VALUES (?,?)", (uid, name))
    conn.commit()
    await update.message.reply_text("Добавлен")


async def admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cur.execute("DELETE FROM admins")
    for a in context.args:
        cur.execute("INSERT INTO admins VALUES (?)", (a,))
    conn.commit()
    await update.message.reply_text("Ок")


async def pred(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(str(update.effective_user.id)):
        return

    uid = context.args[0]
    reason = " ".join(context.args[1:])

    add_v(uid, "warn", reason)

    warns = len([v for v in get_v(uid) if v[0] == "warn"])

    await update.message.reply_text(f"⚠️ Пред: {reason}")

    if warns >= 2:
        await update.message.reply_text("⏳ 2 преда → скоро проеб")


async def proeb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(str(update.effective_user.id)):
        return

    uid = context.args[0]
    reason = " ".join(context.args[1:])

    add_v(uid, "proeb", reason)

    proebs = len([v for v in get_v(uid) if v[0] == "proeb"])

    await update.message.reply_text(f"⛔ Проеб: {reason}")

    if proebs >= 3:
        await update.message.reply_text("🚨 3 проеба → кик (логика заглушка)")


async def reestr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cur.execute("SELECT * FROM users")
    users = cur.fetchall()

    text = "📋 РЕЕСТР НАРУШЕНИЙ\n\n"

    for uid, name in users:
        v = get_v(uid)
        if not v:
            continue
        text += f"{name} | {uid}\n"
        for t, r in v:
            text += ("⚠️ " if t == "warn" else "⛔ ") + r + "\n"
        text += "\n"

    await update.message.reply_text(text)


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("add", add))
app.add_handler(CommandHandler("admins", admins))
app.add_handler(CommandHandler("pred", pred))
app.add_handler(CommandHandler("proeb", proeb))
app.add_handler(CommandHandler("reestr", reestr))

app.run_polling()
