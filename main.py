import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, html, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import CommandStart, Command
from openai import AsyncOpenAI
from aiohttp import web

# Logging
logging.basicConfig(level=logging.INFO)

# Tokenlar
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")

if not TELEGRAM_TOKEN or not CLAUDE_API_KEY:
    raise ValueError("TELEGRAM_TOKEN yoki CLAUDE_API_KEY topilmadi!")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# OpenAI klienti orqali OpenRouter
client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=CLAUDE_API_KEY,
    default_headers={
        "HTTP-Referer": "https://render.com",
        "X-Title": "Telegram Multi-Model Bot"
    }
)

# Xotira lug'atlari
chat_histories = {}
user_models = {} # Foydalanuvchi tanlagan modelni saqlaydi: {user_id: "model_nomi"}

# Modellarni aniqlab olamiz
MODEL_GPT = "openai/gpt-oss-20b:free"
MODEL_GEMMA = "google/gemma-4-31b-it:free"

# Modellarni tanlash uchun tugmalar (Inline Keyboard)
def get_model_keyboard():
    buttons = [
        [InlineKeyboardButton(text="🧠 GPT-OSS 120B (Katta va aqlli)", callback_data="set_gpt")],
        [InlineKeyboardButton(text="⚡ Gemma 4 31B (Tezkor va yangi)", callback_data="set_gemma")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    user_id = message.from_user.id
    chat_histories[user_id] = []
    # Standart holatda GPT modelini o'rnatamiz
    user_models[user_id] = MODEL_GPT
    
    await message.answer(
        f"Salom, {html.bold(message.from_user.full_name)}!\n"
        f"Men multimodel botman. Hozirda sizda <b>GPT-OSS 120B</b> modeli faol.\n\n"
        f"🤖 Modelni o'zgartirish uchun: /model buyrug'ini yuboring.\n"
        f"🧹 Tarixni o'chirish uchun: /clear"
    )

@dp.message(Command("model"))
async def command_model_handler(message: Message) -> None:
    """ Modelni tanlash tugmalarini chiqarish """
    await message.answer("Quyidagi AI modellaridan birini tanlang:", reply_markup=get_model_keyboard())

@dp.message(Command("clear"))
async def command_clear_handler(message: Message) -> None:
    user_id = message.from_user.id
    chat_histories[user_id] = []
    await message.answer("🧹 Suhbatingiz tarixi tozalandi!")

# Tugmalar bosilganda ishlaydigan qism (Callback Query)
@dp.callback_query(F.data == "set_gpt")
async def process_set_gpt(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_models[user_id] = MODEL_GPT
    chat_histories[user_id] = [] # Model almashganda tarixni tozalash tavsiya etiladi
    await callback.message.edit_text("✅ Model <b>GPT-OSS 120B</b> ga o'zgartirildi va chat tarixi yangilandi!", parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "set_gemma")
async def process_set_gemma(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_models[user_id] = MODEL_GEMMA
    chat_histories[user_id] = []
    await callback.message.edit_text("✅ Model <b>Gemma 4 31B</b> ga o'zgartirildi va chat tarixi yangilandi!", parse_mode="HTML")
    await callback.answer()

@dp.message()
async def ai_handler(message: Message) -> None:
    user_id = message.from_user.id
    
    if user_id not in chat_histories:
        chat_histories[user_id] = []
    # Agar foydalanuvchi model tanlamagan bo'lsa, standart GPT qoladi
    if user_id not in user_models:
        user_models[user_id] = MODEL_GPT
        
    waiting_message = await message.answer("💡 <i>O'ylayapman...</i>", parse_mode="HTML")
    
    chat_histories[user_id].append({"role": "user", "content": message.text})
    
    # Tarixni 50 ta xabarga cheklaymiz (Siz xohlagandek)
    if len(chat_histories[user_id]) > 50:
        chat_histories[user_id] = chat_histories[user_id][-50:]

    try:
        # Tanlangan model orqali so'rov yuboriladi
        response = await client.chat.completions.create(
            model=user_models[user_id], # Dinamik ravishda tanlangan model qo'yildi
            messages=chat_histories[user_id],
            max_tokens=1500
        )
        
        reply_text = response.choices[0].message.content
        chat_histories[user_id].append({"role": "assistant", "content": reply_text})
        
        await waiting_message.delete()
        await message.answer(reply_text)
        
    except Exception as e:
        logging.error(f"Xatolik yuz berdi: {e}")
        await waiting_message.delete()
        await message.answer(f"❌ Xatolik yuz berdi:\n<code>{str(e)[:150]}</code>", parse_mode="HTML")

# Veb-ping xizmati Render uchun
async def handle_ping(request):
    return web.Response(text="Bot faol!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def main() -> None:
    asyncio.create_task(start_web_server())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
