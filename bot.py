import os
import asyncio
import imaplib
import email
from email.header import decode_header
import re
from aiohttp import web
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from motor.motor_asyncio import AsyncIOMotorClient
import logging
logging.basicConfig(level=logging.INFO) # <-- Yeh line add karein

# 1. Environment variables load karein
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
OWNER_ID = int(os.getenv("OWNER_ID"))
API_ID = os.getenv("API_ID", "") 
API_HASH = os.getenv("API_HASH", "")

# 2. Bot, Dispatcher aur Database setup
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# MongoDB se connect karein
db_client = AsyncIOMotorClient(MONGO_URL)
db = db_client["OTP_Vault"]
gmails_collection = db["gmails"]

# ==========================================
# 🔒 OWNER CHECK (Security Layer)
# ==========================================
# Yeh function check karega ki message aapne bheja hai ya kisi aur ne
async def is_owner(message: types.Message) -> bool:
    if message.from_user.id != OWNER_ID:
        # Agar koi aur user start karega, bot usko block/ignore kar dega
        print(f"Unauthorized access alert! User ID: {message.from_user.id}")
        return False
    return True

# ==========================================
# 📧 GMAIL IMAP FETCHER (Background Worker)
# ==========================================
def fetch_latest_email_sync(email_address, app_password):
    try:
        # Gmail se connect karein
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(email_address, app_password)
        mail.select("inbox")
        
        # Sabse latest mail (ALL me se aakhiri) search karein
        status, messages = mail.search(None, "ALL")
        email_ids = messages[0].split()
        
        if not email_ids:
            return "📭 Aapka Inbox bilkul khali hai."
            
        latest_email_id = email_ids[-1]
        status, msg_data = mail.fetch(latest_email_id, "(RFC822)")
        
        response_text = ""
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                msg = email.message_from_bytes(response_part[1])
                
                # 1. Subject Decode Karein
                subject, encoding = decode_header(msg["Subject"])[0]
                if isinstance(subject, bytes):
                    subject = subject.decode(encoding if encoding else "utf-8")
                
                response_text += f"📌 **Subject:** {subject}\n\n"
                
                # 2. Body Extract Karein (Plain Text)
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode()
                            break
                else:
                    body = msg.get_payload(decode=True).decode()
                
                # 3. OTP Extract Karein (Regex: 4-8 digit ka number dhundhega)
                otps = re.findall(r'\b\d{4,8}\b', body)
                if otps:
                    response_text += f"🔑 **Possible OTP(s):** `{', '.join(otps[:3])}`\n\n"
                else:
                    response_text += "⚠️ Koi direct OTP detect nahi hua. Niche detail dekhein:\n\n"
                    
                # Message ka chota hissa dikhayein
                response_text += f"📝 **Message:**\n{body[:250]}..."
                
        mail.logout()
        return response_text
    
    except imaplib.IMAP4.error:
        return "❌ Login Failed! App password ya Email galat hai."
    except Exception as e:
        return f"❌ Error: {e}"


# ==========================================
# 🤖 BOT COMMANDS
# ==========================================

@dp.message(Command("start"))
async def start_command(message: types.Message):
    if not await is_owner(message): return
    
    welcome_text = (
        "👋 Welcome Boss!\n\n"
        "Aapka Personal OTP Vault active hai.\n"
        "Comamnds:\n"
        "/addmail <alias> <email> <password> - Naya mail add karein\n"
        "/listmails - Save kiye mails dekhein\n"
        "/getmail <alias> - OTP/Latest mail dekhein"
    )
    await message.answer(welcome_text)

@dp.message(Command("addmail"))
async def add_mail_command(message: types.Message):
    if not await is_owner(message): return
    
    # User message ko split karke data nikalna
    # Example command format: /addmail gaming pro-gamer@gmail.com app_password
    args = message.text.split()
    
    if len(args) != 4:
        await message.answer("⚠️ Sahi format use karein:\n`/addmail <alias> <email> <app_password>`")
        return
        
    alias, email_id, app_pass = args[1], args[2], args[3]
    
    # MongoDB me data insert karna
    try:
        # Check karna ki alias pehle se exist toh nahi karta
        existing = await gmails_collection.find_one({"alias": alias})
        if existing:
            await message.answer(f"❌ '{alias}' naam se pehle hi ek mail save hai. Dusra naam use karein.")
            return

        new_account = {
            "alias": alias,
            "email": email_id,
            "app_password": app_pass
        }
        await gmails_collection.insert_one(new_account)
        await message.answer(f"✅ Success! **{email_id}** as '{alias}' save ho gaya hai.")
    except Exception as e:
        await message.answer(f"❌ Database Error: {e}")

@dp.message(Command("listmails"))
async def list_mails_command(message: types.Message):
    if not await is_owner(message): return
    
    cursor = gmails_collection.find({})
    accounts = await cursor.to_list(length=100)
    
    if not accounts:
        await message.answer("📭 Abhi tak koi mail save nahi hai.")
        return
        
    response = "📂 **Aapke Saved Gmail Accounts:**\n\n"
    for acc in accounts:
        response += f"🔹 **{acc['alias']}** - `{acc['email']}`\n"
        
    await message.answer(response)

@dp.message(Command("getmail"))
async def get_mail_command(message: types.Message):
    if not await is_owner(message): return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("⚠️ Sahi format: `/getmail <alias>`\nExample: `/getmail main`")
        return
        
    alias = args[1]
    
    # 1. Database se account dhundhein
    account = await gmails_collection.find_one({"alias": alias})
    
    if not account:
        await message.answer(f"❌ '{alias}' naam ka koi account nahi mila. Pehle `/listmails` check karein.")
        return
        
    # 2. Loading message bhejein
    wait_msg = await message.answer("⏳ Inbox check kar raha hoon... kripya wait karein.")
    
    # 3. Background thread me IMAP function chalayein
    email_address = account["email"]
    app_password = account["app_password"]
    
    result = await asyncio.to_thread(fetch_latest_email_sync, email_address, app_password)
    
    # 4. Result Edit karke dikhayein
    await wait_msg.edit_text(f"📧 **Alias:** {alias}\n\n{result}")

# ==========================================
# 🌐 DUMMY WEB SERVER (For Render Port Binding)
# ==========================================
async def handle_ping(request):
    return web.Response(text="Bot is Live and Running!")

async def web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render automatic $PORT environment variable deta hai
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Dummy web server started on port {port}")

# ==========================================
# 🚀 BOT RUNNER
# ==========================================
async def main():
    print("Bot is starting...")
    # 1. Background me Dummy Web Server start karein Render ke liye
    asyncio.create_task(web_server())
    
    # 2. Telegram Bot start karein
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
