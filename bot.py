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

def clean(u):
    return u.replace("@", "").strip()


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


# ---------------- CORE FIX (ЕДИНАЯ ЛОГИКА ИНДЕКСОВ) ----------------

def resolve_index(args, items_len):
    """
    ЕДИНЫЙ ПРАВИЛЬНЫЙ РАЗБОР ИНДЕКСА
    """
    if len(args) == 1:
        return items_len - 1  # последний

    try:
        idx = int(args[1]) - 1
        if idx < 0:
            return items_len - 1
        if idx >= items_len:
            return items_len - 1
        return idx
    except:
        return items_len - 1


def mod_name(update):
    u = update.effective_user.username
    return f"@{u}" if u else str(update.effective_user.id)


# ---------------- ADD / DELETE ----------------

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = clean(context.args[0])
    name = " ".join(context.args[1:])

    cur.execute("INSERT OR REPLACE INTO users VALUES (?,?)", (uid, name))
    conn.commit()

    await update.message.reply_text("👤 Пользователь добавлен")


async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = clean(context.args[0])

    cur.execute("DELETE FROM users WHERE user_id=?", (uid,))
    cur.execute("DELETE FROM violations WHERE user_id=?", (uid,))
    conn.commit()

    await update.message.reply_text("❌ Пользователь удален")


# ---------------- PRED (ФИКС) ----------------

async def pred(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = clean(context.args[0])
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else ""

    mod = mod_name(update)

    add_v(uid, "warn", reason, mod)

    await update.message.reply_text(
        f"""❗{uid} получает ⚠️ Предупреждение
⏳Будет снято когда исправишься
👺Модератор: {mod}"""
        + (f"\n💬Причина: {reason}" if reason else "")
    )


# ---------------- PROEB (ФИКС) ----------------

async def proeb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = clean(context.args[0])
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else ""

    mod = mod_name(update)

    add_v(uid, "proeb", reason, mod)

    count = len(get(uid, "proeb"))

    await update.message.reply_text(
        f"""❗{uid} получает ⛔ Проеб ({count}/3)
⏳Будет снято через 30 дней
👺Модератор: {mod}"""
        + (f"\n💬Причина: {reason}" if reason else "")
    )

    if count >= 3:
        await update.message.reply_text(
            f"🚨 {uid} достиг максимального числа ⛔Проебов (3/3) !"
        )


# ---------------- UNPRED (ФИКС) ----------------

async def unpred(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = clean(context.args[0])
    warns = get(uid, "warn")

    if not warns:
        return

    idx = resolve_index(context.args, len(warns))
    vid = warns[idx][0]

    delete_by_id(vid)

    await update.message.reply_text("")


# ---------------- UNPROEB (ФИКС) ----------------

async def unproeb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = clean(context.args[0])
    proebs = get(uid, "proeb")

    if not proebs:
        return

    idx = resolve_index(context.args, len(proebs))
    vid = proebs[idx][0]

    delete_by_id(vid)

    await update.message.reply_text("")


# ---------------- UN ALL ----------------

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
        return

    uid = clean(context.args[0])
    cnt = len(get(uid, "proeb"))

    delete_all(uid, "proeb")

    await update.message.reply_text(
        f"С пользователя {uid} были сняты все ⛔проебы ({cnt}/{cnt})"
    )


# ---------------- STRONG (НЕ ТРОГАЕМ ЛОГИКУ, ТОЛЬКО СТАБИЛИЗАЦИЯ) ----------------

async def strong(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    uid = clean(context.args[0])
    warns = get(uid, "warn")

    if not warns:
        return

    idx = resolve_index(context.args, len(warns))
    vid, reason = warns[idx]

    delete_by_id(vid)
    add_v(uid, "proeb", reason, mod_name(update))

    await update.message.reply_text(
        f"{uid} ⚠️ Предупреждение теперь ⛔ Проеб\nНе игнорируй предупреждения !!!"
    )


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

app.run_polling()
