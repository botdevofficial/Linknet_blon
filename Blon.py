import os
import re
import json
import time
import asyncio
import threading
from flask import Flask

from telegram import Bot, Update
from telegram.constants import ChatMemberStatus, ParseMode

# === Configuration ===
BOT_TOKEN = "7852112263:AAFdd4PBBDlFaHoqHzSicFMRKUA6VHMmTeg"
ALLOWED_LINK_PREFIX = "https://gpay.app.goo.gl/"
BLOCKLIST_FILE = "blocked_users.json"

bot = Bot(token=BOT_TOKEN)
app = Flask(__name__)

@app.route('/health')
def health():
    return "Bot is alive ✅", 200

# === Helpers ===
def load_blocked_usernames():
    if not os.path.exists(BLOCKLIST_FILE):
        return []
    with open(BLOCKLIST_FILE, "r") as f:
        return json.load(f)

def save_blocked_usernames(usernames):
    with open(BLOCKLIST_FILE, "w") as f:
        json.dump(usernames, f)

def extract_usernames(text):
    return [u.lower() for u in re.findall(r'@\w+', text or "")]

# === Command Handlers ===
async def handle_block(update: Update):
    chat = update.effective_chat
    user = update.effective_user
    member = await bot.get_chat_member(chat.id, user.id)

    if member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
        await bot.send_message(chat.id, "❌ Only admins can use /block.")
        return

    blocked = load_blocked_usernames()
    text = update.message.text or ""
    parts = text.split()

    to_block = None
    if len(parts) > 1 and parts[1].startswith("@"):
        to_block = parts[1].lower()
    elif update.message.reply_to_message:
        mentions = extract_usernames(update.message.reply_to_message.text)
        if mentions:
            to_block = mentions[0]

    if not to_block:
        await bot.send_message(chat.id, "Usage: /block @username or reply to a message containing @username.")
        return

    if to_block not in blocked:
        blocked.append(to_block)
        save_blocked_usernames(blocked)
        await bot.send_message(chat.id, f"✅ Blocked {to_block}")
    else:
        await bot.send_message(chat.id, f"🔒 {to_block} is already blocked.")

async def handle_unblock(update: Update):
    chat = update.effective_chat
    user = update.effective_user
    member = await bot.get_chat_member(chat.id, user.id)

    if member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
        await bot.send_message(chat.id, "❌ Only admins can use /unblock.")
        return

    parts = update.message.text.strip().split()
    if len(parts) < 2 or not parts[1].startswith("@"):
        await bot.send_message(chat.id, "Usage: /unblock @username")
        return

    to_unblock = parts[1].lower()
    blocked = load_blocked_usernames()

    if to_unblock in blocked:
        blocked.remove(to_unblock)
        save_blocked_usernames(blocked)
        await bot.send_message(chat.id, f"✅ Unblocked {to_unblock}")
    else:
        await bot.send_message(chat.id, f"ℹ️ {to_unblock} was not blocked.")

# === Message Filter ===
async def filter_message(update: Update):
    msg = update.message
    if not msg:
        return

    text = msg.text or ""
    blocked = load_blocked_usernames()

    links = re.findall(r'https?://\S+', text)
    if msg.entities:
        for entity in msg.entities:
            if entity.type == "url":
                links.append(text[entity.offset:entity.offset + entity.length])
            elif entity.type == "text_link":
                links.append(entity.url)
    links = list(set(links))

    for link in links:
        if not link.startswith(ALLOWED_LINK_PREFIX):
            try:
                await msg.delete()
                print("❌ Deleted disallowed link.")
                return
            except Exception as e:
                print("Delete failed:", e)
                return

    mentions = extract_usernames(text)
    for mention in mentions:
        if mention in blocked:
            try:
                await msg.delete()
                print(f"❌ Deleted blocked mention: {mention}")
                return
            except Exception as e:
                print("Delete failed:", e)
                return

# === Polling Loop ===
def run_polling():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    offset = None
    print("🤖 Bot polling started...")

    while True:
        try:
            updates = loop.run_until_complete(bot.get_updates(offset=offset, timeout=10))
            if updates:
                offset = updates[-1].update_id + 1

                for update in updates:
                    if not update.message or not update.message.text:
                        continue

                    text = update.message.text.strip()
                    if text.startswith("/block"):
                        loop.run_until_complete(handle_block(update))
                    elif text.startswith("/unblock"):
                        loop.run_until_complete(handle_unblock(update))
                    elif update.message.chat.type in ["group", "supergroup"]:
                        loop.run_until_complete(filter_message(update))

        except Exception as e:
            print("[Polling Error]", e)

        time.sleep(1)

# === Launch ===
if __name__ == '__main__':
    threading.Thread(target=run_polling, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)
