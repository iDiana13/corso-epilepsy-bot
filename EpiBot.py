# bot.py
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
import asyncio

# ---------- Настройки ----------
import os
API_TOKEN = os.getenv("API_TOKEN")
AVATAR_LOCAL_PATH = "/mnt/data/A_black_and_white_photograph_features_three_small_.png"

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class Lang(StatesGroup):
    choosing = State()
    chosen = State()

# Клавиатура выбора языка
kb_lang = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Русский")],
        [KeyboardButton(text="English")]
    ],
    resize_keyboard=True
)

# Основные меню (две версии)
kb_main_ru = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Поиск по линии")],
        [KeyboardButton(text="Добавить собаку")],
        [KeyboardButton(text="Помощь")],
    ],
    resize_keyboard=True
)

kb_main_en = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Pedigree Check")],
        [KeyboardButton(text="Add Dog")],
        [KeyboardButton(text="Help")],
    ],
    resize_keyboard=True
)

# ---------- START ----------
@dp.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
    await state.set_state(Lang.choosing)
    await message.answer(
        "Выберите язык.\nChoose your language.",
        reply_markup=kb_lang
    )

# ---------- Выбор языка ----------
@dp.message(Lang.choosing)
async def set_language(message: types.Message, state: FSMContext):
    lang = message.text.strip().lower()

    if lang == "русский" or lang == "russian":
        await state.update_data(lang="ru")
        await state.set_state(Lang.chosen)
        await message.answer(
            "Язык выбран: Русский.\n\n"
            "Привет. Я бот, который помогает проверять родословные Cane Corso на наличие эпилепсии в линиях.\n\n"
            "Дорогой пользователь,\n"
            "эпилепсия в породе Cane Corso, к сожалению, встречается нередко. Если ты не нашёл информацию в нашей базе, "
            "это не означает, что в данной родословной эпилепсии не было. Это может значить только то, что нам пока не "
            "известны такие случаи.\n\n"
            "Если ты обнаружишь упоминание об эпилепсии в базе, это также не подтверждает её генетическое происхождение. "
            "На сегодняшний день не существует никакого генетического теста, который мог бы определить эпилепсию или её "
            "наследование. Эпилепсия может иметь как наследственные, так и приобретённые причины.\n\n"
            "Выбери действие в меню ниже.",
            reply_markup=kb_main_ru
        )

    elif lang == "english" or lang == "en":
        await state.update_data(lang="en")
        await state.set_state(Lang.chosen)
        await message.answer(
            "Language set to English.\n\n"
            "Hello. I am a bot that helps you check Cane Corso pedigrees for epilepsy cases found in the bloodline.\n\n"
            "Dear user,\n"
            "epilepsy in the Cane Corso breed is unfortunately not rare. If you do not find information in our database, "
            "it does not mean that epilepsy has never occurred in this pedigree. It may simply mean that no such cases have "
            "been reported to us yet.\n\n"
            "If you do find epilepsy cases in the database, this also does not confirm any genetic origin. At this time, "
            "there is no genetic test of any kind that can diagnose epilepsy or determine whether it is inherited. "
            "Epilepsy may have hereditary or acquired causes.\n\n"
            "Choose an option from the menu below.",
            reply_markup=kb_main_en
        )

    else:
        await message.answer("Пожалуйста выберите язык. Please choose a language.")

# ---------- Запуск ----------
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

