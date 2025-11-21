# EpiBot.py
# Requirements: aiogram==2.25.1
# Token must be provided via env var EPIBOT_TOKEN

import os
import time
import logging
from aiogram import Bot, Dispatcher, executor, types

# --- Token ---

API_TOKEN = os.getenv("EPIBOT_TOKEN")

if not API_TOKEN:
    raise RuntimeError("EPIBOT_TOKEN is missing. Set it in Render -> Environment Variables.")

# --- Lockfile to prevent multiple instances ---

LOCKFILE = "/tmp/epibot.lock"

# --- In-memory language storage (per process only) ---

user_lang = {}

# --- Logging ---

LOGFILE = "epibot.log"
logging.basicConfig(
    level=logging.INFO,
    filename=LOGFILE,
    format="%(asctime)s %(levelname)s %(message)s",
)
logging.getLogger().addHandler(logging.StreamHandler())

# --- Bot init ---

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)


# --- Keyboards & texts ---

def language_keyboard() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("Русский", "English")
    return kb


def main_menu_markup(lang: str = "ru") -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if lang == "en":
        kb.row("📄 Help", "📂 Add case")
    else:
        kb.row("📄 Помощь", "📂 Добавить историю")
    return kb




# --- Main welcome texts ---

def get_welcome_text(lang: str = "ru") -> str:
    if lang == "en":
        return (
            "Hello. I am a bot that helps you check Cane Corso pedigrees for epilepsy cases found in the bloodline.\n\n"
            "☯︎ Dear user,\n"
            "epilepsy in the Cane Corso breed is unfortunately not rare. If you do not find information in our database, "
            "it does not mean that epilepsy has never occurred in this pedigree. This may simply mean that I am not aware of any such cases.\n\n"
            "If you do find epilepsy cases in the database, this also does not confirm any genetic origin. "
            "At this time, there is no genetic test of any kind that can diagnose epilepsy or determine whether it is inherited. "
            "Epilepsy may have hereditary or acquired causes.\n\n"
            "Choose an option from the menu below."
        )

    return (
        "Привет! Я бот, который помогает проверять родословные Cane Corso на наличие эпилепсии в линиях.\n\n"
        "☯︎ Дорогой пользователь,\n"
        "эпилепсия в породе Cane Corso, к сожалению, встречается нередко. Если ты не нашёл информацию в нашей базе, "
        "это не означает, что в данной родословной эпилепсии не было. Это может значить, что мне такие случаи не известны.\n\n"
        "Если ты обнаружишь упоминание об эпилепсии в базе, это также не подтверждает её генетическое происхождение. "
        "На сегодняшний день не существует никакого генетического теста, который мог бы определить эпилепсию или её наследование. "
        "Эпилепсия может иметь как наследственные, так и приобретённые причины.\n\n"
        "Выбери действие в меню ниже."
    )


# --- /start and /menu ---

@dp.message_handler(commands=["start", "menu"])
async def cmd_start(message: types.Message):
    """Always show language choice upon /start or /menu."""
    if message.chat.type != "private":
        logging.info(f"Ignoring /start from chat type={message.chat.type}")
        return

    uid = message.from_user.id
    logging.info(f"/start from {uid}")

    await message.answer(
        "Пожалуйста, выберите язык.\nPlease choose your language.",
        reply_markup=language_keyboard(),
    )


# --- Russian language selection ---

@dp.message_handler(lambda m: m.text == "Русский")
async def set_ru(message: types.Message):
    if message.chat.type != "private":
        return

    uid = message.from_user.id
    user_lang[uid] = "ru"
    logging.info(f"Language RU set for {uid}")

    await message.answer(
        get_welcome_text("ru"),
        reply_markup=main_menu_markup("ru"),
    )


# --- English language selection ---

@dp.message_handler(lambda m: m.text == "English")
async def set_en(message: types.Message):
    if message.chat.type != "private":
        return

    uid = message.from_user.id
    user_lang[uid] = "en"
    logging.info(f"Language EN set for {uid}")

    await message.answer(
        get_welcome_text("en"),
        reply_markup=main_menu_markup("en"),
    )


# --- Add case -> show consent text (RU / EN) ---

@dp.message_handler(lambda m: m.text in ["📂 Добавить историю", "📂 Add case"])
async def handle_add_case_with_consent(message: types.Message):
    uid = message.from_user.id
    lang = user_lang.get(uid, "ru")

    if lang == "ru":
        text = (
            "Соглашение на обработку информации и материалов:\n\n"
            "Нажимая продолжить и отправляя историю, вы подтверждаете, что:\n"
            "• отправляете информацию добровольно и по собственной инициативе\n"
            "• разрешаете её хранение и обработку в рамках проекта по эпилепсии у Cane Corso\n"
            "• понимаете, что данные могут использоваться в обезличенном виде для анализа и статистики\n"
            "• не отправляете персональные данные третьих лиц без их согласия\n\n"
            "Если вы согласны, введите латинскими буквами полную кличку собаки. Проверьте, чтобы не было ошибок, и следуйте дальнейшим указаниям.\n"
            "Если не согласны, просто не отправляйте данные и вернитесь в меню."
        )
        else:
        text = (
            "Consent to process information and materials:\n\n"
            "By continuing and sending a case, you confirm that:\n"
            "• you provide information voluntarily and on your own initiative\n"
            "• you allow it to be stored and processed within the Cane Corso epilepsy project\n"
            "• the data may be used in anonymized form for analysis and statistics\n"
            "• you will not send personal data of third parties without their consent\n\n"
            "If you agree, please enter the dog’s full name in Latin characters. Make sure there are no mistakes and follow the next instructions.\n"
            "If you do not agree, simply do not send any data and return to the menu."
        )

    await message.answer(text)







# --- Fallback for unknown input ---

@dp.message_handler()
async def fallback_log(message: types.Message):
    logging.info(
        f"fallback from {message.from_user.id} ({message.from_user.username}) "
        f"chat={message.chat.id} type={message.chat.type}: {message.text!r}"
    )

    if message.from_user.is_bot:
        return

    if message.chat.type != "private":
        return

    uid = message.from_user.id
    lang = user_lang.get(uid, "ru")

    if lang == "ru":
        await message.answer("Я не понял. Нажми /start, выбери язык и затем используй меню.")
    else:
        await message.answer("I didn't understand. Send /start, choose language and use the menu.")


from threading import Thread
from flask import Flask

app = Flask(__name__)

@app.route("/")
def healthcheck():
    return "OK", 200

def run_flask():
    app.run(host="0.0.0.0", port=10000)
    

# --- main ---

def main():
    # Prevent double-run
    try:
        if os.path.exists(LOCKFILE):
            with open(LOCKFILE, "r") as f:
                pid = f.read().strip()
            logging.info(f"LOCKFILE exists, PID={pid}. Stopping.")
            return

        with open(LOCKFILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logging.exception("Lockfile error: %s", e)
        return

    logging.info(f"Bot start PID={os.getpid()} token_suffix={API_TOKEN[-4:]}")

    try:
        Thread(target=run_flask, daemon=True).start()
        executor.start_polling(dp, skip_updates=True)
    finally:
        try:
            if os.path.exists(LOCKFILE):
                os.remove(LOCKFILE)
        except Exception:
            pass


if __name__ == "__main__":
    main()




















