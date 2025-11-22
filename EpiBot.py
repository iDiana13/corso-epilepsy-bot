from sqlalchemy import create_engine, text
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

def dogs_menu_text(lang: str = "ru") -> str:
    if lang == "en":
        return (
            "Dog menu.\n"
            "Later here will be:\n"
            "• Add dog\n"
            "• Find dog"
        )
    else:
        return (
            "Меню работы с собаками.\n"
            "Позже здесь будут:\n"
            "• Добавить собаку\n"
            "• Найти собаку"
        )


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
           kb.add(
        types.InlineKeyboardButton(yes_text, callback_data=CB_ADD_CANCEL_YES),
        types.InlineKeyboardButton(no_text, callback_data=CB_ADD_CANCEL_NO),
    )

    return kb


# --- FSM for add case ---

ADD_STATE_DOG = "dog"
ADD_STATE_DAM = "dam"
ADD_STATE_SIRE = "sire"
ADD_STATE_SEX = "sex"
ADD_STATE_BIRTH = "birth_date"

ADD_SUBSTATE_EMPTY_CONFIRM = "empty_confirm"

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

def dogs_menu_text(lang: str = "ru") -> str:
    if lang == "en":
        return (
            "Dog menu.\n"
            "Later here will be:\n"
            "• Add dog\n"
            "• Find dog"
        )
    else:
        return (
            "Меню работы с собаками.\n"
            "Позже здесь будут:\n"
            "• Добавить собаку\n"
            "• Найти собаку"
        )


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
        types.inlineKeyboardButton(no_text, callback_data=CB_ADD_CANCEL_NO),
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

    # сбрасываем состояние ввода
    user_add_case_state.pop(uid, None)
    user_add_case_data.pop(uid, None)

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
    lang = user_lang.get(uid, "ru")

    user_add_case_state[uid] = "dog_name"
    user_add_case_data[uid] = {}

    if lang == "en":
        text = (
            "Please enter the dog's full registered name in Latin letters "
            "exactly as written in the pedigree."
        )
    else:
        text = (
            "Пожалуйста, введите полную кличку собаки латиницей, "
            "точно так как она указана в родословной."
        )

    await message.answer(text)


@dp.message_handler(lambda m: user_add_case_state.get(m.from_user.id) == "dog_name")
async def handle_add_case_dog_name(message: types.Message):
    uid = message.from_user.id
    lang = user_lang.get(uid, "ru")

    user_add_case_data.setdefault(uid, {})["dog_name"] = message.text.strip()
    user_add_case_state[uid] = "dam_name"

    if lang == "en":
        text = (
            "Enter the dam's name (mother) in Latin letters "
            "exactly as written in the pedigree."
        )
    else:
        text = (
            "Введите имя мамы латиницей, "
            "точно так как оно указано в родословной."
        )

    await message.answer(text)


@dp.message_handler(lambda m: user_add_case_state.get(m.from_user.id) == "dam_name")
async def handle_add_case_dam_name(message: types.Message):
    uid = message.from_user.id
    lang = user_lang.get(uid, "ru")

    user_add_case_data.setdefault(uid, {})["dam_name"] = message.text.strip()
    user_add_case_state[uid] = "sire_name"

    if lang == "en":
        text = (
            "Enter the sire's name (father) in Latin letters "
            "exactly as written in the pedigree."
        )
    else:
        text = (
            "Введите имя папы латиницей, "
            "точно так как оно указано в родословной."
        )

    await message.answer(text)


@dp.message_handler(lambda m: user_add_case_state.get(m.from_user.id) == "sire_name")
async def handle_add_case_sire_name(message: types.Message):
    uid = message.from_user.id
    lang = user_lang.get(uid, "ru")

    user_add_case_data.setdefault(uid, {})["sire_name"] = message.text.strip()

    data = user_add_case_data.get(uid, {}).copy()
    logging.info(f"Add case basic pedigree data from {uid}: {data}")

    # --- Сохраняем в базу ---
    save_case(
        user_id=uid,
        dog=data.get("dog_name"),
        dam=data.get("dam_name"),
        sire=data.get("sire_name"),
    )

    # --- Очищаем временные данные ---
    user_add_case_state.pop(uid, None)
    user_add_case_data.pop(uid, None)

    if lang == "en":
        text = (
            "Thank you. The basic pedigree data has been recorded.\n"
            "Later we will ask for more details about the case."
        )
        markup = main_menu_markup("en")
    else:
        text = (
            "Спасибо. Основные данные по родословной сохранены.\n"
            "Позже бот попросит у вас дополнительные детали по случаю."
        )
        markup = main_menu_markup("ru")

    await message.answer(text, reply_markup=markup)


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



























