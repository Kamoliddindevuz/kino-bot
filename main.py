import os
import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN", "8884134047:AAH9VLUItQukSswthtHpuC65IEiWNlterwc")
ADMINS = [8295783400]

bot = Bot(token=TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot, storage=MemoryStorage())

CHANNELS = []        # [{"id": chat_id, "title": title, "link": link}]
MOVIES = {}          # {"code": {"file_id": id, "caption": text}}
CLICKED_CHANNELS = {} # {user_id: set(channel_index)}

class AddChannelState(StatesGroup):
    waiting_for_channel = State()

class AddMovieState(StatesGroup):
    waiting_for_code = State()
    waiting_for_video = State()


# --- CHAT JOIN REQUEST HANDLER ---
@dp.chat_join_request_handler()
async def process_join_request(update: types.ChatJoinRequest):
    user_id = update.from_user.id
    if user_id not in CLICKED_CHANNELS:
        CLICKED_CHANNELS[user_id] = set()
    
    # Barcha kanallar indeksi bo'yicha belgilaymiz
    for idx, ch in enumerate(CHANNELS):
        if ch['id'] == update.chat.id:
            CLICKED_CHANNELS[user_id].add(idx)

    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"<b>'{update.chat.title}'</b> kanaliga zayavka qabul qilindi!\nEndi botga o'tib <b>'✅ Tekshirish'</b> tugmasini bosing."
        )
    except Exception as e:
        logging.error(f"Xabar yuborishda xatolik: {e}")


# --- KANAL TUGMASINI BOSGANDA (CALLBACK) ---
@dp.callback_query_handler(lambda c: c.data.startswith("join_"))
async def track_channel_click(call: types.CallbackQuery):
    user_id = call.from_user.id
    ch_index = int(call.data.split("_")[1])

    if user_id not in CLICKED_CHANNELS:
        CLICKED_CHANNELS[user_id] = set()

    CLICKED_CHANNELS[user_id].add(ch_index)
    
    # Kanal havolasini olish va yo'naltirish
    if ch_index < len(CHANNELS):
        link = CHANNELS[ch_index]['link']
        await call.answer("Kanalga o'tilmoqda... Zayavka yuborib qayting!", show_alert=False)
        await call.message.answer(f"🔗 <a href='{link}'>Kanalga kirish va zayavka yuborish uchun bosing</a>")
    else:
        await call.answer("Kanal topilmadi.")


# --- START HANDLER ---
@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    user_id = message.from_user.id

    user_clicks = CLICKED_CHANNELS.get(user_id, set())
    unvisited = [ch for idx, ch in enumerate(CHANNELS) if idx not in user_clicks]

    if unvisited and CHANNELS:
        keyboard = types.InlineKeyboardMarkup(row_width=1)
        for idx, ch in enumerate(CHANNELS):
            if idx not in user_clicks:
                keyboard.add(types.InlineKeyboardButton(text=f"➕ {ch['title']}", callback_data=f"join_{idx}"))
        
        keyboard.add(types.InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_subscription"))

        await message.answer(
            "<b>Botdan foydalanish uchun quyidagi kanallarga kirib qo'shilish so'rovini (zayavka) yuboring:</b>",
            reply_markup=keyboard
        )
    else:
        await message.answer("<b>Xush kelibsiz! Kino kodini yuboring:</b>")


# --- TEKSHIRISH TUGMASI ---
@dp.callback_query_handler(text="check_subscription")
async def check_callback(call: types.CallbackQuery):
    user_id = call.from_user.id
    user_clicks = CLICKED_CHANNELS.get(user_id, set())

    # Barcha kanallarga bosilganini tekshiramiz
    if len(user_clicks) < len(CHANNELS):
        await call.answer("Barcha kanallarga zayavka yubormadingiz! Har bir kanal tugmasini bosing.", show_alert=True)
    else:
        await call.message.delete()
        await call.message.answer("<b>Rahmat! Zayavkalaringiz tasdiqlandi. Kino kodini yuboring:</b>")


# --- ADMIN PANEL ---
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
        
        if any(c['id'] == chat.id for c in CHANNELS):
            await message.answer("⚠️ Bu kanal allaqachon qo'shilgan!")
            await state.finish()
            return

        try:
            invite_link = await bot.create_chat_invite_link(
                chat_id=chat.id,
                creates_join_request=True
            )
            CHANNELS.append({
                "id": chat.id,
                "title": chat.title,
                "link": invite_link.invite_link
            })
            await message.answer(
                f"✅ <b>Kanal qo'shildi!</b>\n\n"
                f"<b>Kanal:</b> {chat.title}\n"
                f"<b>Jami kanallar:</b> {len(CHANNELS)} ta"
            )
        except Exception as e:
            await message.answer(f"❌ Xatolik! Bot kanalda admin ekanligini tekshiring.\n\nLog: {e}")
    else:
        await message.answer("Iltimos, kanal xabarini FORWARD qilib yuboring.")
    await state.finish()


# --- KINO BAZA ---
@dp.message_handler(commands=['add'])
async def add_movie_start(message: types.Message):
    if message.from_user.id not in ADMINS:
        return
    await AddMovieState.waiting_for_code.set()
    await message.answer("Kino uchun kod kiriting:")


@dp.message_handler(state=AddMovieState.waiting_for_code)
async def process_movie_code(message: types.Message, state: FSMContext):
    await state.update_data(code=message.text.strip())
    await AddMovieState.waiting_for_video.set()
    await message.answer("Endi videoni yuboring:")


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
