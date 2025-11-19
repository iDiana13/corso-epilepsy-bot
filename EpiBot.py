# EpiBot_fixed.py
# Требует: pip install aiogram==2.25.1
# Исправления:
# - токен только через переменную окружения EPIBOT_TOKEN
# - защита от дублей инстансов через lockfile
# - ограничение отправки меню (cooldown)
# - игнорирование не приватных чатов
# - подробное логирование
# - safe_send_language вместо прямой отправки клавиатуры

import os
import time
import logging
from aiogram import Bot, Dispatcher, executor, types

# --- Токен ---
API_TOKEN = os.getenv("EPIBOT_TOKEN")

if not API_TOKEN:
    raise RuntimeError("EPIBOT_TOKEN отсутствует. Укажите токен в Render -> Environment Variables.")

# --- Lockfile для защиты от нескольких инстансов ---
LOCKFILE = "/tmp/epibot.lock"

# --- Rate limit для частых отправок меню ---
last_sent = {}
MIN_SEND_INTERVAL = 300  # 5 минут

# --- Логирование ---
LOGFILE = "epibot.log"
logging.basicConfig(level=logging.INFO, filename=LOGFILE,
                    format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger().addHandler(logging.StreamHandler())

# --- Инициализация бота ---
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)


# --- Клавиатуры и текст ---
def language_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("Русский", "English")
    return kb

def main_menu_markup(lang="ru"):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if lang == "en":
        kb.add("Help")
    else:
        kb.add("Помощь")
    return kb

def greetings_text(lang="ru"):
    if lang == "en":
        return "Please choose language."
    return "Выберите язык."


# --- Безопасная отправка меню ---
async def safe_send_language(message, text, markup):
    uid = message.from_user.id
    now = time.time()

    if last_sent.get(uid, 0) + MIN_SEND_INTERVAL > now:
        logging.info(f"Пропуск отправки меню для {uid} - cooldown")
        return

    last_sent[uid] = now
    await message.answer(text, reply_markup=markup)


# --- /start ---
@dp.message_handler(commands=["start", "menu"])
async def cmd_start(message: types.Message):

    if message.chat.type != "private":
        logging.info(f"Игнорирую /start из чата {message.chat.type}")
        return

    uid = message.from_user.id
    logging.info(f"/start от {uid}")

    if "user_lang" not in globals():
        globals()["user_lang"] = {}
    user_lang = globals()["user_lang"]

    if uid in user_lang:
        lang = user_lang[uid]
        await safe_send_language(
            message,
            "Choose an option from the menu." if lang == "en" else "Выберите опцию в меню.",
            main_menu_markup(lang)
        )
        return

    await safe_send_language(message, greetings_text("ru"), language_keyboard())


# --- Установка RU ---
@dp.message_handler(lambda m: m.text in ["Русский", "Русky", "Русский🇷🇺"])
async def set_ru(message):
    if message.chat.type != "private":
        return

    uid = message.from_user.id
    if "user_lang" not in globals():
        globals()["user_lang"] = {}
    globals()["user_lang"][uid] = "ru"

    logging.info(f"Язык RU установлен для {uid}")
    await message.answer("Язык установлен - русский", reply_markup=main_menu_markup("ru"))


# --- Установка EN ---
@dp.message_handler(lambda m: m.text in ["English"])
async def set_en(message):
    if message.chat.type != "private":
        return

    uid = message.from_user.id
    if "user_lang" not in globals():
        globals()["user_lang"] = {}
    globals()["user_lang"][uid] = "en"

    logging.info(f"Язык EN установлен для {uid}")
    await message.answer("Language set to English", reply_markup=main_menu_markup("en"))


# --- fallback ---
@dp.message_handler()
async def fallback_log(message):

    logging.info(
        f"fallback от {message.from_user.id} ({message.from_user.username}) "
        f"chat={message.chat.id} type={message.chat.type}: {message.text!r}"
    )

    if message.from_user.is_bot:
        logging.info("Игнорирую сообщение от бота")
        return

    if message.chat.type != "private":
        logging.info("Игнорирую сообщение не из private чата")
        return

    uid = message.from_user.id
    if "user_lang" not in globals():
        globals()["user_lang"] = {}

    lang = globals()["user_lang"].get(uid, "ru")

    if lang == "ru":
        await message.answer("Я не понял. Отправь /start или выбери опцию в меню.")
    else:
        await message.answer("I didn't understand. Send /start or choose an option from the menu.")


# --- Поиск возможных sleep() ---
def find_sleep_lines(project_root="."):
    import glob, re
    results = []
    for p in glob.glob(project_root + "/**/*.py", recursive=True):
        try:
            with open(p, "r", encoding="utf-8") as f:
                txt = f.read()
            for m in re.finditer(r"sleep\(", txt):
                results.append((p, m.group(0)))
        except:
            pass
    return results


# --- main ---
def main():

    # проверка двойного запуска
    try:
        if os.path.exists(LOCKFILE):
            with open(LOCKFILE, "r") as f:
                pid = f.read().strip()
            logging.info(f"LOCKFILE найден, PID={pid}. Останавливаю запуск.")
            return

        with open(LOCKFILE, "w") as f:
            f.write(str(os.getpid()))

    except Exception as e:
        logging.exception("Ошибка lockfile: %s", e)
        return

    logging.info(f"Старт бота PID={os.getpid()} token_suffix={API_TOKEN[-4:]}")
    logging.info(f"Проверка на sleep: {find_sleep_lines('.')}")

    try:
        executor.start_polling(dp, skip_updates=True)
    finally:
        try:
            if os.path.exists(LOCKFILE):
                os.remove(LOCKFILE)
        except:
            pass


if __name__ == "__main__":
    main()
