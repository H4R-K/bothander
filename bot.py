import os
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from motor.motor_asyncio import AsyncIOMotorClient

# 1. Environment variables load karein
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
OWNER_ID = int(os.getenv("OWNER_ID"))

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
