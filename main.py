import os
import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMINS = [8295783400]

bot = Bot(token=TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot, storage=MemoryStorage())

CHANNELS = []
MOVIES = {}
PENDING_USERS = set()  # (user_id, chat_id) ko'rinishida saqlanadi

class AddChannelState(StatesGroup):
    waiting_for_channel = State()

class AddMovieState(StatesGroup):
    waiting_for_code = State()
    waiting_for_video = State()


@dp.chat_join_request_handler()
async def process_join_request(update: types.ChatJoinRequest):
    PENDING_USERS.add((update.from_user.id, update.chat.id))
    try:
        await bot.send_message(
            chat_id=update.from_user.id,
            text="<b>Zayavka qabul qilindi!</b>\nEndi botga qaytib <b>'✅ Tekshirish'</b> tugmasini bosing."
        )
    except Exception as e:
        logging.error(f"Xatolik: {e}")


async def check_user_status(user_id: int, chat_id: int) -> bool:
    if (user_id, chat_id) in PENDING_USERS:
        return True
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
    except Exception as e:
        logging.error(f"Kanal tekshirishda xato: {e}")
    return False


@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    user_id = message.from_user.id

    unsubscribed = []
    for ch in CHANNELS:
        is_ok = await check_user_status(user_id, ch['id'])
        if not is_ok:
            unsubscribed.append(ch)

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


@dp.callback_query_handler(text="check_subscription")
async def check_callback(call: types.CallbackQuery):
    user_id = call.from_user.id
    unsubscribed = []

    for ch in CHANNELS:
        is_ok = await check_user_status(user_id, ch['id'])
        if not is_ok:
            unsubscribed.append(ch)

    if unsubscribed:
        await call.answer("Hali zayavka yubormadingiz yoki obuna bo'lmadingiz!", show_alert=True)
    else:
        await call.message.delete()
        await call.message.answer("<b>Rahmat! Zayavka tasdiqlandi. Kino kodini yuboring:</b>")


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
            invite_link = await bot.create_chat_invite_link(
                chat_id=chat.id,
                creates_join_request=True
            )
            CHANNELS.append({
                "id": chat.id,
                "title": chat.title,
                "link": invite_link.invite_link
            })
            await message.answer(f"✅ <b>Kanal qo'shildi!</b>\n\n<b>Kanal:</b> {chat.title}\n<b>Link:</b> {invite_link.invite_link}")
        except Exception as e:
            await message.answer(f"❌ Xatolik! Bot kanalda admin va link yaratish huquqi borligini tekshiring.\n\nLog: {e}")
    else:
        await message.answer("Iltimos, xabarni FORWARD qilib yuboring.")
    await state.finish()


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
