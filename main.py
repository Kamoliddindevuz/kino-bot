import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- SOZLAMALAR ---
BOT_TOKEN = "8884134047:AAH9VLUItQukSswthtHpuC65IEiWNlterwc"
ADMIN_ID = 8295783400  # O'zingizning Telegram ID raqamingiz (int)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- BAZANI SOZLASH ---
def init_db():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    
    # Foydalanuvchilar jadvali
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY
        )
    """)
    
    # Kinolar jadvali
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            code INTEGER PRIMARY KEY,
            file_id TEXT,
            caption TEXT
        )
    """)
    
    # Majburiy obuna kanallari jadvali
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            channel_id TEXT PRIMARY KEY,
            title TEXT,
            invite_link TEXT
        )
    """)
    
    conn.commit()
    conn.close()

init_db()

# --- FSM (HOLATLAR) ---
class AddMovie(StatesGroup):
    waiting_for_code = State()
    waiting_for_video = State()

class AddChannel(StatesGroup):
    waiting_for_channel = State()

# --- BAZA BILAN ISHLASH FUNKSIYALARI ---
def add_user(user_id: int):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def get_channels():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT channel_id, title, invite_link FROM channels")
    rows = cursor.fetchall()
    conn.close()
    return rows

def remove_channel_from_db(channel_id: str):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
    conn.commit()
    conn.close()

# Obunani tekshirish
async def check_sub(user_id: int) -> bool:
    channels = get_channels()
    for ch_id, title, link in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch_id, user_id=user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception as e:
            logging.error(f"Obuna tekshirishda xatolik ({ch_id}): {e}")
            return False
    return True

# Obuna klaviaturasini yaratish
def get_sub_keyboard():
    channels = get_channels()
    builder = InlineKeyboardBuilder()
    for ch_id, title, link in channels:
        builder.button(text=f"➕ {title}", url=link)
    
    builder.button(text="✅ Tekshirish", callback_data="check_subscription")
    builder.adjust(1)
    return builder.as_markup()

# --- HANDLERLAR ---

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    add_user(message.from_user.id)
    
    if not await check_sub(message.from_user.id):
        await message.answer(
            "Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:",
            reply_markup=get_sub_keyboard()
        )
        return

    await message.answer("Xush kelibsiz! Kino kodini yuboring (masalan: 12 yoki 105).")

@dp.callback_query(F.data == "check_subscription")
async def check_button_handler(callback: types.CallbackQuery):
    if await check_sub(callback.from_user.id):
        await callback.message.delete()
        await callback.message.answer("Obuna tasdiqlandi! Endi kino kodini yuborishingiz mumkin.")
    else:
        await callback.answer("Siz hali barcha kanallarga obuna bo'lmadingiz! ❌", show_alert=True)

# ADMIN PANEL: Kanal qo'shish (/addchannel)
@dp.message(Command("addchannel"))
async def add_channel_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer(
        "Kanalni ulash uchun ushbu tartibni bajaring:\n\n"
        "1. Botni kanalingizga/guruhingizga **Admin** qiling.\n"
        "2. Kanal/guruhdan ixtiyoriy bir postni **menga forward (qayta yo'naltirib)** yuboring yoki `@username` manzilini yozib yuboring."
    )
    await state.set_state(AddChannel.waiting_for_channel)

@dp.message(AddChannel.waiting_for_channel)
async def process_channel_input(message: types.Message, state: FSMContext):
    chat_id = None
    title = None

    # Forward qilingan postdan ma'lumot olish
    if message.forward_from_chat:
        chat_id = str(message.forward_from_chat.id)
        title = message.forward_from_chat.title
    # @username shaklida yozilgan bo'lsa
    elif message.text and message.text.startswith("@"):
        try:
            chat = await bot.get_chat(message.text)
            chat_id = str(chat.id)
            title = chat.title
        except Exception as e:
            await message.answer(f"Kanal topilmadi yoki bot u yerda admin emas. Xato: {e}")
            return
    else:
        await message.answer("Iltimos, kanal postini forward qiling yoki `@username` ko'rinishida yuboring.")
        return

    # Taklif havolasini (Invite Link) olish
    try:
        chat_obj = await bot.get_chat(chat_id)
        invite_link = chat_obj.invite_link or f"https://t.me/{chat_obj.username}" if chat_obj.username else None
        
        if not invite_link:
            invite_link = await bot.create_chat_invite_link(chat_id)
            invite_link = invite_link.invite_link

    except Exception as e:
        await message.answer(f"Kanal linkini olishda xatolik. Bot kanalda admin ekanligini tekshiring!\nXato: {e}")
        return

    # Bazaga saqlash
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO channels (channel_id, title, invite_link) VALUES (?, ?, ?)",
        (chat_id, title, invite_link)
    )
    conn.commit()
    conn.close()

    await message.answer(f"✅ Kanal muvaffaqiyatli qo'shildi:\n**{title}** (`{chat_id}`)")
    await state.clear()

# ADMIN PANEL: Kanallar ro'yxati va o'chirish (/channels)
@dp.message(Command("channels"))
async def list_channels(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    channels = get_channels()
    if not channels:
        await message.answer("Hozircha hech qanday kanal ulanmagan.")
        return

    builder = InlineKeyboardBuilder()
    text = "📋 **Ulanga kanallar ro'yxati:**\n\n"
    for ch_id, title, link in channels:
        text += f"• {title} (`{ch_id}`)\n"
        builder.button(text=f"❌ {title} ni o'chirish", callback_data=f"del_ch_{ch_id}")

    builder.adjust(1)
    await message.answer(text, reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("del_ch_"))
async def delete_channel_callback(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    channel_id = callback.data.replace("del_ch_", "")
    remove_channel_from_db(channel_id)
    await callback.answer("Kanal o'chirildi! ✅", show_alert=True)
    await callback.message.delete()

# STATISTIKA VA KINO QO'SHISH COMMANDLARI
@dp.message(Command("stat"))
async def stat_handler(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM movies")
    movie_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM channels")
    channel_count = cursor.fetchone()[0]
    conn.close()

    await message.answer(
        f"📊 **Bot Statistikasi:**\n\n"
        f"👤 Foydalanuvchilar: **{user_count}** ta\n"
        f"🎬 Kinolar: **{movie_count}** ta\n"
        f"📢 Ulandan kanallar: **{channel_count}** ta"
    )

@dp.message(Command("add"))
async def add_movie_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer("Kino uchun ixtiyoriy raqam (kod) kiriting:")
    await state.set_state(AddMovie.waiting_for_code)

@dp.message(AddMovie.waiting_for_code)
async def process_code(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Iltimos, faqat raqam kiriting!")
        return
    
    await state.update_data(movie_code=int(message.text))
    await message.answer("Endi ushbu kodga tegishli kino videosini yuboring:")
    await state.set_state(AddMovie.waiting_for_video)

@dp.message(AddMovie.waiting_for_video, F.video)
async def process_video(message: types.Message, state: FSMContext):
    data = await state.get_data()
    movie_code = data["movie_code"]
    file_id = message.video.file_id
    caption = message.caption or ""

    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO movies (code, file_id, caption) VALUES (?, ?, ?)",
        (movie_code, file_id, caption)
    )
    conn.commit()
    conn.close()

    await message.answer(f"✅ Kino saqlandi! Kod: **{movie_code}**")
    await state.clear()

@dp.message(F.text.isdigit())
async def get_movie(message: types.Message):
    add_user(message.from_user.id)

    if not await check_sub(message.from_user.id):
        await message.answer(
            "Kinolarni ko'rish uchun avval kanallarga obuna bo'ling:",
            reply_markup=get_sub_keyboard()
        )
        return

    movie_code = int(message.text)
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT file_id, caption FROM movies WHERE code = ?", (movie_code,))
    result = cursor.fetchone()
    conn.close()

    if result:
        file_id, caption = result
        await message.answer_video(video=file_id, caption=caption)
    else:
        await message.answer("Ushbu kod ostida hech qanday kino topilmadi ❌")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
