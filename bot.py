# ---------------- ADME ----------------

async def adme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("☝️Ты не админ !")
        return

    u = update.effective_user

    uid = str(u.id)
    username = f"@{u.username}" if u.username else f"id{u.id}"
    name = u.full_name

    cur.execute("INSERT OR REPLACE INTO users VALUES (?,?)", (uid, name))
    conn.commit()

    await update.message.reply_text("👤 Добавлен")


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

    await update.message.reply_text("✏️ Обновлено")


# alias
async def ren(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await rename(update, context)


# ---------------- NOLIST ----------------

async def nolist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("☝️Ты не админ !")
        return

    cur.execute("SELECT user_id, name FROM users")
    db_users = cur.fetchall()

    db_set = set()
    for uid, name in db_users:
        if name:
            db_set.add(clean(name))

    chat_users = await update.effective_chat.get_members()

    missing = []

    try:
        async for member in update.effective_chat.get_members():
            u = member.user
            if not u:
                continue
            if not u.username:
                continue

            uname = "@" + u.username
            if uname not in db_set:
                missing.append(uname)

    except Exception:
        missing = []

    if not missing:
        await update.message.reply_text("✔️ Все в списке")
        return

    text = "✖️НЕ В СПИСКЕ✖️\n\n"
    for u in missing:
        text += f"{u}\n"

    await update.message.reply_text(text)


# alias
async def nl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await nolist(update, context)


# ---------------- COMM ----------------

async def comm(update: Update, context: ContextTypes.DEFAULT_TYPE):

    admins = await update.effective_chat.get_administrators()
    is_admin_user = any(a.user.id == update.effective_user.id for a in admins)

    if is_admin_user:
        text = """
/adme - добавить себя
/ren @user имя - изменить имя
/nolist - список не добавленных
/nl - алиас nolist
"""
    else:
        text = """
/adme - добавить себя
/comm - команды
"""

    await update.message.reply_text(text)
