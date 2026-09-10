import os
import re
import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

# Logging sozlamalari
logging.basicConfig(level=logging.INFO)

# TELEGRAM BOT TOKEN
TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

bot = Bot(token=TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot, storage=MemoryStorage())

# Vaqtinchalik ma'lumotlar bazasi (Xotirada)
# Asosiy ishda ma'lumotlar bazasi (SQLite, DB va h.k.) ishlatiladi
CHANNELS = []  # [{ "id": chat_id, "title": title, "link": link }]
MOVIES = {}    # { "code": { "file_id": id, "caption": text } }
ADMINS = []    # Admin ID lari

class AddChannelState(StatesGroup):
    waiting_for_channel = State()

class AddMovieState(StatesGroup):
    waiting_for_code = State()
    waiting_for_video = State()


# --- START VA HELP HANDLERLARI ---

@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    # Adminlarni birinchi start bosganda ro'yxatga olish (misol uchun)
    if message.from_user.id not in ADMINS and len(ADMINS) == 0:
        ADMINS.append(message.from_user.id)

    # Majburiy obunani tekshirish
    unsubscribed = []
    for ch in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=ch['id'], user_id=message.from_user.id)
            if member.status in ['left', 'kicked']:
                unsubscribed.append(ch)
        except Exception as e:
            logging.error(f"Kanalni tekshirishda xatolik: {e}")

    if unsubscribed:
        keyboard = types.InlineKeyboardMarkup(row_width=1)
        for ch in unsubscribed:
            url = ch.get('link') or "https://t.me"
            keyboard.add(types.InlineKeyboardButton(text=f"➕ {ch['title']}", url=url))
        keyboard.add(types.InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_subscription"))
        
        await message.answer(
            "<b>Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling va Zayavka yuboring:</b>",
            reply_markup=keyboard
        )
        return

    await message.answer("<b>Xush kelibsiz!</b> Kinoni ko'rish uchun kino kodini yuboring.")


@dp.callback_query_handler(text="check_subscription")
async def check_sub_callback(call: types.CallbackQuery):
    unsubscribed = []
    for ch in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=ch['id'], user_id=call.from_user.id)
            if member.status in ['left', 'kicked']:
                unsubscribed.append(ch)
        except Exception:
            pass

    if unsubscribed:
        await call.answer("⚠️ Hali barcha kanallarga obuna bo'lmadingiz!", show_alert=True)
    else:
        await call.message.delete()
        await call.message.answer("✅ Rahmat! Endi kino kodini yuborishingiz mumkin.")


# --- KANAL QO'SHISH VA BOSHQARISH ---

@dp.message_handler(commands=['addchannel'])
async def cmd_add_channel(message: types.Message):
    if message.from_user.id not in ADMINS:
        return
    
    await message.answer(
        "<b>Kanal ulash uchun:</b>\n\n"
        "1. Botni kanalga <b>Admin</b> qiling (Taklif havolalari yaratish huquqini bering).\n"
        "2. Kanalning <code>@username</code>ini, <code>https://t.me/...</code> linkini yoki <b>kanaldan biror xabarni ushbu botga FORWARD qilib yuboring</b>."
    )
    await AddChannelState.waiting_for_channel.set()


@dp.message_handler(state=AddChannelState.waiting_for_channel, content_types=types.ContentTypes.ANY)
async def process_add_channel(message: types.Message, state: FSMContext):
    chat_id = None
    custom_link = None

    # 1. Agar kanaldan Forward qilingan xabar bo'lsa (Zayavkali/Private kanallar uchun eng ma'quli)
    if message.forward_from_chat:
        chat_id = message.forward_from_chat.id

    # 2. Agar matn ko'rinishida yuborilgan bo'lsa
    elif message.text:
        text = message.text.strip()
        if "t.me/" in text:
            username_match = re.search(r"t\.me/([a-zA-Z0-9_]+)", text)
            if username_match:
                chat_id = f"@{username_match.group(1)}"
            else:
                custom_link = text
        elif text.startswith("@"):
            chat_id = text
        elif text.startswith("-100") and text[1:].isdigit():
            chat_id = int(text)

    if not chat_id:
        await message.answer("❌ Kanal aniqlanmadi. Iltimos, kanaldan biror xabarni FORWARD qilib yuboring yoki @username / link yuboring.")
        return

    try:
        chat_info = await bot.get_chat(chat_id)
        bot_member = await bot.get_chat_member(chat_info.id, bot.id)
        
        if bot_member.status not in ["administrator", "creator"]:
            await message.answer("⚠️ Bot ushbu kanalda ADMIN emas! Avval botga adminlik huquqini bering.")
            await state.finish()
            return

        # Kanal invite linkini olish
        invite_link = custom_link or chat_info.invite_link
        if not invite_link:
            try:
                invite_link = await bot.export_chat_invite_link(chat_info.id)
            except Exception:
                invite_link = f"https://t.me/{chat_info.username}" if chat_info.username else None

        # Kanalni ro'yxatga saqlash
        channel_data = {
            "id": chat_info.id,
            "title": chat_info.title,
            "link": invite_link
        }
        
        # Takrorlanmaslikni tekshirish
        CHANNELS[:] = [c for c in CHANNELS if c['id'] != chat_info.id]
        CHANNELS.append(channel_data)

        await message.answer(f"✅ <b>{chat_info.title}</b> kanali muvaffaqiyatli ulandi!\nLink: {invite_link}")
        await state.finish()

    except Exception as e:
        await message.answer(f"❌ Xatolik yuz berdi: {e}")
        await state.finish()


@dp.message_handler(commands=['channels'])
async def list_channels(message: types.Message):
    if message.from_user.id not in ADMINS:
        return
    if not CHANNELS:
        await message.answer("Hozircha ulangan kanallar yo'q.")
        return

    text = "<b>Ulangan kanallar ro'yxati:</b>\n\n"
    for idx, ch in enumerate(CHANNELS, 1):
        text += f"{idx}. {ch['title']} (ID: <code>{ch['id']}</code>)\n"
    await message.answer(text)


# --- ZAYAVKALARNI AVTOMATIK QABUL QILISH (JOIN REQUEST) ---

@dp.chat_join_request_handler()
async def auto_approve_join_request(update: types.ChatJoinRequest):
    try:
        # Zayapkani avtomatik tasdiqlash
        await update.approve()
        
        # Foydalanuvchiga xabar yuborish
        await bot.send_message(
            chat_id=update.from_user.id,
            text="✅ Sizning kanaldagi zayavkangiz qabul qilindi! Endi botdan kinolarni tomosha qilishingiz mumkin."
        )
    except Exception as e:
        logging.error(f"Zayavka qabul qilishda xatolik: {e}")


# --- KINO YUKLASH VA QIDIRISH ---

@dp.message_handler(commands=['add'])
async def add_movie_start(message: types.Message):
    if message.from_user.id not in ADMINS:
        return
    await message.answer("Kino uchun kod kiriting (Masalan: 101):")
    await AddMovieState.waiting_for_code.set()


@dp.message_handler(state=AddMovieState.waiting_for_code)
async def process_movie_code(message: types.Message, state: FSMContext):
    code = message.text.strip()
    await state.update_data(code=code)
    await message.answer(f"<b>{code}</b> kodi uchun kino videosini yuboring:")
    await AddMovieState.waiting_for_video.set()


@dp.message_handler(content_types=types.ContentTypes.VIDEO, state=AddMovieState.waiting_for_video)
async def process_movie_video(message: types.Message, state: FSMContext):
    data = await state.get_data()
    code = data['code']
    
    MOVIES[code] = {
        "file_id": message.video.file_id,
        "caption": message.caption or ""
    }
    
    await message.answer(f"✅ Kino saqlandi! Kod: <b>{code}</b>")
    await state.finish()


@dp.message_handler(commands=['stat'])
async def show_stats(message: types.Message):
    if message.from_user.id not in ADMINS:
        return
    await message.answer(f"📊 <b>Statistika:</b>\n\nUlangan kanallar: {len(CHANNELS)} ta\nYuklangan kinolar: {len(MOVIES)} ta")


# --- KINO KODINI QABUL QILISH ---

@dp.message_handler()
async def get_movie_by_code(message: types.Message):
    code = message.text.strip()
    
    if code in MOVIES:
        movie = MOVIES[code]
        await message.answer_video(
            video=movie['file_id'],
            caption=movie['caption']
        )
    else:
        await message.answer("❌ Bunday kodli kino topilmadi. Kodni to'g'ri kiritganingizni tekshiring.")


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
