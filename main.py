import os
from dotenv import load_dotenv
load_dotenv()
import logging
from telebot import TeleBot
from db import init_db
from handlers.user_handlers import register_user_handlers
from handlers.admin_handlers import register_admin_handlers

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не указан в .env")

bot = TeleBot(TOKEN)

def init_reference_data():
    from sqlalchemy.orm import Session
    from db import SessionLocal
    from models import ExamLevel, Section

    db: Session = SessionLocal()
    try:
        for i in range(1, 6):
            if not db.query(ExamLevel).filter(ExamLevel.name == f"HSK {i}").first():
                db.add(ExamLevel(name=f"HSK {i}"))
        for name in ["Аудирование", "Чтение", "Письмо"]:
            if not db.query(Section).filter(Section.name == name).first():
                db.add(Section(name=name))
        db.commit()
        logger.info("Справочные данные инициализированы.")
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
    init_reference_data()

    register_user_handlers(bot)
    register_admin_handlers(bot)

    logger.info("Бот запущен.")
    bot.infinity_polling()