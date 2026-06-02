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

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# Database Initializing (Fixed back to OTP_Vault)
db_client = AsyncIOMotorClient(MONGO_URL)
db = db_client["OTP_Vault"]
gmails_collection = db["gmails"]
tg_collection = db["telegram_accounts"] 

temp_clients = {}

# ==========================================
# 🛡️ 2. STATES & SECURITY
# ==========================================
class TgLogin(StatesGroup):
    phone = State()
    code = State()
    password = State()

class GmailLogin(StatesGroup):
    alias = State()
    email = State()
    password = State()

async def is_owner(event) -> bool:
    if event.from_user.id != OWNER_ID:
        return False
    return True

# ==========================================
# 🎛️ 3. KEYBOARD MENUS (UI GENERATORS)
# ==========================================
def get_home_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📧 GMAIL VAULT", callback_data="menu_gmail")],
        [InlineKeyboardButton(text="📱 TELEGRAM VAULT", callback_data="menu_tg")],
        [InlineKeyboardButton(text="🔐 System Status", callback_data="menu_status")]
    ])

def get_gmail_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add New Gmail", callback_data="g_add")],
        [InlineKeyboardButton(text="🔑 Fetch OTP", callback_data="g_fetch_menu")],
        [InlineKeyboardButton(text="📂 List Saved Gmails", callback_data="g_list")],
        [InlineKeyboardButton(text="🏠 Home", callback_data="menu_home")]
    ])

def get_tg_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add New Telegram", callback_data="t_add")],
        [InlineKeyboardButton(text="🔑 Fetch OTP", callback_data="t_fetch_menu")],
        [InlineKeyboardButton(text="📂 List Saved Telegrams", callback_data="t_list")],
        [InlineKeyboardButton(text="🏠 Home", callback_data="menu_home")]
    ])

def get_back_home_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Back to Home", callback_data="menu_home")]
    ])

# ==========================================
# 🚀 4. MAIN MENU & NAVIGATION
# ==========================================
@dp.message(Command("start"))
async def start_command(message: types.Message, state: FSMContext):
    if not await is_owner(message): return
    await state.clear() # Clear any stuck FSM process
    
    welcome_text = (
        "🛡️ <b>TITAN OS [INTERACTIVE UI]</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Welcome Boss. The encrypted OTP Vault is online.\n"
        "<i>Select an option below to manage your assets:</i>"
    )
    await message.answer(welcome_text, reply_markup=get_home_keyboard())

@dp.callback_query(F.data == "menu_home")
async def cb_home(call: CallbackQuery, state: FSMContext):
    if not await is_owner(call): return
    await state.clear()
    text = "🛡️ <b>TITAN OS [CORE MENU]</b>\n━━━━━━━━━━━━━━━━━━━━\n<i>Select a vault component:</i>"
    await call.message.edit_text(text, reply_markup=get_home_keyboard())

@dp.callback_query(F.data == "menu_gmail")
async def cb_gmail_menu(call: CallbackQuery):
    if not await is_owner(call): return
    text = "📧 <b>GMAIL CONTROL CENTER</b>\n━━━━━━━━━━━━━━━━━━━━\n<i>Choose an action:</i>"
    await call.message.edit_text(text, reply_markup=get_gmail_keyboard())

@dp.callback_query(F.data == "menu_tg")
async def cb_tg_menu(call: CallbackQuery):
    if not await is_owner(call): return
    text = "📱 <b>TELEGRAM CONTROL CENTER</b>\n━━━━━━━━━━━━━━━━━━━━\n<i>Choose an action:</i>"
    await call.message.edit_text(text, reply_markup=get_tg_keyboard())

@dp.callback_query(F.data == "menu_status")
async def cb_status(call: CallbackQuery):
    if not await is_owner(call): return
    g_count = await gmails_collection.count_documents({})
    t_count = await tg_collection.count_documents({})
    text = (
        "📊 <b>SYSTEM STATUS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📧 Saved Gmails: <b>{g_count}</b>\n"
        f"📱 Saved Telegrams: <b>{t_count}</b>\n"
        "✅ Ghost Server: <b>Online</b>\n"
        "✅ Keep-Alive Ping: <b>Active</b>"
    )
    await call.message.edit_text(text, reply_markup=get_back_home_keyboard())

# ==========================================
# 📧 5. GMAIL OPERATIONS (FSM & DYNAMIC UI)
# ==========================================
@dp.callback_query(F.data == "g_list")
async def cb_g_list(call: CallbackQuery):
    if not await is_owner(call): return
    accounts = await gmails_collection.find({}).to_list(length=100)
    if not accounts:
        await call.message.edit_text("📭 <b>VAULT:</b> No Gmails registered.", reply_markup=get_gmail_keyboard())
        return
    res = "📧 <b>SAVED GMAIL ACCOUNTS</b>\n━━━━━━━━━━━━━━━━━━━━\n"
    for acc in accounts: res += f"🔹 <b>{acc['alias']}</b> ➾ <code>{acc['email']}</code>\n"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="menu_gmail")]])
    await call.message.edit_text(res, reply_markup=keyboard)

@dp.callback_query(F.data == "g_add")
async def cb_g_add(call: CallbackQuery, state: FSMContext):
    if not await is_owner(call): return
    await call.message.edit_text(
        "➕ <b>[ADD GMAIL] Step 1/3</b>\n"
        "Enter a short Alias (e.g., main, work, gaming):"
    )
    await state.set_state(GmailLogin.alias)

@dp.message(GmailLogin.alias)
async def g_process_alias(message: types.Message, state: FSMContext):
    alias = message.text.strip()
    existing = await gmails_collection.find_one({"alias": alias})
    if existing:
        await message.answer(f"❌ Alias '<b>{alias}</b>' already exists. Try another alias:")
        return
    await state.update_data(alias=alias)
    await message.answer("➕ <b>[ADD GMAIL] Step 2/3</b>\nEnter your full Gmail Address:")
    await state.set_state(GmailLogin.email)

@dp.message(GmailLogin.email)
async def g_process_email(message: types.Message, state: FSMContext):
    email_id = message.text.strip()
    await state.update_data(email=email_id)
    await message.answer("➕ <b>[ADD GMAIL] Step 3/3</b>\nEnter your 16-digit App Password (without spaces):")
    await state.set_state(GmailLogin.password)

@dp.message(GmailLogin.password)
async def g_process_password(message: types.Message, state: FSMContext):
    password = message.text.strip().replace(" ", "")
    data = await state.get_data()
    try:
        await gmails_collection.insert_one({"alias": data['alias'], "email": data['email'], "app_password": password})
        await message.answer(
            f"✅ <b>GMAIL SAVED</b>\nAccount <code>{data['email']}</code> is securely linked as [<b>{data['alias']}</b>].",
            reply_markup=get_back_home_keyboard()
        )
    except Exception as e:
        await message.answer(f"❌ <b>Error:</b> {e}", reply_markup=get_back_home_keyboard())
    await state.clear()

# --- DYNAMIC OTP FETCH (GMAIL) ---
@dp.callback_query(F.data == "g_fetch_menu")
async def cb_g_fetch_menu(call: CallbackQuery):
    if not await is_owner(call): return
    accounts = await gmails_collection.find({}).to_list(length=100)
    if not accounts:
        await call.message.edit_text("📭 No Gmails saved to fetch OTP.", reply_markup=get_gmail_keyboard())
        return
    
    # Create Dynamic Buttons
    buttons = []
    for acc in accounts:
        buttons.append([InlineKeyboardButton(text=f"📧 {acc['alias']}", callback_data=f"getg_{acc['alias']}")])
    buttons.append([InlineKeyboardButton(text="🔙 Back", callback_data="menu_gmail")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await call.message.edit_text("🔑 <b>Select an account to fetch OTP:</b>", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("getg_"))
async def cb_fetch_g_otp(call: CallbackQuery):
    if not await is_owner(call): return
    alias = call.data.split("getg_")[1]
    
    account = await gmails_collection.find_one({"alias": alias})
    if not account: return
    
    await call.message.edit_text(f"⏳ <i>Scanning inbox for [<b>{alias}</b>]...</i>")
    
    # Run IMAP script
    result = await asyncio.to_thread(fetch_latest_email_sync, account["email"], account["app_password"])
    
    final_response = f"🛡️ <b>GMAIL INTERCEPT | [{alias.upper()}]</b>\n━━━━━━━━━━━━━━━━━━━━\n{result}"
    await call.message.edit_text(final_response, reply_markup=get_back_home_keyboard())

# ==========================================
# 📱 6. TELEGRAM OPERATIONS (FSM & DYNAMIC UI)
# ==========================================
@dp.callback_query(F.data == "t_list")
async def cb_t_list(call: CallbackQuery):
    if not await is_owner(call): return
    accounts = await tg_collection.find({}).to_list(length=100)
    if not accounts:
        await call.message.edit_text("📭 <b>VAULT:</b> No Telegrams registered.", reply_markup=get_tg_keyboard())
        return
    res = "📱 <b>SAVED TELEGRAM ACCOUNTS</b>\n━━━━━━━━━━━━━━━━━━━━\n"
    for acc in accounts: res += f"🔹 <code>{acc['phone']}</code>\n"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="menu_tg")]])
    await call.message.edit_text(res, reply_markup=keyboard)

@dp.callback_query(F.data == "t_add")
async def cb_t_add(call: CallbackQuery, state: FSMContext):
    if not await is_owner(call): return
    await call.message.edit_text(
        "➕ <b>[ADD TELEGRAM] Step 1/3</b>\n"
        "Enter Target Phone Number (with +CountryCode):"
    )
    await state.set_state(TgLogin.phone)

@dp.message(TgLogin.phone)
async def t_process_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    await state.update_data(phone=phone)
    wait_msg = await message.answer("⏳ <i>Connecting to Telegram Servers...</i>")
    
    client = TelegramClient(StringSession(), API_ID, API_HASH, device_model="Titan OTP Vault", system_version="Core 1.0", app_version="TitanBot v3.0")
    await client.connect()
    try:
        code_request = await client.send_code_request(phone)
        temp_clients[message.from_user.id] = {"client": client, "phone_code_hash": code_request.phone_code_hash}
        await wait_msg.edit_text(
            "➕ <b>[ADD TELEGRAM] Step 2/3</b>\n"
            "✅ <b>OTP SENT!</b> Enter the code received on official Telegram App.\n"
            "⚠️ <i>Important: Enter with spaces (e.g., 1 2 3 4 5)</i>"
        )
        await state.set_state(TgLogin.code)
    except Exception as e:
        await wait_msg.edit_text(f"❌ <b>ERROR:</b> {e}", reply_markup=get_back_home_keyboard())
        await state.clear()

@dp.message(TgLogin.code)
async def t_process_code(message: types.Message, state: FSMContext):
    code = message.text.strip().replace(" ", "")
    data = await state.get_data()
    phone = data['phone']
    client_data = temp_clients.get(message.from_user.id)
    
    if not client_data:
        await message.answer("❌ Session timeout.", reply_markup=get_back_home_keyboard())
        await state.clear()
        return
        
    client, phone_code_hash = client_data["client"], client_data["phone_code_hash"]
    wait_msg = await message.answer("⏳ <i>Verifying Code...</i>")
    
    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        session_string = client.session.save()
        await tg_collection.insert_one({"phone": phone, "session_string": session_string})
        await wait_msg.edit_text(f"✅ <b>TELEGRAM SAVED</b>\nAccount <code>{phone}</code> is secured.", reply_markup=get_back_home_keyboard())
        await client.disconnect()
        del temp_clients[message.from_user.id]
        await state.clear()
    except telethon.errors.SessionPasswordNeededError:
        await wait_msg.edit_text("🔒 <b>[ADD TELEGRAM] Step 3/3</b>\n2FA Detected! Enter your Cloud Password:")
        await state.set_state(TgLogin.password)
    except Exception as e:
        await wait_msg.edit_text(f"❌ <b>ERROR:</b> {e}", reply_markup=get_back_home_keyboard())
        await client.disconnect()
        await state.clear()

@dp.message(TgLogin.password)
async def t_process_password(message: types.Message, state: FSMContext):
    password = message.text.strip()
    data = await state.get_data()
    phone = data['phone']
    client = temp_clients.get(message.from_user.id)["client"]
    wait_msg = await message.answer("⏳ <i>Decrypting 2FA...</i>")
    
    try:
        await client.sign_in(password=password)
        session_string = client.session.save()
        await tg_collection.insert_one({"phone": phone, "session_string": session_string})
        await wait_msg.edit_text(f"✅ <b>TELEGRAM SAVED (2FA Passed)</b>\nAccount <code>{phone}</code> is secured.", reply_markup=get_back_home_keyboard())
        await client.disconnect()
        del temp_clients[message.from_user.id]
        await state.clear()
    except Exception as e:
        await wait_msg.edit_text(f"❌ <b>ERROR:</b> {e}", reply_markup=get_back_home_keyboard())
        await client.disconnect()
        await state.clear()

# --- DYNAMIC OTP FETCH (TELEGRAM) ---
@dp.callback_query(F.data == "t_fetch_menu")
async def cb_t_fetch_menu(call: CallbackQuery):
    if not await is_owner(call): return
    accounts = await tg_collection.find({}).to_list(length=100)
    if not accounts:
        await call.message.edit_text("📭 No Telegrams saved to fetch OTP.", reply_markup=get_tg_keyboard())
        return
    
    buttons = []
    for acc in accounts:
        buttons.append([InlineKeyboardButton(text=f"📱 {acc['phone']}", callback_data=f"gett_{acc['phone']}")])
    buttons.append([InlineKeyboardButton(text="🔙 Back", callback_data="menu_tg")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await call.message.edit_text("🔑 <b>Select an account to fetch OTP:</b>", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("gett_"))
async def cb_fetch_t_otp(call: CallbackQuery):
    if not await is_owner(call): return
    phone = call.data.split("gett_")[1]
    
    account = await tg_collection.find_one({"phone": phone})
    if not account: return
    
    wait_msg = await call.message.edit_text(f"⏳ <i>Syncing with Telegram core for <code>{phone}</code>...</i>")
    session_str = account.get("session_string")
    
    try:
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH, device_model="Titan OTP Vault", system_version="Core 1.0", app_version="TitanBot v3.0")
        await client.connect()
        if not await client.is_user_authorized():
            await wait_msg.edit_text("❌ <b>SESSION DEAD:</b> Token expired. Re-add account.", reply_markup=get_back_home_keyboard())
            await client.disconnect()
            return
            
        messages = await client.get_messages(777000, limit=2)
        if not messages:
            await wait_msg.edit_text(f"📭 No official messages found.", reply_markup=get_back_home_keyboard())
        else:
            response = f"🛡️ <b>TELEGRAM INTERCEPT | {phone}</b>\n━━━━━━━━━━━━━━━━━━━━\n"
            for msg in messages:
                response += f"💬 <b>[OFFICIAL MESSAGE]:</b>\n<code>{msg.text}</code>\n▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
            await wait_msg.edit_text(response, reply_markup=get_back_home_keyboard())
        await client.disconnect()
    except Exception as e:
        await wait_msg.edit_text(f"❌ <b>ERROR:</b> {e}", reply_markup=get_back_home_keyboard())


# ==========================================
# 🛠️ 7. CORE LOGIC (IMAP Fetch & Keep-Alive)
# ==========================================
def fetch_latest_email_sync(email_address, app_password):
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(email_address, app_password)
        mail.select("inbox")
        status, messages = mail.search(None, "ALL")
        email_ids = messages[0].split()
        if not email_ids: return "📭 <i>Inbox is empty.</i>"
        latest_email_id = email_ids[-1]
        status, msg_data = mail.fetch(latest_email_id, "(RFC822)")
        response_text = ""
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                msg = email.message_from_bytes(response_part[1])
                subject, encoding = decode_header(msg["Subject"])[0]
                if isinstance(subject, bytes): subject = subject.decode(encoding if encoding else "utf-8")
                response_text += f"📌 <b>SUBJECT:</b> <code>{subject}</code>\n"
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode()
                            break
                else: body = msg.get_payload(decode=True).decode()
                otps = re.findall(r'\b\d{4,8}\b', body)
                if otps: response_text += f"🔑 <b>DETECTED OTP:</b> <code>{', '.join(otps[:3])}</code>\n"
                response_text += f"\n📝 <b>BODY:</b>\n<i>{body[:250]}...</i>"
        mail.logout()
        return response_text
    except Exception as e:
        return f"❌ <b>ERROR:</b> {e}"

async def keep_sessions_alive():
    while True:
        try:
            accounts = await tg_collection.find({}).to_list(length=100)
            for acc in accounts:
                session_str = acc.get("session_string")
                if session_str:
                    client = TelegramClient(StringSession(session_str), API_ID, API_HASH, device_model="Titan OTP Vault", system_version="Core 1.0", app_version="TitanBot v3.0")
                    await client.connect()
                    if await client.is_user_authorized(): await client.get_me()
                    await client.disconnect()
        except Exception:
            pass
        await asyncio.sleep(43200)

async def handle_ping(request):
    return web.Response(text="TITAN OS V3 is active.")

async def web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def main():
    asyncio.create_task(web_server())
    asyncio.create_task(keep_sessions_alive())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
