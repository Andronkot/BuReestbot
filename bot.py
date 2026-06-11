import os
import sqlite3
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

TOKEN = os.getenv("TOKEN")

conn = sqlite3.connect("bot.db", check_same_thread=False, timeout=10)
cur = conn.cursor()

# ---------------- DB ----------------

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    name TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS violations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    type TEXT,
    reason TEXT,
    created_at TEXT,
    moderator TEXT
)
""")

conn.commit()

# ---------------- HELPERS ----------------

def clean_user(u: str):
    if not u:
        return None
    return str(u).replace("@", "").strip()

def mod_name(update: Update):
    u = update.effective_user.username
    return f"@{u}" if u else str(update.effective_user.id)

async def is_admin(update: Update):
    admins = await update.effective_chat.get_administrators()
    return any(a.user.id == update.effective_user.id for a in admins)

def add_v(uid, t, r, mod):
    cur.execute(
        "INSERT INTO violations(user_id,type,reason,created_at,moderator) VALUES (?,?,?,?,?)",
        (uid, t, r, datetime.now().isoformat(), mod),
    )
    conn.commit()

def get(uid, t):
    cur.execute(
        "SELECT id, reason, created_at FROM violations WHERE user_id=? AND type=? ORDER BY id ASC",
        (uid, t),
    )
    return cur.fetchall()

def delete_id(i):
    cur.execute("DELETE FROM violations WHERE id=?", (i,))
    conn.commit()

def delete_all(uid, t):
    cur.execute(
        "DELETE FROM violations WHERE user_id=? AND type=?",
        (uid, t),
    )
    conn.commit()

def cleanup():
    limit = datetime.now() - timedelta(days=30)
    cur.execute("DELETE FROM violations WHERE datetime(created_at) < ?", (limit.isoformat(),))
    conn.commit()

# ---------------- TRACK USERS ----------------

async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return

    u = update.effective_user

    uid = u.id
    username = f"@{u.username}" if u.username else f"id{u.id}"
    name = u.full_name

    cur.execute(
        "INSERT OR REPLACE INTO users VALUES (?,?,?)",
        (uid, username, name),
    )
    conn.commit()

# ---------------- RESOLVE ----------------

async def resolve(update, context):
    if context.args:
        return clean_user(context.args[0])

    if update.message and update.message.reply_to_message:
        return update.message.reply_to_message.from_user.id

    return None

# ---------------- ADME ----------------

async def adme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("☝️Ты не админ !")
        return

    u = update.effective_user

    uid = u.id
    username = f"@{u.username}" if u.username else f"id{u.id}"
    name = " ".join(context.args) if context.args else u.full_name

    cur.execute("INSERT OR REPLACE INTO users VALUES (?,?,?)", (uid, username, name))
    conn.commit()

    await update.message.reply_text(f"👤 Добавлен: {username}")

# ---------------- DELETE ----------------

async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("☝️Ты не админ !")
        return

    uid = await resolve(update, context)
    if not uid:
        return

    cur.execute("DELETE FROM users WHERE user_id=?", (uid,))
    cur.execute("DELETE FROM violations WHERE user_id=?", (uid,))
    conn.commit()

    await update.message.reply_text("❌ Пользователь удален")

# ---------------- PRED ----------------

async def pred(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("☝️Ты не админ !")
        return

    uid = await resolve(update, context)
    if not uid:
        return

    reason = " ".join(context.args[1:]) if len(context.args) > 1 else ""
    mod = mod_name(update)

    add_v(uid, "warn", reason, mod)

    text = f"<b>❗{uid} получает ⚠️ Предупреждение</b>\n⏳Снимается после исправления\n👺Модератор: {mod}"
    if reason:
        text += f"\n💬Причина: {reason}"

    await update.message.reply_text(text, parse_mode="HTML")

# ---------------- PROEB ----------------

async def proeb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("☝️Ты не админ !")
        return

    uid = await resolve(update, context)
    if not uid:
        return

    reason = " ".join(context.args[1:]) if len(context.args) > 1 else ""
    mod = mod_name(update)

    add_v(uid, "proeb", reason, mod)

    count = len(get(uid, "proeb"))

    text = f"<b>❗{uid} получает ⛔ Проеб ({count}/3)</b>\n⏳Снимается через 30 дней\n👺Модератор: {mod}"
    if reason:
        text += f"\n💬Причина: {reason}"

    await update.message.reply_text(text, parse_mode="HTML")

# ---------------- UNPRED ----------------

async def unpred(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("☝️Ты не админ !")
        return

    uid = await resolve(update, context)
    if not uid:
        return

    warns = get(uid, "warn")
    if not warns:
        return

    item = warns[-1] if len(context.args) == 1 else warns[int(context.args[1]) - 1]
    delete_id(item[0])

# ---------------- UNPROEB ----------------

async def unproeb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("☝️Ты не админ !")
        return

    uid = await resolve(update, context)
    if not uid:
        return

    proebs = get(uid, "proeb")
    if not proebs:
        return

    item = proebs[-1] if len(context.args) == 1 else proebs[int(context.args[1]) - 1]
    delete_id(item[0])

# ---------------- UN ALL ----------------

async def unpreds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("☝️Ты не админ !")
        return

    uid = await resolve(update, context)
    if not uid:
        return

    cnt = len(get(uid, "warn"))
    delete_all(uid, "warn")

    await update.message.reply_text(f"✅ снято ⚠️ ({cnt}/{cnt})")

async def unproebs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("☝️Ты не админ !")
        return

    uid = await resolve(update, context)
    if not uid:
        return

    cnt = len(get(uid, "proeb"))
    delete_all(uid, "proeb")

    await update.message.reply_text(f"✅ снято ⛔ ({cnt}/{cnt})")

# ---------------- STRONG ----------------

async def strong(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("☝️Ты не админ !")
        return

    uid = await resolve(update, context)
    if not uid:
        return

    warns = get(uid, "warn")
    if not warns:
        return

    item = warns[-1] if len(context.args) == 1 else warns[int(context.args[1]) - 1]
    delete_id(item[0])

    add_v(uid, "proeb", item[1], mod_name(update))

    await update.message.reply_text(f"<b>{uid} ⚠️ → ⛔</b>", parse_mode="HTML")

# ---------------- MYR ----------------

async def myr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = await resolve(update, context)
    if not uid:
        uid = update.effective_user.id

    cleanup()

    warns = get(uid, "warn")
    proebs = get(uid, "proeb")

    if not warns and not proebs:
        await update.message.reply_text("Замечания отсутствуют 🤗")
        return

    text = f"<b>❕Реестр пользователя {uid}</b>\n\n"

    for i, (_, r, d) in enumerate(proebs, 1):
        text += f"{i}. ⛔ {r}\nВыдан: {d}\n\n"

    for i, (_, r, d) in enumerate(warns, 1):
        text += f"{i}. ⚠️ {r}\nВыдан: {d}\n\n"

    await update.message.reply_text(text, parse_mode="HTML")

async def ree(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await myr(update, context)

# ---------------- RELIST ----------------

async def relist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("☝️Ты не админ !")
        return

    cur.execute("SELECT * FROM users")
    users = cur.fetchall()

    text = "<b>📋СПИСОК УЧАСТНИКОВ📋</b>\n\n"

    for _, uid, name in users:
        text += f"{name} | {uid}\n"

    await update.message.reply_text(text, parse_mode="HTML")

# ---------------- REESTR ----------------

async def reestr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("☝️Ты не админ !")
        return

    cur.execute("SELECT * FROM users")
    users = cur.fetchall()

    text = "<b>📛РЕЕСТР НАРУШЕНИЙ📛</b>\n\n"

    for _, uid, name in users:
        warns = get(uid, "warn")
        proebs = get(uid, "proeb")

        if not warns and not proebs:
            continue

        text += f"{name} | {uid}\n"

        for _, r, _ in proebs:
            text += f"⛔ {r}\n"

        for _, r, _ in warns:
            text += f"⚠️ {r}\n"

        text += "\n"

    await update.message.reply_text(text, parse_mode="HTML")

# ---------------- COMM ----------------

async def comm(update: Update, context: ContextTypes.DEFAULT_TYPE):

    admins = await update.effective_chat.get_administrators()
    is_admin_user = any(a.user.id == update.effective_user.id for a in admins)

    if is_admin_user:
        text = """
<b>📖 АДМИН КОМАНДЫ</b>

👤 /adme /del /relist
⚠️ /pred /proeb /strong
❌ /unpred /unproeb /unpreds /unproebs
📊 /reestr /myr /ree
"""
    else:
        text = """
<b>📖 ПОЛЬЗОВАТЕЛЬ</b>

👤 /adme — добавиться
📊 /myr — мой реестр
📊 /ree — реестр
📖 /comm — команды
"""

    await update.message.reply_text(text, parse_mode="HTML")

# ---------------- APP ----------------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("adme", adme))
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

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, track))

app.run_polling()
