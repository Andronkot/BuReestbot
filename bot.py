import os
import sqlite3
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

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

def clean_user(uid: str):
    return uid.replace("@", "").replace("@@", "").strip()

async def is_admin(update: Update):
    admins = await update.effective_chat.get_administrators()
    return any(a.user.id == update.effective_user.id for a in admins)

def add_v(uid, t, reason, mod):
    cur.execute(
        "INSERT INTO violations(user_id,type,reason,created_at,moderator) VALUES (?,?,?,?,?)",
        (uid, t, reason, datetime.now().isoformat(), mod)
    )
    conn.commit()

def get_all(uid, t):
    cur.execute("SELECT id, reason, created_at FROM violations WHERE user_id=? AND type=? ORDER BY id ASC", (uid, t))
    return cur.fetchall()

def get_all_mix(uid):
    cur.execute("SELECT id, type, reason, created_at FROM violations WHERE user_id=? ORDER BY id ASC", (uid,))
    return cur.fetchall()

def delete_by_id(vid):
    cur.execute("DELETE FROM violations WHERE id=?", (vid,))
    conn.commit()

def delete_all(uid, t):
    cur.execute("DELETE FROM violations WHERE user_id=? AND type=?", (uid, t))
    conn.commit()

# ---------------- COMMANDS ----------------

# /add @user name
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    if len(context.args) < 2:
        return

    uid = clean_user(context.args[0])
    name = " ".join(context.args[1:])

    cur.execute("INSERT OR REPLACE INTO users VALUES (?,?)", (uid, name))
    conn.commit()

    await update.message.reply_text("👤 Пользователь добавлен")


# /del @user
async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = clean_user(context.args[0])

    cur.execute("DELETE FROM users WHERE user_id=?", (uid,))
    cur.execute("DELETE FROM violations WHERE user_id=?", (uid,))
    conn.commit()

    await update.message.reply_text("❌ Пользователь удален")


# ---------------- PRED ----------------

async def pred(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = clean_user(context.args[0])
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else ""

    mod = f"@{update.effective_user.username}" if update.effective_user.username else str(update.effective_user.id)

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

    uid = clean_user(context.args[0])
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else ""

    mod = f"@{update.effective_user.username}" if update.effective_user.username else str(update.effective_user.id)

    add_v(uid, "proeb", reason, mod)

    count = len(get_all(uid, "proeb"))

    text = f"""❗@{uid} получает ⛔ Проеб ({count}/3)
⏳Будет снято через 30 дней
👺Модератор: {mod}"""

    if reason:
        text += f"\n💬Причина: {reason}"

    await update.message.reply_text(text)

    if count >= 3:
        await update.message.reply_text(f"🚨 @{uid} достиг максимального числа ⛔Проебов (3/3) !")


# ---------------- UNPRED ----------------

async def unpred(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = clean_user(context.args[0])
    all_w = get_all(uid, "warn")

    if not all_w:
        return

    if len(context.args) == 1:
        delete_by_id(all_w[-1][0])
    else:
        idx = int(context.args[1]) - 1
        if 0 <= idx < len(all_w):
            delete_by_id(all_w[idx][0])

    await update.message.reply_text("")


async def unproeb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = clean_user(context.args[0])
    all_p = get_all(uid, "proeb")

    if not all_p:
        return

    if len(context.args) == 1:
        delete_by_id(all_p[-1][0])
    else:
        idx = int(context.args[1]) - 1
        if 0 <= idx < len(all_p):
            delete_by_id(all_p[idx][0])

    await update.message.reply_text("")


# ---------------- UNPRED ALL ----------------

async def unpreds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = clean_user(context.args[0])
    all_w = len(get_all(uid, "warn"))

    delete_all(uid, "warn")

    await update.message.reply_text(
        f"✅С пользователя @{uid} были сняты все ⚠️предупреждения ({all_w}/{all_w})"
    )


# ---------------- UNPROEBS ALL ----------------

async def unproebs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = clean_user(context.args[0])
    all_p = len(get_all(uid, "proeb"))

    delete_all(uid, "proeb")

    await update.message.reply_text(
        f"✅С пользователя @{uid} были сняты все ⛔проебы ({all_p}/{all_p})"
    )


# ---------------- STRONG ----------------

async def strong(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = clean_user(context.args[0])
    idx = int(context.args[1]) - 1

    warns = get_all(uid, "warn")

    if idx < 0 or idx >= len(warns):
        return

    vid, reason, _ = warns[idx]

    delete_by_id(vid)
    add_v(uid, "proeb", reason, f"@{update.effective_user.username}")

    await update.message.reply_text(
        f"{uid} ⚠️ Предупреждение теперь ⛔ Проеб\n"
        f"Не игнорируй предупреждения !!!"
    )


# ---------------- RELIST ----------------

async def relist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    cur.execute("SELECT * FROM users")
    users = cur.fetchall()

    text = "📋СПИСОК УЧАСТНИКОВ📋\n\n"

    for uid, name in users:
        text += f"{name} | @{uid}\n"

    await update.message.reply_text(text)


# ---------------- REESTR ----------------

async def reestr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    cur.execute("SELECT * FROM users")
    users = cur.fetchall()

    text = "📛РЕЕСТР НАРУШЕНИЙ📛\n\n"

    for uid, name in users:
        warns = get_all(uid, "warn")
        proebs = get_all(uid, "proeb")

        if not warns and not proebs:
            continue

        text += f"{name} | @{uid}\n"

        for _, r, _ in proebs:
            text += f"⛔{r or ' '} ⛔ "

        text += "\n"

        for _, r, _ in warns:
            text += f"⚠️{r or ' '} ⚠️ "

        text += "\n\n"

    await update.message.reply_text(text)


# ---------------- APP ----------------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("add", add))
app.add_handler(CommandHandler("del", delete))
app.add_handler(CommandHandler("pred", pred))
app.add_handler(CommandHandler("proeb", proeb))
app.add_handler(CommandHandler("unpred", unpred))
app.add_handler(CommandHandler("unproeb", unproeb))
app.add_handler(CommandHandler("unpreds", unpreds))
app.add_handler(CommandHandler("unproebs", unproebs))
app.add_handler(CommandHandler("strong", strong))
app.add_handler(CommandHandler("relist", relist))
app.add_handler(CommandHandler("reestr", reestr))

app.run_polling()
