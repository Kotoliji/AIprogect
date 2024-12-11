import openai
from telegram import Update, InputFile
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import logging
from io import BytesIO
from gtts import gTTS
import os
import speech_recognition as sr
import tempfile
import pyogg
import ctypes
import numpy as np
from PIL import Image
import requests

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
openai.api_key = "YOUR_OPENAI_API_KEY"


# --- Вступні повідомлення ---
messages = [
    {"role": "system", "content": "Ти - універсальний бот, що обробляє текст, аудіо та зображення."}
]

# --- Текстова обробка ---
def get_chatgpt_response(user_text: str) -> str:
    messages.append({"role": "user", "content": user_text})
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=messages
    )
    reply = response.choices[0].message.content.strip()
    messages.append({"role": "assistant", "content": reply})
    return reply

# --- Аудіо обробка ---
def transcribe_audio(ogg_data):
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp_file:
        tmp_file.write(ogg_data.getvalue())
        tmp_file_name = tmp_file.name

    try:
        opus_file = pyogg.OpusFile(tmp_file_name)

        channels = opus_file.channels
        buffer_length = opus_file.buffer_length
        total_samples = buffer_length * channels

        c_short_array_type = ctypes.c_short * total_samples
        c_short_array = c_short_array_type.from_address(ctypes.addressof(opus_file.buffer.contents))

        pcm_array = np.ctypeslib.as_array(c_short_array)

        raw_data = pcm_array.tobytes()

        r = sr.Recognizer()
        sample_rate = opus_file.frequency
        audio_data = sr.AudioData(raw_data, sample_rate, 2)
        try:
            text = r.recognize_google(audio_data, language="uk-UA")
            return text.strip()
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            logger.error(f"Помилка розпізнавання: {e}")
            return None
    finally:
        if os.path.exists(tmp_file_name):
            os.remove(tmp_file_name)



# --- Генерація зображень ---
def generate_image(prompt: str) -> BytesIO:
    try:
        response = openai.Image.create(
            prompt=prompt,
            n=1,
            size="512x512"
        )
        image_url = response['data'][0]['url']
        image_data = BytesIO()
        image_data.write(requests.get(image_url).content)
        image_data.seek(0)
        return image_data
    except Exception as e:
        logger.error(f"Помилка генерації зображення: {e}")
        raise

# --- Telegram Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = ("Привіт! Я OpenAI бот. Надішліть текст, аудіо або запит для створення зображення."
                    "Для створенн зображення напиши 'Створи зображення:' ")
    await update.message.reply_text(welcome_text)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    if user_text.startswith("Створи зображення:"):
        prompt = user_text.replace("Створи зображення:", "").strip()
        try:
            image = generate_image(prompt)
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=image, caption="Ось ваше зображення")
        except Exception:
            await update.message.reply_text("Не вдалося створити зображення. Спробуйте ще раз.")
    else:
        response_text = get_chatgpt_response(user_text)
        await update.message.reply_text(response_text)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_id = update.message.voice.file_id
    file = await context.bot.get_file(file_id)
    file_path = BytesIO()
    await file.download_to_memory(file_path)
    file_path.seek(0)

    recognized_text = transcribe_audio(file_path)
    if not recognized_text:
        await update.message.reply_text("Не вдалося розпізнати аудіо.")
        return

    response_text = get_chatgpt_response(recognized_text)
    tts = gTTS(response_text, lang="uk")
    audio_response = BytesIO()
    tts.write_to_fp(audio_response)
    audio_response.seek(0)

    await context.bot.send_voice(
        chat_id=update.effective_chat.id,
        voice=audio_response,
        caption=response_text
    )

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Цей бот не підтримує аналіз зображень. Для створення зображення введіть: 'Створи зображення: [ваш опис]'")

# --- Основна функція ---
def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.PHOTO, handle_image))

    application.run_polling()

if __name__ == '__main__':
    main()