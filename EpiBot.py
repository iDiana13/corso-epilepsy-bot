import os
import logging

from sqlalchemy import create_engine, text
from aiogram import Bot, Dispatcher, executor, types
import re
from datetime import datetime


# --- Admin users ---
ADMINS = {5059876030}

# --- Database init ---
engine = create_engine("sqlite:///epibot.db", echo=False)

# --- Ensure table exists ---
with engine.connect() as connection:
    connection.execute(text("""
    CREATE TABLE IF NOT EXISTS cases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        dog_name TEXT,
        dog_pedigree_url TEXT,
        dam_name TEXT,
        dam_pedigree_url TEXT,
        sire_name TEXT,
        sire_pedigree_url TEXT,
        sex TEXT,
        birth_date TEXT,
        timestamp TEXT
    );
    """))
    connection.commit()


# --- Token ---

API_TOKEN = os.getenv("EPIBOT_TOKEN")

if not API_TOKEN:
    raise RuntimeError("EPIBOT_TOKEN is missing. Set it in Render -> Environment Variables.")

# --- Lockfile to prevent multiple instances ---

LOCKFILE = "/tmp/epibot.lock"

# --- In-memory language storage (per process only) ---

user_lang = {}             # язык пользователя
user_add_case_state = {}   # состояние анкеты по собаке
user_add_case_data = {}    # временные данные по собакам
user_add_case_substate = {}      # подстатус, например подтверждение пустого поля
user_add_case_empty_field = {}   # какое поле сейчас подтверждаем как пустое
user_search_state = {}        # uid -> "dog_name" or None
user_search_results = {}      # uid -> list of last search results


# --- FSM for add case ---

ADD_STATE_DOG = "dog"
ADD_STATE_DAM = "dam"
ADD_STATE_SIRE = "sire"
ADD_STATE_SEX = "sex"
ADD_STATE_BIRTH = "birth_date"

ADD_SUBSTATE_EMPTY_CONFIRM = "empty_confirm"
ADD_STATE_CONFIRM = "confirm"

PEDIGREE_PREFIX = "https://canecorsopedigree.com/"

CB_ADD_BACK = "add_back"
CB_ADD_CANCEL = "add_cancel"
CB_ADD_NEXT = "add_next"

CB_ADD_CANCEL_YES = "add_cancel_yes"
CB_ADD_CANCEL_NO = "add_cancel_no"

CB_ADD_EMPTY_YES = "add_empty_yes"
CB_ADD_EMPTY_NO = "add_empty_no"

CB_ADD_SEX_MALE = "add_sex_male"
CB_ADD_SEX_FEMALE = "add_sex_female"

CB_ADD_CONFIRM_SAVE = "add_confirm_save"

def dogs_menu_text(lang: str = "ru") -> str:
    if lang == "en":
        return (
            "Dog menu.\n\n"
            "You can add a new dog or search an existing one."
        )
    else:
        return (
            "Меню работы с собаками.\n\n"
            "Вы можете добавить новую собаку или найти уже сохранённую."
        )

def dogs_menu_keyboard(lang: str = "ru") -> types.InlineKeyboardMarkup:
    if lang == "en":
        add_text = "Add dog"
        search_text = "Find dog"
    else:
        add_text = "Добавить собаку"
        search_text = "Найти собаку"

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(add_text, callback_data="dogs_add"))
    kb.add(types.InlineKeyboardButton(search_text, callback_data="dogs_search"))
    return kb


def add_case_inline_nav(lang: str = "ru") -> types.InlineKeyboardMarkup:
    if lang == "en":
        back_text = "Back"
        cancel_text = "Cancel"
        next_text = "Next"
    else:
        back_text = "Назад"
        cancel_text = "Отмена"
        next_text = "Вперёд"

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton(back_text, callback_data=CB_ADD_BACK),
        types.InlineKeyboardButton(cancel_text, callback_data=CB_ADD_CANCEL),
        types.InlineKeyboardButton(next_text, callback_data=CB_ADD_NEXT),
    )
    return kb


def add_case_inline_nav_with_sex(lang: str = "ru") -> types.InlineKeyboardMarkup:
    if lang == "en":
        back_text = "Back"
        cancel_text = "Cancel"
        next_text = "Next"
        male_text = "Male"
        female_text = "Female"
    else:
        back_text = "Назад"
        cancel_text = "Отмена"
        next_text = "Вперёд"
        male_text = "Кобель"
        female_text = "Сука"

    

    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton(back_text, callback_data=CB_ADD_BACK),
        types.InlineKeyboardButton(cancel_text, callback_data=CB_ADD_CANCEL),
        types.InlineKeyboardButton(next_text, callback_data=CB_ADD_NEXT),
    )
    kb.row(
        types.InlineKeyboardButton(male_text, callback_data=CB_ADD_SEX_MALE),
        types.InlineKeyboardButton(female_text, callback_data=CB_ADD_SEX_FEMALE),
    )
    return kb

def add_case_inline_nav_confirm(lang: str = "ru") -> types.InlineKeyboardMarkup:
    if lang == "en":
        back_text = "Back"
        cancel_text = "Cancel"
        save_text = "Save"
    else:
        back_text = "Назад"
        cancel_text = "Отмена"
        save_text = "Сохранить"

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton(back_text, callback_data=CB_ADD_BACK),
        types.InlineKeyboardButton(cancel_text, callback_data=CB_ADD_CANCEL),
        types.InlineKeyboardButton(save_text, callback_data=CB_ADD_CONFIRM_SAVE),
    )
    return kb


def empty_field_confirm_keyboard(lang: str = "ru") -> types.InlineKeyboardMarkup:
    if lang == "en":
        yes_text = "Yes, leave empty"
        no_text = "No, go back"
    else:
        yes_text = "Да, оставить пустым"
        no_text = "Нет, вернуться к вводу"

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton(yes_text, callback_data=CB_ADD_EMPTY_YES),
        types.InlineKeyboardButton(no_text, callback_data=CB_ADD_EMPTY_NO),
    )
    return kb

def cancel_confirm_keyboard(lang: str = "ru") -> types.InlineKeyboardMarkup:
    if lang == "en":
        yes_text = "Yes"
        no_text = "No"
    else:
        yes_text = "Да"
        no_text = "Нет"

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton(yes_text, callback_data=CB_ADD_CANCEL_YES),
        types.InlineKeyboardButton(no_text, callback_data=CB_ADD_CANCEL_NO),
    )
    return kb



def get_user_lang(uid: int) -> str:
    lang = user_lang.get(uid, "ru")
    return "en" if lang == "en" else "ru"


def is_valid_birth_date(s: str) -> bool:
    if not re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", s):
        return False
    year = int(s[0:4])
    month = int(s[5:7])
    day = int(s[8:10])
    try:
        datetime(year, month, day)
    except ValueError:
        return False
    return True


def is_valid_pedigree_url(url: str) -> bool:
    return url.startswith(PEDIGREE_PREFIX)


def is_case_minimal_ok(data: dict) -> bool:
    dog_name = (data.get("dog_name") or "").strip()
    if not dog_name:
        return False

    links = [
        (data.get("dog_pedigree_url") or "").strip(),
        (data.get("dam_pedigree_url") or "").strip(),
        (data.get("sire_pedigree_url") or "").strip(),
    ]
    has_link = any(links)

    if has_link:
        return True

    dam_name = (data.get("dam_name") or "").strip()
    sire_name = (data.get("sire_name") or "").strip()
    if not dam_name or not sire_name:
        return False

    return True

def dog_step_intro(lang: str) -> str:
    if lang == "en":
        return (
            "Step 1. Dog.\n\n"
            "Send the dog's name in one message.\n"
            "If there is a pedigree link, send it as a separate message.\n"
            "When you finish this block, press “Next”."
        )
    else:
        return (
            "Шаг 1. Собака.\n\n"
            "Сначала отправьте кличку собаки одним сообщением.\n"
            "Если есть ссылка на родословную, отправьте её отдельным сообщением.\n"
            "Когда закончите с этим блоком (имя и ссылка), нажмите «Вперёд»."
        )


def dam_step_intro(lang: str) -> str:
    if lang == "en":
        return (
            "Step 2. Dam (mother).\n\n"
            "Send the dam's name in one message.\n"
            "If there is a pedigree link, send it as a separate message.\n"
            "When you finish this block, press “Next”."
        )
    else:
        return (
            "Шаг 2. Мать.\n\n"
            "Отправьте кличку мамы одним сообщением.\n"
            "Если есть ссылка на родословную мамы, отправьте её отдельным сообщением.\n"
            "Когда закончите с этим блоком, нажмите «Вперёд»."
        )


def sire_step_intro(lang: str) -> str:
    if lang == "en":
        return (
            "Step 3. Sire (father).\n\n"
            "Send the sire's name in one message.\n"
            "If there is a pedigree link, send it as a separate message.\n"
            "When you finish this block, press “Next”."
        )
    else:
        return (
            "Шаг 3. Отец.\n\n"
            "Отправьте кличку папы одним сообщением.\n"
            "Если есть ссылка на родословную папы, отправьте её отдельным сообщением.\n"
            "Когда закончите с этим блоком, нажмите «Вперёд»."
        )


def sex_step_intro(lang: str) -> str:
    if lang == "en":
        return (
            "Step 4. Sex.\n\n"
            "Choose the dog's sex using the buttons.\n"
            "If you want to skip this field, press “Next”."
        )
    else:
        return (
            "Шаг 4. Пол.\n\n"
            "Выберите пол собаки с помощью кнопок ниже.\n"
            "Если хотите пропустить поле, нажмите «Вперёд»."
        )


def birth_step_intro(lang: str) -> str:
    if lang == "en":
        return (
            "Step 5. Date of birth.\n\n"
            "Enter the date in the format YYYY.MM.DD, for example: 2021.03.27.\n"
            "If you do not know the exact date, you can leave the field empty and press “Next”."
        )
    else:
        return (
            "Шаг 5. Дата рождения.\n\n"
            "Введите дату рождения в формате ГГГГ.ММ.ДД, например: 2021.03.27.\n"
            "Если точной даты нет, можно оставить поле пустым и нажать «Вперёд»."
        )


def build_confirm_text(lang: str, data: dict) -> str:
    def val(v, default_ru: str, default_en: str) -> str:
        if not v or not str(v).strip():
            return default_ru if lang == "ru" else default_en
        return str(v).strip()

    dog_name = val(data.get("dog_name"), "не указано", "not specified")
    dam_name = val(data.get("dam_name"), "не указано", "not specified")
    sire_name = val(data.get("sire_name"), "не указано", "not specified")
    sex = val(data.get("sex"), "не указан", "not specified")
    birth_date = val(data.get("birth_date"), "не указана", "not specified")

    dog_url = val(data.get("dog_pedigree_url"), "нет", "none")
    dam_url = val(data.get("dam_pedigree_url"), "нет", "none")
    sire_url = val(data.get("sire_pedigree_url"), "нет", "none")

    if lang == "en":
        lines = [
            "Check the data before saving:",
            "",
            f"1. Dog: {dog_name}",
            f"2. Dam: {dam_name}",
            f"3. Sire: {sire_name}",
            f"4. Sex: {sex}",
            f"5. Birth date: {birth_date}",
            "6. Pedigree links:",
            f"   • Dog: {dog_url}",
            f"   • Dam: {dam_url}",
            f"   • Sire: {sire_url}",
        ]
    else:
        lines = [
            "Проверим данные перед сохранением:",
            "",
            f"1. Собака: {dog_name}",
            f"2. Мать: {dam_name}",
            f"3. Отец: {sire_name}",
            f"4. Пол: {sex}",
            f"5. Дата рождения: {birth_date}",
            "6. Ссылки:",
            f"   • Собака: {dog_url}",
            f"   • Мать: {dam_url}",
            f"   • Отец: {sire_url}",
        ]

    return "\n".join(lines)


def empty_field_warning_text(lang: str) -> str:
    if lang == "en":
        return (
            "This field is currently empty. Missing data can reduce the quality of the database.\n"
            "Do you want to leave the field empty and continue?"
        )
    else:
        return (
            "Это поле сейчас пустое. Незаполненные данные могут снизить качество базы.\n"
            "Вы хотите оставить поле пустым и продолжить?"
        )


def cancel_confirm_text(lang: str) -> str:
    if lang == "en":
        return "Do you really want to cancel and go to the dog menu?"
    else:
        return "Вы действительно хотите отменить заполнение и выйти в меню собак?"


def dog_name_required_text(lang: str) -> str:
    if lang == "en":
        return "Dog name is required. Please enter the name to continue."
    else:
        return "Кличка собаки обязательна. Укажите кличку, чтобы продолжить."


def date_format_error_text(lang: str) -> str:
    if lang == "en":
        return (
            "Enter the date in the format YYYY.MM.DD,\n"
            "for example: 2021.03.27"
        )
    else:
        return (
            "Введите дату рождения в формате ГГГГ.ММ.ДД,\n"
            "например: 2021.03.27"
        )


def url_error_text(lang: str) -> str:
    if lang == "en":
        return "The link must be from canecorsopedigree.com"
    else:
        return "Ссылка должна быть с сайта canecorsopedigree.com"


def insufficient_data_text(lang: str) -> str:
    if lang == "en":
        return (
            "There is not enough data to save this record.\n\n"
            "To save, you need:\n"
            "• dog name, and\n"
            "• either at least one pedigree link (dog or parents),\n"
            "• or both dam and sire names if there are no links."
        )
    else:
        return (
            "Сейчас данных недостаточно для сохранения записи.\n\n"
            "Для сохранения записи нужно:\n"
            "• указать кличку собаки, и\n"
            "• либо хотя бы одну ссылку на родословную (собаки или родителей),\n"
            "• либо кличку матери и кличку отца, если ссылок нет."
        )

async def send_dogs_menu_from_message(message: types.Message, uid: int):
    lang = get_user_lang(uid)

    # reset state
    user_add_case_state.pop(uid, None)
    user_add_case_data.pop(uid, None)
    user_add_case_substate.pop(uid, None)
    user_add_case_empty_field.pop(uid, None)
    user_search_state.pop(uid, None)
    user_search_results.pop(uid, None)

    await message.answer(
        dogs_menu_text(lang),
        reply_markup=dogs_menu_keyboard(lang),
    )


async def send_dogs_menu_from_query(query: types.CallbackQuery, uid: int):
    lang = get_user_lang(uid)

    # reset state
    user_add_case_state.pop(uid, None)
    user_add_case_data.pop(uid, None)
    user_add_case_substate.pop(uid, None)
    user_add_case_empty_field.pop(uid, None)
    user_search_state.pop(uid, None)
    user_search_results.pop(uid, None)

    await query.message.reply_text(
        dogs_menu_text(lang),
        reply_markup=dogs_menu_keyboard(lang),
    )
async def start_dog_search(query: types.CallbackQuery, uid: int):
    lang = get_user_lang(uid)

    # reset add case state when starting search
    user_add_case_state.pop(uid, None)
    user_add_case_data.pop(uid, None)
    user_add_case_substate.pop(uid, None)
    user_add_case_empty_field.pop(uid, None)

    user_search_state[uid] = "dog_name"
    user_search_results.pop(uid, None)

    if lang == "en":
        text = (
            "Dog search.\n\n"
            "Send the dog name or a part of it.\n"
            "The search is case insensitive. If there are several matches, I will show a list."
        )
    else:
        text = (
            "Поиск собаки.\n\n"
            "Отправьте имя собаки или его часть.\n"
            "Поиск нечувствителен к регистру. Если найдётся несколько вариантов, я покажу список."
        )

    await query.message.reply_text(text)


async def send_search_results_list(message: types.Message, results: list, lang: str):
    if lang == "en":
        header = "Several dogs found:\n"
        dam_label = "dam"
        sire_label = "sire"
        back_text = "Back to dog menu"
    else:
        header = "Найдено несколько собак:\n"
        dam_label = "мать"
        sire_label = "отец"
        back_text = "Назад в меню собак"

    lines = [header, ""]
    for idx, row in enumerate(results, start=1):
        dam_name = row["dam_name"] or ("не указано" if lang == "ru" else "not specified")
        sire_name = row["sire_name"] or ("не указано" if lang == "ru" else "not specified")
        line = f"{idx}. {row['dog_name']} ({dam_label}: {dam_name}, {sire_label}: {sire_name})"
        lines.append(line)

    text = "\n".join(lines)

    kb = types.InlineKeyboardMarkup()
    for row in results:
        cb = f"case_show_{row['id']}"
        kb.add(types.InlineKeyboardButton(row["dog_name"], callback_data=cb))

    kb.add(types.InlineKeyboardButton(back_text, callback_data="dogs_search_back"))

    await message.answer(text, reply_markup=kb)


async def show_dog_card(message: types.Message, case_id: int, uid: int, lang: str):
    with engine.connect() as connection:
        result = connection.execute(
            text(
                """
                SELECT dog_name, sex, birth_date,
                       dam_name, sire_name,
                       dog_pedigree_url, dam_pedigree_url, sire_pedigree_url
                FROM cases
                WHERE id = :cid
                """
            ),
            {"cid": case_id},
        )
        row = result.fetchone()

    if not row:
        if lang == "en":
            await message.answer("Record not found.")
        else:
            await message.answer("Запись не найдена.")
        return

    (
        dog_name,
        sex,
        birth_date,
        dam_name,
        sire_name,
        dog_url,
        dam_url,
        sire_url,
    ) = row

    def v(val, default_ru: str, default_en: str) -> str:
        if not val or not str(val).strip():
            return default_ru if lang == "ru" else default_en
        return str(val).strip()

    dog_name = v(dog_name, "не указано", "not specified")
    sex = v(sex, "не указан", "not specified")
    birth_date = v(birth_date, "не указана", "not specified")
    dam_name = v(dam_name, "не указано", "not specified")
    sire_name = v(sire_name, "не указано", "not specified")
    dog_url = v(dog_url, "нет", "none")
    dam_url = v(dam_url, "нет", "none")
    sire_url = v(sire_url, "нет", "none")

    if lang == "en":
        lines = [
            "Dog card:",
            "",
            f"Name: {dog_name}",
            f"Sex: {sex}",
            f"Birth date: {birth_date}",
            "",
            f"Dam: {dam_name}",
            f"Sire: {sire_name}",
            "",
            "Pedigree links:",
            f"• Dog: {dog_url}",
            f"• Dam: {dam_url}",
            f"• Sire: {sire_url}",
        ]
        back_results_text = "Back to results"
        back_menu_text = "Back to dog menu"
    else:
        lines = [
            "Карточка собаки:",
            "",
            f"Имя: {dog_name}",
            f"Пол: {sex}",
            f"Дата рождения: {birth_date}",
            "",
            f"Мать: {dam_name}",
            f"Отец: {sire_name}",
            "",
            "Ссылки на родословные:",
            f"• Собака: {dog_url}",
            f"• Мать: {dam_url}",
            f"• Отец: {sire_url}",
        ]
        back_results_text = "Назад к результатам"
        back_menu_text = "Назад в меню собак"

    text_out = "\n".join(lines)

    kb = types.InlineKeyboardMarkup()
    results = user_search_results.get(uid) or []
    if results and len(results) > 1:
        kb.add(types.InlineKeyboardButton(back_results_text, callback_data="search_back_to_results"))
    kb.add(types.InlineKeyboardButton(back_menu_text, callback_data="dogs_search_back"))

    await message.answer(text_out, reply_markup=kb)



# --- Database helper functions ---

def save_case(
    user_id: int,
    dog_name: str,
    dog_pedigree_url: str,
    dam_name: str,
    dam_pedigree_url: str,
    sire_name: str,
    sire_pedigree_url: str,
    sex: str,
    birth_date: str,
):
    """Сохраняет данные по собаке в SQLite."""
    with engine.connect() as connection:
        connection.execute(
            text(
                """
                INSERT INTO cases (
                    user_id,
                    dog_name,
                    dog_pedigree_url,
                    dam_name,
                    dam_pedigree_url,
                    sire_name,
                    sire_pedigree_url,
                    sex,
                    birth_date,
                    timestamp
                )
                VALUES (
                    :uid,
                    :dog_name,
                    :dog_pedigree_url,
                    :dam_name,
                    :dam_pedigree_url,
                    :sire_name,
                    :sire_pedigree_url,
                    :sex,
                    :birth_date,
                    datetime('now')
                )
                """
            ),
            {
                "uid": user_id,
                "dog_name": dog_name,
                "dog_pedigree_url": dog_pedigree_url,
                "dam_name": dam_name,
                "dam_pedigree_url": dam_pedigree_url,
                "sire_name": sire_name,
                "sire_pedigree_url": sire_pedigree_url,
                "sex": sex,
                "birth_date": birth_date,
            },
        )
        connection.commit()
    logging.info(f"Saved case for user={user_id}, dog='{dog_name}'")



def delete_case_by_dog_name(name: str):
    """Удаляет записи из SQLite по имени собаки."""
    with engine.connect() as connection:
        connection.execute(
            text("DELETE FROM cases WHERE dog_name = :name"),
            {"name": name},
        )
        connection.commit()
    logging.info(f"Deleted cases with dog_name='{name}'")


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

def add_case_nav_keyboard(lang: str = "ru") -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if lang == "en":
        kb.row("Back to bot menu", "I continue")
    else:
        kb.row("Назад в меню бота", "Продолжаю")
    return kb

def add_case_back_only_keyboard(lang: str = "ru") -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if lang == "en":
        kb.row("Back to bot menu")
    else:
        kb.row("Назад в меню бота")
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
            "Если вы согласны, нажмите «Продолжаю».\n"
            "Если не согласны, нажмите «Назад в меню бота» или просто не отправляйте данные."
        )
    else:
        text = (
            "Consent to process information and materials:\n\n"
            "By continuing and sending a case, you confirm that:\n"
            "• you provide information voluntarily and on your own initiative\n"
            "• you allow it to be stored and processed within the Cane Corso epilepsy project\n"
            "• the data may be used in anonymized form for analysis and statistics\n"
            "• you will not send personal data of third parties without their consent\n\n"
            "If you agree, press “I continue”.\n"
            "If you do not agree, press “Back to bot menu” or simply do not send any data."
        )

    await message.answer(text, reply_markup=add_case_nav_keyboard(lang))


# --- Add case step-by-step input (dog, dam, sire) ---

# user_add_case_state[uid] = "dog_name" | "dam_name" | "sire_name"


@dp.message_handler(lambda m: m.text in ["Назад в меню бота", "Back to bot menu"])
async def handle_back_to_bot_menu(message: types.Message):
    uid = message.from_user.id
    lang = user_lang.get(uid, "ru")

    # reset add case and search state
    user_add_case_state.pop(uid, None)
    user_add_case_data.pop(uid, None)
    user_add_case_substate.pop(uid, None)
    user_add_case_empty_field.pop(uid, None)
    user_search_state.pop(uid, None)
    user_search_results.pop(uid, None)

    if lang == "en":
        await message.answer(
            get_welcome_text("en"),
            reply_markup=main_menu_markup("en"),
        )
    else:
        await message.answer(
            get_welcome_text("ru"),
            reply_markup=main_menu_markup("ru"),
        )


@dp.message_handler(lambda m: m.text in ["Продолжаю", "I continue"])
async def handle_add_case_start_steps(message: types.Message):
    uid = message.from_user.id
    lang = get_user_lang(uid)

    # do not restart form if it is already in progress
    if user_add_case_state.get(uid) is not None:
        return

    user_add_case_state[uid] = ADD_STATE_DOG
    user_add_case_substate[uid] = None
    user_add_case_empty_field[uid] = None
    user_add_case_data[uid] = {
        "dog_name": "",
        "dog_pedigree_url": "",
        "dam_name": "",
        "dam_pedigree_url": "",
        "sire_name": "",
        "sire_pedigree_url": "",
        "sex": "",
        "birth_date": "",
    }

    # set reply keyboard to single "Back to bot menu" button
    await message.answer(
        " ",
        reply_markup=add_case_back_only_keyboard(lang),
    )

    # send first step with inline navigation
    await message.answer(
        dog_step_intro(lang),
        reply_markup=add_case_inline_nav(lang),
    )

@dp.message_handler(lambda m: user_search_state.get(m.from_user.id) == "dog_name")
async def handle_search_message(message: types.Message):
    uid = message.from_user.id
    lang = get_user_lang(uid)

    q = (message.text or "").strip()
    if not q:
        if lang == "en":
            await message.answer("Please enter a search string.")
        else:
            await message.answer("Введите строку для поиска.")
        return

    with engine.connect() as connection:
        result = connection.execute(
            text(
                """
                SELECT id, dog_name, dam_name, sire_name, sex, birth_date
                FROM cases
                WHERE LOWER(dog_name) LIKE '%' || LOWER(:q) || '%'
                ORDER BY timestamp DESC
                LIMIT 20
                """
            ),
            {"q": q},
        )
        rows = result.fetchall()

    if not rows:
        if lang == "en":
            text_out = "No matches found for this query."
            repeat_text = "Repeat search"
            back_text = "Back to dog menu"
        else:
            text_out = "По этому запросу ничего не найдено."
            repeat_text = "Повторить поиск"
            back_text = "Назад в меню собак"

        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton(repeat_text, callback_data="dogs_search_repeat"))
        kb.add(types.InlineKeyboardButton(back_text, callback_data="dogs_search_back"))

        await message.answer(text_out, reply_markup=kb)
        return

    results = []
    for r in rows:
        results.append(
            {
                "id": r[0],
                "dog_name": r[1],
                "dam_name": r[2],
                "sire_name": r[3],
                "sex": r[4],
                "birth_date": r[5],
            }
        )

    user_search_results[uid] = results

    if len(results) == 1:
        await show_dog_card(message, results[0]["id"], uid, lang)
        return

    await send_search_results_list(message, results, lang)


@dp.message_handler(lambda m: user_add_case_state.get(m.from_user.id) is not None)
async def handle_add_case_message(message: types.Message):
    uid = message.from_user.id
    lang = get_user_lang(uid)
    state = user_add_case_state.get(uid)
    data = user_add_case_data.setdefault(uid, {})

    text = (message.text or "").strip()
    if not text:
        return

    # Шаг собаки: сначала имя, потом пробуем воспринимать как ссылку
    if state == ADD_STATE_DOG:
        if not data.get("dog_name"):
            data["dog_name"] = text
        else:
            if is_valid_pedigree_url(text):
                data["dog_pedigree_url"] = text
            else:
                await message.answer(url_error_text(lang))

    elif state == ADD_STATE_DAM:
        if not data.get("dam_name"):
            data["dam_name"] = text
        else:
            if is_valid_pedigree_url(text):
                data["dam_pedigree_url"] = text
            else:
                await message.answer(url_error_text(lang))

    elif state == ADD_STATE_SIRE:
        if not data.get("sire_name"):
            data["sire_name"] = text
        else:
            if is_valid_pedigree_url(text):
                data["sire_pedigree_url"] = text
            else:
                await message.answer(url_error_text(lang))

    elif state == ADD_STATE_SEX:
        # Пол выбираем только кнопками, текст игнорируем
        await message.answer(
            sex_step_intro(lang),
            reply_markup=add_case_inline_nav_with_sex(lang),
        )

    elif state == ADD_STATE_BIRTH:
        if text:
            if is_valid_birth_date(text):
                data["birth_date"] = text
            else:
                await message.answer(date_format_error_text(lang))

    user_add_case_data[uid] = data


@dp.message_handler(commands=["delete"])
async def admin_delete_case(message: types.Message):
    uid = message.from_user.id

    if uid not in ADMINS:
        await message.answer("⛔ У вас нет прав для выполнения этой команды.")
        return

    parts = message.text.split(maxsplit=1)

    if len(parts) < 2:
        await message.answer("Укажите имя собаки. Пример:\n/delete Bella")
        return

    dog_name = parts[1].strip()

    delete_case_by_dog_name(dog_name)

    await message.answer(f"✔ Запись с именем '{dog_name}' удалена (если она существовала).")

async def repaint_current_step(query: types.CallbackQuery, uid: int):
    lang = get_user_lang(uid)
    state = user_add_case_state.get(uid)
    data = user_add_case_data.setdefault(uid, {})

    # Common cases: steps 1 4
    if state == ADD_STATE_DOG:
        await query.message.edit_text(
            dog_step_intro(lang),
            reply_markup=add_case_inline_nav(lang),
        )
    elif state == ADD_STATE_DAM:
        await query.message.edit_text(
            dam_step_intro(lang),
            reply_markup=add_case_inline_nav(lang),
        )
    elif state == ADD_STATE_SIRE:
        await query.message.edit_text(
            sire_step_intro(lang),
            reply_markup=add_case_inline_nav(lang),
        )
    elif state == ADD_STATE_SEX:
        await query.message.edit_text(
            sex_step_intro(lang),
            reply_markup=add_case_inline_nav_with_sex(lang),
        )
    elif state == ADD_STATE_BIRTH:
        await query.message.edit_text(
            birth_step_intro(lang),
            reply_markup=add_case_inline_nav(lang),
        )
    elif state == ADD_STATE_CONFIRM:
        # Confirmation step
        await query.message.edit_text(
            build_confirm_text(lang, data),
            reply_markup=add_case_inline_nav_confirm(lang),
        )
    else:
        # Fallback to first step
        await query.message.edit_text(
            dog_step_intro(lang),
            reply_markup=add_case_inline_nav(lang),
        )



async def handle_add_case_back(query: types.CallbackQuery, uid: int):
    state = user_add_case_state.get(uid)

    if state == ADD_STATE_DOG:
        await send_dogs_menu_from_query(query, uid)
        return

    if state == ADD_STATE_DAM:
        user_add_case_state[uid] = ADD_STATE_DOG
    elif state == ADD_STATE_SIRE:
        user_add_case_state[uid] = ADD_STATE_DAM
    elif state == ADD_STATE_SEX:
        user_add_case_state[uid] = ADD_STATE_SIRE
    elif state == ADD_STATE_BIRTH:
        user_add_case_state[uid] = ADD_STATE_SEX

    await query.answer()
    await repaint_current_step(query, uid)


async def handle_add_case_next(query: types.CallbackQuery, uid: int):
    lang = get_user_lang(uid)
    state = user_add_case_state.get(uid)
    data = user_add_case_data.setdefault(uid, {})

    # 1. Кличка собаки обязательна
    if state == ADD_STATE_DOG:
        if not (data.get("dog_name") or "").strip():
            await query.answer()
            await query.message.reply_text(dog_name_required_text(lang))
            return

    # 2. Если это шаг даты рождения - сразу пробуем сохранить / показать ошибку
    if state == ADD_STATE_BIRTH:
        await go_next_step_or_save(query, uid)
        return

    # 3. Для остальных шагов проверяем, пустой ли блок, и при необходимости спрашиваем подтверждение
    empty_field = None

    if state == ADD_STATE_DAM:
        if not (data.get("dam_name") or "").strip() and not (data.get("dam_pedigree_url") or "").strip():
            empty_field = "dam"
    elif state == ADD_STATE_SIRE:
        if not (data.get("sire_name") or "").strip() and not (data.get("sire_pedigree_url") or "").strip():
            empty_field = "sire"
    elif state == ADD_STATE_SEX:
        if not (data.get("sex") or "").strip():
            empty_field = "sex"

    if empty_field:
        user_add_case_substate[uid] = ADD_SUBSTATE_EMPTY_CONFIRM
        user_add_case_empty_field[uid] = empty_field
        await query.answer()
        await query.message.edit_text(
            empty_field_warning_text(lang),
            reply_markup=empty_field_confirm_keyboard(lang),
        )
        return

    # 4. Просто перейти на следующий шаг, если не дата и не пустой блок
    if state == ADD_STATE_DOG:
        user_add_case_state[uid] = ADD_STATE_DAM
    elif state == ADD_STATE_DAM:
        user_add_case_state[uid] = ADD_STATE_SIRE
    elif state == ADD_STATE_SIRE:
        user_add_case_state[uid] = ADD_STATE_SEX
    elif state == ADD_STATE_SEX:
        user_add_case_state[uid] = ADD_STATE_BIRTH

    await query.answer()
    await repaint_current_step(query, uid)



async def go_next_step_or_save(query: types.CallbackQuery, uid: int):
    lang = get_user_lang(uid)
    state = user_add_case_state.get(uid)
    data = user_add_case_data.setdefault(uid, {})

    if state == ADD_STATE_DOG:
        user_add_case_state[uid] = ADD_STATE_DAM
    elif state == ADD_STATE_DAM:
        user_add_case_state[uid] = ADD_STATE_SIRE
    elif state == ADD_STATE_SIRE:
        user_add_case_state[uid] = ADD_STATE_SEX
    elif state == ADD_STATE_SEX:
        user_add_case_state[uid] = ADD_STATE_BIRTH
    elif state == ADD_STATE_BIRTH:
        # вместо сохранения переходим на шаг подтверждения
        user_add_case_state[uid] = ADD_STATE_CONFIRM
    elif state == ADD_STATE_CONFIRM:
        await query.answer()
        return

    await query.answer()
    await repaint_current_step(query, uid)


    # Это последний шаг, проверяем минимальные условия
    if not is_case_minimal_ok(data):
        await query.answer()
        await query.message.reply_text(insufficient_data_text(lang))
        return

    # Сохраняем
    save_case(
        user_id=uid,
        dog_name=(data.get("dog_name") or "").strip(),
        dog_pedigree_url=(data.get("dog_pedigree_url") or "").strip(),
        dam_name=(data.get("dam_name") or "").strip(),
        dam_pedigree_url=(data.get("dam_pedigree_url") or "").strip(),
        sire_name=(data.get("sire_name") or "").strip(),
        sire_pedigree_url=(data.get("sire_pedigree_url") or "").strip(),
        sex=(data.get("sex") or "").strip(),
        birth_date=(data.get("birth_date") or "").strip(),
    )

    # Чистим состояние
    user_add_case_state.pop(uid, None)
    user_add_case_data.pop(uid, None)
    user_add_case_substate.pop(uid, None)
    user_add_case_empty_field.pop(uid, None)

    if lang == "en":
        saved_text = "Form saved. The record has been added to the database."
    else:
        saved_text = "Анкета сохранена. Запись добавлена в базу."

    await query.answer()
    await query.message.reply_text(saved_text)
    await send_dogs_menu_from_query(query, uid)

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("add_"))
async def handle_add_case_callback(query: types.CallbackQuery):
    uid = query.from_user.id
    lang = get_user_lang(uid)
    data_str = query.data
    state = user_add_case_state.get(uid)
    data = user_add_case_data.setdefault(uid, {})
    substate = user_add_case_substate.get(uid)

    # Выбор пола
    if data_str in (CB_ADD_SEX_MALE, CB_ADD_SEX_FEMALE):
        if lang == "en":
            male_value = "Male"
            female_value = "Female"
            chosen_text = "Sex: Male." if data_str == CB_ADD_SEX_MALE else "Sex: Female."
        else:
            male_value = "Кобель"
            female_value = "Сука"
            chosen_text = "Пол: Кобель." if data_str == CB_ADD_SEX_MALE else "Пол: Сука."

        data["sex"] = male_value if data_str == CB_ADD_SEX_MALE else female_value
        user_add_case_data[uid] = data

        await query.answer()
        await query.message.edit_text(
            sex_step_intro(lang) + "\n\n" + chosen_text,
            reply_markup=add_case_inline_nav_with_sex(lang),
        )
        return

    # Отмена анкеты
    if data_str == CB_ADD_CANCEL:
        await query.answer()
        await query.message.edit_text(
            cancel_confirm_text(lang),
            reply_markup=cancel_confirm_keyboard(lang),
        )
        return

    if data_str == CB_ADD_CANCEL_YES:
        await send_dogs_menu_from_query(query, uid)
        return

    if data_str == CB_ADD_CANCEL_NO:
        await query.answer()
        await repaint_current_step(query, uid)
        return

    # Подтверждение пустого поля
    if data_str == CB_ADD_EMPTY_YES:
        user_add_case_substate[uid] = None
        field_name = user_add_case_empty_field.get(uid)
        user_add_case_empty_field[uid] = None

        # Двигаемся дальше, либо переходим к подтверждению
        await go_next_step_or_save(query, uid)
        return

    if data_str == CB_ADD_EMPTY_NO:
        user_add_case_substate[uid] = None
        user_add_case_empty_field[uid] = None
        await repaint_current_step(query, uid)
        return

    # Навигация Назад
    if data_str == CB_ADD_BACK:
        await handle_add_case_back(query, uid)
        return

    # Навигация Вперёд
    if data_str == CB_ADD_NEXT:
        await handle_add_case_next(query, uid)
        return

    # Сохранение на шаге подтверждения
    if data_str == CB_ADD_CONFIRM_SAVE:
        await handle_add_case_confirm_save(query, uid)
        return
@dp.callback_query_handler(lambda c: c.data and (c.data.startswith("dogs_") or c.data.startswith("case_show_") or c.data.startswith("search_")))
async def handle_dogs_and_search_callbacks(query: types.CallbackQuery):
    uid = query.from_user.id
    lang = get_user_lang(uid)
    data_str = query.data

    # dogs_add -> показать согласие и запустить анкету
    if data_str == "dogs_add":
        await query.answer()
        await handle_add_case_with_consent(query.message)
        return

    # dogs_search -> запуск сценария поиска
    if data_str == "dogs_search":
        await query.answer()
        await start_dog_search(query, uid)
        return

    # Назад в меню собак из поиска
    if data_str == "dogs_search_back":
        user_search_state.pop(uid, None)
        user_search_results.pop(uid, None)
        await query.answer()
        await send_dogs_menu_from_query(query, uid)
        return

    # Повторить поиск
    if data_str == "dogs_search_repeat":
        await query.answer()
        await start_dog_search(query, uid)
        return

    # Показ конкретной карточки
    if data_str.startswith("case_show_"):
        try:
            case_id = int(data_str.replace("case_show_", ""))
        except ValueError:
            await query.answer()
            return

        await query.answer()
        await show_dog_card(query.message, case_id, uid, lang)
        return

    # Назад к списку результатов
    if data_str == "search_back_to_results":
        results = user_search_results.get(uid) or []
        if results:
            await query.answer()
            await send_search_results_list(query.message, results, lang)
        else:
            await query.answer()
            await send_dogs_menu_from_query(query, uid)
        return



    # Save to DB
    save_case(
        user_id=uid,
        dog_name=(data.get("dog_name") or "").strip(),
        dog_pedigree_url=(data.get("dog_pedigree_url") or "").strip(),
        dam_name=(data.get("dam_name") or "").strip(),
        dam_pedigree_url=(data.get("dam_pedigree_url") or "").strip(),
        sire_name=(data.get("sire_name") or "").strip(),
        sire_pedigree_url=(data.get("sire_pedigree_url") or "").strip(),
        sex=(data.get("sex") or "").strip(),
        birth_date=(data.get("birth_date") or "").strip(),
    )

    # Clear state
    user_add_case_state.pop(uid, None)
    user_add_case_data.pop(uid, None)
    user_add_case_substate.pop(uid, None)
    user_add_case_empty_field.pop(uid, None)

    if lang == "en":
        saved_text = "Form saved. The record has been added to the database."
    else:
        saved_text = "Анкета сохранена. Запись добавлена в базу."

    await query.answer()
    await query.message.reply_text(saved_text)
    await send_dogs_menu_from_query(query, uid)





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








































