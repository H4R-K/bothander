import os
import asyncio
import imaplib
import email
from email.header import decode_header
import re
from aiohttp import web
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from motor.motor_asyncio import AsyncIOMotorClient
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
import telethon.errors

# ==========================================
# ⚙️ 1. SYSTEM ENVIRONMENT & SETUP
# ==========================================
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
OWNER_ID = int(os.getenv("OWNER_ID"))
API_ID = os.getenv("API_ID", "") 
API_HASH = os.getenv("API_HASH", "")

# Default HTML Parse Mode for Professional UI
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# Database Initializing
db_client = AsyncIOMotorClient(MONGO_URL)
db = db_client["TitanVault"]
gmails_collection = db["gmails"]
tg_collection = db["telegram_accounts"] 

temp_clients = {}

class TgLogin(StatesGroup):
    phone = State()
    code = State()
    password = State()

# ==========================================
# 🛡️ 2. CORE SECURITY & AUTHENTICATION
# ==========================================
async def is_owner(message: types.Message | types.CallbackQuery) -> bool:
    user_id = message.from_user.id
    if user_id != OWNER_ID:
        print(f"⚠️ UNAUTHORIZED ACCESS ATTEMPT | USER ID: {user_id}")
        return False
    return True

# ==========================================
# 📧 3. GMAIL ENGINE (IMAP)
# ==========================================
def fetch_latest_email_sync(email_address, app_password):
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(email_address, app_password)
        mail.select("inbox")
        status, messages = mail.search(None, "ALL")
        email_ids = messages[0].split()
        
        if not email_ids: return "📭 <i>Inbox is completely empty.</i>"
            
        latest_email_id = email_ids[-1]
        status, msg_data = mail.fetch(latest_email_id, "(RFC822)")
        
        response_text = ""
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                msg = email.message_from_bytes(response_part[1])
                subject, encoding = decode_header(msg["Subject"])[0]
                if isinstance(subject, bytes):
                    subject = subject.decode(encoding if encoding else "utf-8")
                
                response_text += f"📌 <b>SUBJECT:</b> <code>{subject}</code>\n"
                
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode()
                            break
                else:
                    body = msg.get_payload(decode=True).decode()
                
                otps = re.findall(r'\b\d{4,8}\b', body)
                if otps:
                    response_text += f"🔑 <b>SYSTEM DETECTED OTP:</b> <code>{', '.join(otps[:3])}</code>\n"
                else:
                    response_text += "⚠️ <i>No direct OTP detected. Check body below.</i>\n"
                
                response_text += f"\n📝 <b>MESSAGE BODY:</b>\n<i>{body[:250]}...</i>"
                
        mail.logout()
        return response_text
    
    except imaplib.IMAP4.error:
        return "❌ <b>AUTH FAILED</b> | App password or Email is incorrect."
    except Exception as e:
        return f"❌ <b>SYSTEM ERROR:</b> {e}"

# ==========================================
# 🎛️ 4. INTERACTIVE MAIN MENU (START COMMAND)
# ==========================================
@dp.message(Command("start"))
async def start_command(message: types.Message):
    if not await is_owner(message): return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📧 Vault: Gmails", callback_data="cb_list_gmails"),
         InlineKeyboardButton(text="📱 Vault: Telegrams", callback_data="cb_list_tgs")],
        [InlineKeyboardButton(text="ℹ️ How to add accounts?", callback_data="cb_help")]
    ])
    
    welcome_text = (
        "🛡️ <b>TITAN OS [CORE ACTIVE]</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Welcome Boss. The encrypted OTP Vault is online and ready for commands.\n\n"
        "<i>Select a vault component below or use system commands directly.</i>"
    )
    await message.answer(welcome_text, reply_markup=keyboard)

# --- INLINE BUTTON HANDLERS ---
@dp.callback_query(F.data == "cb_list_gmails")
async def cb_gmail_list(call: CallbackQuery):
    if not await is_owner(call): return
    accounts = await gmails_collection.find({}).to_list(length=100)
    if not accounts:
        await call.message.edit_text("📭 <b>VAULT [GMAIL]:</b> No accounts registered.")
        return
    response = "📧 <b>TITAN VAULT | GMAIL ACCOUNTS</b>\n━━━━━━━━━━━━━━━━━━━━\n"
    for acc in accounts: response += f"🔹 <b>{acc['alias']}</b> ➾ <code>{acc['email']}</code>\n"
    response += "\n<i>To fetch OTP:</i> <code>/getmail [alias]</code>"
    await call.message.edit_text(response)

@dp.callback_query(F.data == "cb_list_tgs")
async def cb_tg_list(call: CallbackQuery):
    if not await is_owner(call): return
    accounts = await tg_collection.find({}).to_list(length=100)
    if not accounts:
        await call.message.edit_text("📭 <b>VAULT [TELEGRAM]:</b> No accounts registered.")
        return
    response = "📱 <b>TITAN VAULT | TELEGRAM ACCOUNTS</b>\n━━━━━━━━━━━━━━━━━━━━\n"
    for acc in accounts: response += f"🔹 <code>{acc['phone']}</code>\n"
    response += "\n<i>To fetch OTP:</i> <code>/gettg [phone]</code>"
    await call.message.edit_text(response)

@dp.callback_query(F.data == "cb_help")
async def cb_help_menu(call: CallbackQuery):
    if not await is_owner(call): return
    help_text = (
        "🛠️ <b>SYSTEM COMMAND MANUAL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>[GMAIL INTEGRATION]</b>\n"
        "<code>/addmail [alias] [email] [app_password]</code>\n"
        "<code>/getmail [alias]</code>\n"
        "<code>/listmails</code>\n\n"
        "<b>[TELEGRAM INTEGRATION]</b>\n"
        "<code>/addtg</code> <i>(Interactive Setup)</i>\n"
        "<code>/gettg [phone]</code>\n"
        "<code>/listtg</code>\n"
    )
    await call.message.edit_text(help_text)

# ==========================================
# 📧 5. GMAIL TERMINAL COMMANDS
# ==========================================
@dp.message(Command("addmail"))
async def add_mail_command(message: types.Message):
    if not await is_owner(message): return
    args = message.text.split()
    if len(args) != 4:
        await message.answer("⚠️ <b>INVALID SYNTAX</b>\nUsage: <code>/addmail [alias] [email] [app_password]</code>")
        return
    alias, email_id, app_pass = args[1], args[2], args[3]
    try:
        existing = await gmails_collection.find_one({"alias": alias})
        if existing:
            await message.answer(f"❌ <b>CONFLICT:</b> Alias '<code>{alias}</code>' already exists in the Vault.")
            return
        await gmails_collection.insert_one({"alias": alias, "email": email_id, "app_password": app_pass})
        await message.answer(f"✅ <b>VAULT UPDATED</b>\nEmail <code>{email_id}</code> is securely linked as [<b>{alias}</b>].")
    except Exception as e:
        await message.answer(f"❌ <b>DATABASE ERROR:</b> {e}")

@dp.message(Command("listmails"))
async def list_mails_command(message: types.Message):
    if not await is_owner(message): return
    accounts = await gmails_collection.find({}).to_list(length=100)
    if not accounts:
        await message.answer("📭 <b>VAULT [GMAIL]:</b> No accounts registered.")
        return
    response = "📧 <b>TITAN VAULT | GMAIL ACCOUNTS</b>\n━━━━━━━━━━━━━━━━━━━━\n"
    for acc in accounts: response += f"🔹 <b>{acc['alias']}</b> ➾ <code>{acc['email']}</code>\n"
    await message.answer(response)

@dp.message(Command("getmail"))
async def get_mail_command(message: types.Message):
    if not await is_owner(message): return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("⚠️ <b>INVALID SYNTAX</b>\nUsage: <code>/getmail [alias]</code>")
        return
    alias = args[1]
    account = await gmails_collection.find_one({"alias": alias})
    if not account:
        await message.answer(f"❌ <b>NOT FOUND:</b> Alias '<code>{alias}</code>' does not exist in the Vault.")
        return
    
    wait_msg = await message.answer("⏳ <i>[SYSTEM SCANNING] Accessing encrypted inbox...</i>")
    result = await asyncio.to_thread(fetch_latest_email_sync, account["email"], account["app_password"])
    
    final_response = (
        f"🛡️ <b>GMAIL INTERCEPT | [{alias.upper()}]</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{result}"
    )
    await wait_msg.edit_text(final_response)

# ==========================================
# 📱 6. TELEGRAM TERMINAL COMMANDS
# ==========================================
@dp.message(Command("listtg"))
async def list_tg_command(message: types.Message):
    if not await is_owner(message): return
    accounts = await tg_collection.find({}).to_list(length=100)
    if not accounts:
        await message.answer("📭 <b>VAULT [TELEGRAM]:</b> No accounts registered.")
        return
    response = "📱 <b>TITAN VAULT | TELEGRAM ACCOUNTS</b>\n━━━━━━━━━━━━━━━━━━━━\n"
    for acc in accounts: response += f"🔹 <code>{acc['phone']}</code>\n"
    await message.answer(response)

@dp.message(Command("gettg"))
async def get_tg_command(message: types.Message):
    if not await is_owner(message): return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("⚠️ <b>INVALID SYNTAX</b>\nUsage: <code>/gettg [phone]</code>")
        return
    phone = args[1]
    account = await tg_collection.find_one({"phone": phone})
    if not account:
        await message.answer(f"❌ <b>NOT FOUND:</b> Phone '<code>{phone}</code>' does not exist in the Vault.")
        return
    
    wait_msg = await message.answer("⏳ <i>[SYSTEM SCANNING] Communicating with Telegram core servers...</i>")
    session_str = account.get("session_string")
    
    try:
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH, device_model="Titan OTP Vault", system_version="Core 1.0", app_version="TitanBot v2.0")
        await client.connect()
        if not await client.is_user_authorized():
            await wait_msg.edit_text("❌ <b>SESSION DEAD:</b> Token expired. Re-authenticate using <code>/addtg</code>.")
            await client.disconnect()
            return
            
        messages = await client.get_messages(777000, limit=2)
        if not messages:
            await wait_msg.edit_text(f"📭 <b>CLEAN:</b> No official messages found for <code>{phone}</code>.")
        else:
            response = (
                f"🛡️ <b>TELEGRAM INTERCEPT | {phone}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
            )
            for msg in messages:
                response += f"💬 <b>[OFFICIAL MESSAGE]:</b>\n<code>{msg.text}</code>\n"
                response += "▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
            await wait_msg.edit_text(response)
        await client.disconnect()
    except Exception as e:
        await wait_msg.edit_text(f"❌ <b>SYSTEM ERROR:</b> {e}")

# ==========================================
# 🔐 7. ADVANCED FSM: TG AUTHENTICATION
# ==========================================
@dp.message(Command("addtg"))
async def add_tg_start(message: types.Message, state: FSMContext):
    if not await is_owner(message): return
    await message.answer(
        "📱 <b>[TELEGRAM SETUP INITIALIZED]</b>\n"
        "Enter the Target Phone Number with Country Code.\n"
        "<i>Format: +919876543210</i>"
    )
    await state.set_state(TgLogin.phone)

@dp.message(TgLogin.phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    await state.update_data(phone=phone)
    wait_msg = await message.answer("⏳ <i>Establishing encrypted connection with Telegram...</i>")
    
    client = TelegramClient(StringSession(), API_ID, API_HASH, device_model="Titan OTP Vault", system_version="Core 1.0", app_version="TitanBot v2.0")
    await client.connect()
    try:
        code_request = await client.send_code_request(phone)
        temp_clients[message.from_user.id] = {"client": client, "phone_code_hash": code_request.phone_code_hash}
        await wait_msg.edit_text(
            "✅ <b>PACKET SENT SUCCESSFULLY</b>\n\n"
            "An official code has been delivered to your active Telegram App.\n"
            "⚠️ <b>ANTI-SPAM RULE:</b> Enter the code with spaces! (e.g., <code>1 2 3 4 5</code>)"
        )
        await state.set_state(TgLogin.code)
    except Exception as e:
        await wait_msg.edit_text(f"❌ <b>CONNECTION FAILED:</b> {e}\n<i>Please verify number and restart /addtg</i>")
        await state.clear()

@dp.message(TgLogin.code)
async def process_code(message: types.Message, state: FSMContext):
    code = message.text.strip().replace(" ", "")
    data = await state.get_data()
    phone = data['phone']
    client_data = temp_clients.get(message.from_user.id)
    
    if not client_data:
        await message.answer("❌ <b>SESSION TIMEOUT:</b> Process killed. Start /addtg again.")
        await state.clear()
        return
        
    client, phone_code_hash = client_data["client"], client_data["phone_code_hash"]
    wait_msg = await message.answer("⏳ <i>Verifying authentication matrix...</i>")
    
    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        session_string = client.session.save()
        await tg_collection.insert_one({"phone": phone, "session_string": session_string})
        await wait_msg.edit_text(f"✅ <b>[VAULT SECURED]</b>\nTelegram account <code>{phone}</code> successfully encrypted & saved.")
        await client.disconnect()
        del temp_clients[message.from_user.id]
        await state.clear()
    except telethon.errors.SessionPasswordNeededError:
        await wait_msg.edit_text("🔒 <b>[2FA DETECTED]</b> Account is protected by a Cloud Password.\nPlease enter your 2FA password:")
        await state.set_state(TgLogin.password)
    except Exception as e:
        await wait_msg.edit_text(f"❌ <b>AUTH REJECTED:</b> {e}\n<i>Try /addtg again.</i>")
        await client.disconnect()
        await state.clear()

@dp.message(TgLogin.password)
async def process_password(message: types.Message, state: FSMContext):
    password = message.text.strip()
    data = await state.get_data()
    phone = data['phone']
    client = temp_clients.get(message.from_user.id)["client"]
    wait_msg = await message.answer("⏳ <i>Decrypting 2-Step Verification...</i>")
    
    try:
        await client.sign_in(password=password)
        session_string = client.session.save()
        await tg_collection.insert_one({"phone": phone, "session_string": session_string})
        await wait_msg.edit_text(f"✅ <b>[VAULT SECURED]</b>\nTelegram account <code>{phone}</code> successfully encrypted & saved (2FA Passed).")
        await client.disconnect()
        del temp_clients[message.from_user.id]
        await state.clear()
    except Exception as e:
        await wait_msg.edit_text(f"❌ <b>PASSWORD REJECTED:</b> {e}\n<i>Wrong password. Restart /addtg.</i>")
        await client.disconnect()
        await state.clear()

# ==========================================
# 🔄 8. TELEGRAM KEEP-ALIVE [GHOST PING]
# ==========================================
async def keep_sessions_alive():
    while True:
        try:
            print("[SYSTEM] 🔄 Initiating Ghost Ping for all Telegram Sessions...")
            accounts = await tg_collection.find({}).to_list(length=100)
            for acc in accounts:
                session_str, phone = acc.get("session_string"), acc.get("phone")
                if session_str:
                    client = TelegramClient(StringSession(session_str), API_ID, API_HASH, device_model="Titan OTP Vault", system_version="Core 1.0", app_version="TitanBot v2.0")
                    await client.connect()
                    if await client.is_user_authorized():
                        await client.get_me()
                        print(f"[SYSTEM] ✅ Keep-alive success for: {phone}")
                    else:
                        print(f"[SYSTEM] ⚠️ Dead token detected for: {phone}")
                    await client.disconnect()
        except Exception as e:
            print(f"[SYSTEM] ❌ Keep-Alive Exception: {e}")
            pass
        await asyncio.sleep(43200) # Ping every 12 hours

# ==========================================
# 🌐 9. RENDER WEB SERVER & ENGINE START
# ==========================================
async def handle_ping(request):
    return web.Response(text="TITAN OS: The Vault is active and listening.")

async def web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"[SYSTEM] 🌐 Ghost Web Server initialized on PORT {port}")

async def main():
    print("[SYSTEM] 🚀 Booting up Titan OS...")
    asyncio.create_task(web_server())
    asyncio.create_task(keep_sessions_alive())
    print("[SYSTEM] 🛡️ System fully operational. Bot is now polling.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
