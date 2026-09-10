import os
import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

# Logging sozlamalari
logging.basicConfig(level=logging.INFO)

# TELEGRAM BOT TOKEN VA ADMINLAR
TOKEN = os.getenv("BOT_TOKEN", "8884134047:AAH9VLUItQukSswthtHpuC65IEiWNlterwc")
ADMINS = [8295783400]  # O'zingizning Telegram ID'ingiz

bot = Bot(token=TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot, storage=MemoryStorage())

# Vaqtinchalik ma'lumotlar bazasi (Xotirada)
CHANNELS = []       # [{"id": chat_id, "title": title, "link": link}]
MOVIES = {}         # {"code": {"file_id": id, "caption": text}}
PENDING_USERS = set() # Zayavka tashlagan foydalanuvchilar ID'si

class AddChannelState(StatesGroup):
    waiting_for_channel = State()

class AddMovieState(StatesGroup):
    waiting_for_code = State()
    waiting_for_video = State()


# --- CHAT JOIN REQUEST HANDLER (Zayavkalarni ushlab qolish) ---
@dp.chat_join_request_handler()
async def process_join_request(update: types.ChatJoinRequest):
    # Foydalanuvchi zayavka tashlaganda uni ro'yxatga olamiz
    PENDING_USERS.add(update.from_user.id)
    try:
        await bot.send_message(
            chat_id=update.from_user.id,
            text="<b>Arizangiz qabul qilindi!</b>\nEndi botdan bemalol foydalanishingiz mumkin."
        )
    except Exception as e:
        logging.error(f"Foydalanuvchiga xabar yuborishda xatolik: {e}")


# --- START HANDLER ---
@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    user_id = message.from_user.id

    if user_id not in ADMINS and len(ADMINS) == 0:
        ADMINS.append(user_id)

    # Obunani va Zayavkalarni tekshirish
    unsubscribed = []
    for ch in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=ch['id'], user_id=user_id)
            # Agar foydalanuvchi kanalda bo'lmasa va zayavka ham topshirmagan bo'lsa
            if member.status in ['left', 'kicked'] and user_id not in PENDING_USERS:
                unsubscribed.append(ch)
        except Exception as e:
            logging.error(f"Kanalni tekshirishda xatolik: {e}")

    if unsubscribed:
        keyboard = types.InlineKeyboardMarkup(row_width=1)
        for ch in unsubscribed:
            keyboard.add(types.InlineKeyboardButton(text=f"➕ {ch['title']}", url=ch['link']))
        keyboard.add(types.InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_subscription"))

        await message.answer(
            "<b>Botdan foydalanish uchun quyidagi kanallarga qo'shilish so'rovini (zayavka) yuboring:</b>",
            reply_markup=keyboard
        )
    else:
        await message.answer("<b>Xush kelibsiz! Kino kodini yuboring:</b>")


# --- TEKSHIRISH BUTTON CALLBACK ---
@dp.callback_query_handler(text="check_subscription")
async def check_callback(call: types.CallbackQuery):
    user_id = call.from_user.id
    unsubscribed = []

    for ch in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=ch['id'], user_id=user_id)
            if member.status in ['left', 'kicked'] and user_id not in PENDING_USERS:
                unsubscribed.append(ch)
        except Exception as e:
            logging.error(f"Tekshirishda xatolik: {e}")

    if unsubscribed:
        await call.answer("Barcha kanallarga zayavka yubormadingiz!", show_alert=True)
    else:
        await call.message.delete()
        await call.message.answer("<b>Rahmat! Obuna/Zayavka tekshirildi. Kino kodini yuboring:</b>")


# --- ADMIN PANEL & KANAL QO'SHISH ---
@dp.message_handler(commands=['addchannel'])
async def add_channel_start(message: types.Message):
    if message.from_user.id not in ADMINS:
        return
    await AddChannelState.waiting_for_channel.set()
    await message.answer("Kanalni qo'shish uchun kanaldan biror xabarni botga <b>FORWARD</b> qilib yuboring.")

@dp.message_handler(state=AddChannelState.waiting_for_channel, content_types=types.ContentTypes.ANY)
async def process_channel_forward(message: types.Message, state: FSMContext):
    if message.forward_from_chat:
        chat = message.forward_from_chat
        try:
            # Zayavkali maxsus link yaratamiz (creates_join_request=True)
            invite_link = await bot.create_chat_invite_link(
                chat_id=chat.id,
                creates_join_request=True
            )
            
            CHANNELS.append({
                "id": chat.id,
                "title": chat.title,
                "link": invite_link.invite_link
            })
            
            await message.answer(f"✅ <b>Kanal muvaffaqiyatli qo'shildi!</b>\n\n<b>Kanal:</b> {chat.title}\n<b>Zayavka havolasi:</b> {invite_link.invite_link}")
        except Exception as e:
            await message.answer(f"❌ Xatolik! Botni kanalda admin qilganingizga va link yaratish huquqi borligiga ishonch hosil qiling.\n\nLog: {e}")
    else:
        await message.answer("Iltimos, kanal xabarini <b>FORWARD</b> (qayta yo'naltirib) qilib yuboring.")
    await state.finish()


# --- KINO QO'SHISH VA QIDIRISH ---
@dp.message_handler(commands=['add'])
async def add_movie_start(message: types.Message):
    if message.from_user.id not in ADMINS:
        return
    await AddMovieState.waiting_for_code.set()
    await message.answer("Kino uchun kod kiriting (Masalan: 101):")

@dp.message_handler(state=AddMovieState.waiting_for_code)
async def process_movie_code(message: types.Message, state: FSMContext):
    await state.update_data(code=message.text.strip())
    await AddMovieState.waiting_for_video.set()
    await message.answer("Endi kinoni (video faylini) yuboring:")

@dp.message_handler(state=AddMovieState.waiting_for_video, content_types=types.ContentType.VIDEO)
async def process_movie_video(message: types.Message, state: FSMContext):
    data = await state.get_data()
    code = data['code']
    
    MOVIES[code] = {
        "file_id": message.video.file_id,
        "caption": message.caption or ""
    }
    await message.answer(f"✅ Kino saqlandi! Kodu: <b>{code}</b>")
    await state.finish()

@dp.message_handler()
async def search_movie(message: types.Message):
    code = message.text.strip()
    if code in MOVIES:
        movie = MOVIES[code]
        await message.answer_video(video=movie['file_id'], caption=movie['caption'])
    else:
        await message.answer("Bunday kodli kino topilmadi.")


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
