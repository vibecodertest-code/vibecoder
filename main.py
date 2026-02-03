import os
import csv
from datetime import datetime, timezone
from typing import Tuple, Optional

from dotenv import load_dotenv
load_dotenv()

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

FAQ_QUESTION = 1
LEAD_NAME = 2
LEAD_CONTACT = 3

MENU_FAQ = "FAQ"
MENU_LEAD = "Оставить заявку"
MENU_HUMAN = "Позвать человека"
MENU_BACK = "В меню"

FAQ_DATA = {
    "цена": "Цены зависят от задачи. Напишите, что именно нужно, и я передам команде.",
    "стоимость": "Стоимость зависит от объёма работ. Опишите запрос, и мы ответим точнее.",
    "адрес": "Напишите ваш город/район, и мы пришлём актуальный адрес и схему проезда.",
    "график": "Обычно работаем в будни. Уточните удобное время, и мы подтвердим.",
    "доставка": "Есть доставка. Оставьте контакт, и менеджер расскажет условия.",
    "оплата": "Возможны разные способы оплаты. Оставьте контакт, и мы уточним детали.",
    "контакты": "Оставьте ваш контакт, и мы свяжемся с вами в ближайшее время.",
}

def build_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[MENU_FAQ, MENU_LEAD], [MENU_HUMAN]],
        resize_keyboard=True,
        one_time_keyboard=False,
        selective=True,
    )

def build_back_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[MENU_BACK]],
        resize_keyboard=True,
        one_time_keyboard=False,
        selective=True,
    )

def normalize_text(s: str) -> str:
    return " ".join((s or "").strip().lower().split())

def ensure_leads_file(path: str) -> None:
    if os.path.exists(path):
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["created_at", "name", "contact", "tg_user_id", "tg_username"])

def append_lead(path: str, lead: dict) -> None:
    ensure_leads_file(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            lead.get("created_at", ""),
            lead.get("name", ""),
            lead.get("contact", ""),
            lead.get("tg_user_id", ""),
            lead.get("tg_username", ""),
        ])

def get_user_identity(update: Update) -> Tuple[str, str]:
    user = update.effective_user
    tg_user_id = str(user.id) if user and user.id is not None else ""
    tg_username = "@{}".format(user.username) if user and user.username else ""
    return tg_user_id, tg_username

async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: Optional[str] = None) -> None:
    msg = text or "Меню:"
    await update.effective_message.reply_text(msg, reply_markup=build_menu_keyboard())

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text(
        "Привет! Я FAQ-бот. Могу ответить на частые вопросы, принять заявку или позвать человека.",
        reply_markup=build_menu_keyboard(),
    )
    return ConversationHandler.END

async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.effective_message.text or "").strip()
    if text == MENU_FAQ:
        await update.effective_message.reply_text(
            "Напишите короткий вопрос или ключевое слово (например: цена, график, адрес).",
            reply_markup=build_back_keyboard(),
        )
        return FAQ_QUESTION
    if text == MENU_LEAD:
        await update.effective_message.reply_text(
            "Ок. Как вас зовут?",
            reply_markup=build_back_keyboard(),
        )
        return LEAD_NAME
    if text == MENU_HUMAN:
        admin_chat_id = context.application.bot_data["admin_chat_id"]
        tg_user_id, tg_username = get_user_identity(update)
        await update.effective_message.reply_text("Ок, передал команде.", reply_markup=build_menu_keyboard())
        await context.bot.send_message(
            chat_id=admin_chat_id,
            text="Пользователь попросил человека.\nuser_id: {}\nusername: {}".format(tg_user_id, tg_username),
        )
        return ConversationHandler.END
    await show_menu(update, context, "Выберите действие кнопкой из меню.")
    return ConversationHandler.END

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await show_menu(update, context, "Вернул в меню.")
    context.user_data.pop("lead_name", None)
    return ConversationHandler.END

async def faq_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.effective_message.text or ""
    if raw.strip() == MENU_BACK:
        return await back_to_menu(update, context)
    key = normalize_text(raw)
    answer = None
    if key:
        for k, v in FAQ_DATA.items():
            if k in key:
                answer = v
                break
        if answer is None:
            answer = FAQ_DATA.get(key)
    if answer:
        await update.effective_message.reply_text(answer, reply_markup=build_menu_keyboard())
        return ConversationHandler.END
    await update.effective_message.reply_text(
        "Не нашёл готового ответа. Можете оставить заявку, и мы свяжемся с вами.",
        reply_markup=build_menu_keyboard(),
    )
    return ConversationHandler.END

async def lead_name_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.effective_message.text or ""
    if raw.strip() == MENU_BACK:
        return await back_to_menu(update, context)
    name = raw.strip()
    if not name:
        await update.effective_message.reply_text("Имя не может быть пустым. Напишите ваше имя.", reply_markup=build_back_keyboard())
        return LEAD_NAME
    context.user_data["lead_name"] = name
    await update.effective_message.reply_text("Спасибо. Оставьте контакт (телефон/telegram/email).", reply_markup=build_back_keyboard())
    return LEAD_CONTACT

async def lead_contact_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.effective_message.text or ""
    if raw.strip() == MENU_BACK:
        context.user_data.pop("lead_name", None)
        return await back_to_menu(update, context)
    contact = raw.strip()
    if not contact:
        await update.effective_message.reply_text(
            "Контакт не может быть пустым. Введите телефон/telegram/email.",
            reply_markup=build_back_keyboard(),
        )
        return LEAD_CONTACT

    name = (context.user_data.get("lead_name", "") or "").strip()
    tg_user_id, tg_username = get_user_identity(update)
    created_at = datetime.now(timezone.utc).isoformat()

    lead = {
        "created_at": created_at,
        "name": name,
        "contact": contact,
        "tg_user_id": tg_user_id,
        "tg_username": tg_username,
    }

    leads_path = os.path.join(os.getcwd(), "leads.csv")
    append_lead(leads_path, lead)

    admin_chat_id = context.application.bot_data["admin_chat_id"]
    await context.bot.send_message(
        chat_id=admin_chat_id,
        text=(
            "Новая заявка:\n"
            "Имя: {}\n"
            "Контакт: {}\n"
            "user_id: {}\n"
            "username: {}"
        ).format(name, contact, tg_user_id, tg_username),
    )

    context.user_data.pop("lead_name", None)
    await update.effective_message.reply_text("Заявка принята! Мы свяжемся с вами.", reply_markup=build_menu_keyboard())
    return ConversationHandler.END

def read_required_env() -> Tuple[str, int]:
    token = (os.getenv("TELEGRAM_TOKEN") or "").strip()
    admin_raw = (os.getenv("ADMIN_CHAT_ID") or "").strip()
    missing = []
    if not token:
        missing.append("TELEGRAM_TOKEN")
    if not admin_raw:
        missing.append("ADMIN_CHAT_ID")
    if missing:
        names = ", ".join(missing)
        raise SystemExit(
            "Ошибка запуска: не заданы переменные окружения.\n"
            "Добавьте: {}\n"
            "Пример:\n"
            "TELEGRAM_TOKEN=...\n"
            "ADMIN_CHAT_ID=123456789".format(names)
        )
    try:
        admin_chat_id = int(admin_raw)
    except ValueError:
        raise SystemExit("Ошибка запуска: ADMIN_CHAT_ID должен быть числом (chat id администратора).")
    return token, admin_chat_id

def main() -> None:
    token, admin_chat_id = read_required_env()

    app = Application.builder().token(token).build()
    app.bot_data["admin_chat_id"] = admin_chat_id

    lead_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex("^{}$".format(MENU_LEAD)), menu_router)],
        states={
            LEAD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_name_step)],
            LEAD_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_contact_step)],
        },
        fallbacks=[
            MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex("^{}$".format(MENU_BACK)), back_to_menu),
            CommandHandler("start", start),
        ],
        allow_reentry=True,
    )

    faq_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex("^{}$".format(MENU_FAQ)), menu_router)],
        states={
            FAQ_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, faq_answer)],
        },
        fallbacks=[
            MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex("^{}$".format(MENU_BACK)), back_to_menu),
            CommandHandler("start", start),
        ],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(lead_conv)
    app.add_handler(faq_conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_router))

    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()