# handlers/admin_handlers.py
from telebot import TeleBot, types
import os
from sqlalchemy.orm import Session
from db import SessionLocal
from models import ExamLevel, Section, Task
import logging
from state import set_user_state, get_user_state, is_admin_mode, clear_user_state

logger = logging.getLogger(__name__)

# 🔑 Загрузка ADMIN_IDS
admin_ids_str = os.getenv("ADMIN_IDS", "")
try:
    ADMIN_IDS = [
        int(x.strip()) for x in admin_ids_str.split(",")
        if x.strip().isdigit()
    ]
except Exception as e:
    logger.error(f"Ошибка парсинга ADMIN_IDS: {e}")
    ADMIN_IDS = []

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def register_admin_handlers(bot: TeleBot):

    # --- Вход в админку ---
    @bot.message_handler(commands=['admin'])
    def admin_start(message):
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "🚫 Доступ запрещён.")
            return

        # Переключаем в админ-режим
        set_user_state(message.from_user.id, mode="admin", step="main_menu", data={})

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add("➕ Добавить задание")
        markup.add("↩️ Выход")
        bot.send_message(
            message.chat.id,
            "🔐 Админ-панель\nВыберите действие:",
            reply_markup=markup
        )

    # --- Выход из админки ---
    @bot.message_handler(func=lambda msg: (
        is_admin(msg.from_user.id) and
        is_admin_mode(msg.from_user.id) and
        msg.text == "↩️ Выход"
    ))
    def admin_exit(message):
        clear_user_state(message.from_user.id)
        bot.send_message(
            message.chat.id,
            "✅ Вы вышли из админ-панели.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        # Опционально: вернуть в стартовое меню
        from handlers.user_handlers import send_welcome
        send_welcome(message)

    # --- Начало добавления задания ---
    @bot.message_handler(func=lambda msg: (
        is_admin(msg.from_user.id) and
        is_admin_mode(msg.from_user.id) and
        msg.text == "➕ Добавить задание"
    ))
    def start_add_task(message):
        set_user_state(message.from_user.id,
                       step="choose_level",
                       data={})

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        levels = [f"HSK {i}" for i in range(1, 6)]
        markup.add(*levels)
        bot.send_message(message.chat.id, "1️⃣ Выберите уровень:", reply_markup=markup)

    # --- Шаг 1: выбор уровня ---
    @bot.message_handler(func=lambda msg: (
        is_admin(msg.from_user.id) and
        is_admin_mode(msg.from_user.id) and
        get_user_state(msg.from_user.id).get("step") == "choose_level"
    ))
    def choose_level_admin(message):
        valid_levels = [f"HSK {i}" for i in range(1, 6)]
        if message.text not in valid_levels:
            bot.send_message(message.chat.id, "❌ Неверный уровень. Выберите из списка.")
            return

        data = get_user_state(message.from_user.id).get("data", {})
        data["level_name"] = message.text
        set_user_state(message.from_user.id, step="choose_section", data=data)

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add("Аудирование", "Чтение", "Письмо")
        bot.send_message(message.chat.id, "2️⃣ Выберите раздел:", reply_markup=markup)

    # --- Шаг 2: выбор раздела ---
    @bot.message_handler(func=lambda msg: (
        is_admin(msg.from_user.id) and
        is_admin_mode(msg.from_user.id) and
        get_user_state(msg.from_user.id).get("step") == "choose_section"
    ))
    def choose_section_admin(message):
        valid_sections = ["Аудирование", "Чтение", "Письмо"]
        if message.text not in valid_sections:
            bot.send_message(message.chat.id, "❌ Неверный раздел. Выберите из списка.")
            return

        state = get_user_state(message.from_user.id)
        data = state.get("data", {})
        data["section_name"] = message.text
        set_user_state(message.from_user.id, step="task_number", data=data)

        bot.send_message(
            message.chat.id,
            "3️⃣ Введите номер задания (целое число ≥ 1):",
            reply_markup=types.ReplyKeyboardRemove()
        )

    # --- Шаг 3: номер задания ---
    @bot.message_handler(func=lambda msg: (
        is_admin(msg.from_user.id) and
        is_admin_mode(msg.from_user.id) and
        get_user_state(msg.from_user.id).get("step") == "task_number"
    ))
    def enter_task_number(message):
        try:
            num = int(message.text)
            if num < 1:
                raise ValueError
        except (ValueError, TypeError):
            bot.send_message(message.chat.id, "❌ Некорректный номер. Введите целое число ≥ 1.")
            return

        state = get_user_state(message.from_user.id)
        data = state.get("data", {})
        data["task_number"] = num
        set_user_state(message.from_user.id, step="photo", data=data)
        bot.send_message(message.chat.id, "4️⃣ Отправьте фото задания (в сжатом виде, НЕ документом):")

    # --- Шаг 4: фото ---
    @bot.message_handler(content_types=['photo'], func=lambda msg: (
        is_admin(msg.from_user.id) and
        is_admin_mode(msg.from_user.id) and
        get_user_state(msg.from_user.id).get("step") == "photo"
    ))
    def receive_photo(message):
        photo_file_id = message.photo[-1].file_id
        state = get_user_state(message.from_user.id)
        data = state.get("data", {})
        data["photo_file_id"] = photo_file_id

        section = data["section_name"]
        if section == "Аудирование":
            set_user_state(message.from_user.id, step="audio", data=data)
            bot.send_message(message.chat.id, "5️⃣ Отправьте аудиофайл (голосовое сообщение или MP3):")
        else:
            set_user_state(message.from_user.id, step="comment", data=data)
            bot.send_message(message.chat.id, "5️⃣ Введите текст комментария к заданию:")

    # --- Шаг 5a: аудио ---
    @bot.message_handler(content_types=['audio', 'voice'], func=lambda msg: (
        is_admin(msg.from_user.id) and
        is_admin_mode(msg.from_user.id) and
        get_user_state(msg.from_user.id).get("step") == "audio"
    ))
    def receive_audio(message):
        file_id = message.voice.file_id if message.voice else message.audio.file_id
        state = get_user_state(message.from_user.id)
        data = state.get("data", {})
        data["audio_file_id"] = file_id
        set_user_state(message.from_user.id, step="comment", data=data)
        bot.send_message(message.chat.id, "6️⃣ Введите текст комментария к заданию:")

    # --- Шаг 5b/6: комментарий ---
    @bot.message_handler(func=lambda msg: (
        is_admin(msg.from_user.id) and
        is_admin_mode(msg.from_user.id) and
        get_user_state(msg.from_user.id).get("step") == "comment"
    ))
    def enter_comment(message):
        state = get_user_state(message.from_user.id)
        data = state.get("data", {})
        data["comment"] = message.text.strip()

        if data["section_name"] == "Письмо":
            set_user_state(message.from_user.id, step="confirm", data=data)
            _show_preview_and_confirm(bot, message.chat.id, data)
        else:
            set_user_state(message.from_user.id, step="correct_answer", data=data)
            bot.send_message(
                message.chat.id,
                "7️⃣ Введите правильный ответ (точно так, как должен ввести пользователь):\n"
                "Например: «3» или «北京» или «他去了学校»"
            )

    # --- Шаг 6/7: правильный ответ ---
    @bot.message_handler(func=lambda msg: (
        is_admin(msg.from_user.id) and
        is_admin_mode(msg.from_user.id) and
        get_user_state(msg.from_user.id).get("step") == "correct_answer"
    ))
    def enter_correct_answer(message):
        state = get_user_state(message.from_user.id)
        data = state.get("data", {})
        data["correct_answer"] = message.text.strip()
        set_user_state(message.from_user.id, step="confirm", data=data)
        _show_preview_and_confirm(bot, message.chat.id, data)

    # --- Предпросмотр ---
    def _show_preview_and_confirm(bot, chat_id, data):
        section = data["section_name"]
        preview = (
            f"🔍 *Предпросмотр задания*\n\n"
            f"📌 Уровень: {data['level_name']}\n"
            f"📚 Раздел: {section}\n"
            f"🔢 Номер: {data['task_number']}\n"
            f"💬 Комментарий: {data['comment']}\n"
        )
        if section != "Письмо":
            preview += f"✅ Правильный ответ: `{data['correct_answer']}`\n"

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add("✅ Подтвердить", "❌ Отменить")
        bot.send_message(chat_id, preview, parse_mode="Markdown", reply_markup=markup)

    # --- Подтверждение / отмена ---
    @bot.message_handler(func=lambda msg: (
        is_admin(msg.from_user.id) and
        is_admin_mode(msg.from_user.id) and
        get_user_state(msg.from_user.id).get("step") == "confirm" and
        msg.text in ["✅ Подтвердить", "❌ Отменить"]
    ))
    def confirm_or_cancel(message):
        if message.text == "❌ Отменить":
            clear_user_state(message.from_user.id)
            bot.send_message(
                message.chat.id,
                "↩️ Добавление отменено.",
                reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("/admin")
            )
            return

        state = get_user_state(message.from_user.id)
        _save_task(bot, message.chat.id, state.get("data", {}))
        clear_user_state(message.from_user.id)

    # --- Сохранение ---
    def _save_task(bot, chat_id, data):
        db: Session = SessionLocal()
        try:
            level = db.query(ExamLevel).filter(ExamLevel.name == data["level_name"]).first()
            section = db.query(Section).filter(Section.name == data["section_name"]).first()
            if not level or not section:
                bot.send_message(chat_id, "❌ Ошибка: уровень или раздел не найдены.")
                return

            task = Task(
                level_id=level.id,
                section_id=section.id,
                task_number=data["task_number"],
                photo_file_id=data["photo_file_id"],
                audio_file_id=data.get("audio_file_id"),
                comment_text=data["comment"],
                correct_answer=data.get("correct_answer")
            )
            db.add(task)
            db.commit()

            bot.send_message(
                chat_id,
                f"✅ Задание добавлено!\n\n"
                f"Уровень: {data['level_name']}\n"
                f"Раздел: {data['section_name']}\n"
                f"Номер: {data['task_number']}",
                reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("/admin")
            )
            logger.info(f"Админ {chat_id} добавил задание: {data['level_name']} {data['section_name']} №{data['task_number']}")

        except Exception as e:
            logger.error(f"Ошибка сохранения задания: {e}")
            bot.send_message(chat_id, f"❌ Ошибка при сохранении: {str(e)[:200]}")
        finally:
            db.close()

    # --- Обработка неожиданных сообщений ---
    @bot.message_handler(func=lambda msg: (
        is_admin(msg.from_user.id) and
        is_admin_mode(msg.from_user.id) and
        get_user_state(msg.from_user.id).get("step") not in [
            "main_menu", "choose_level", "choose_section", "task_number", "confirm"
        ]
    ))
    def handle_unexpected_input(message):
        step = get_user_state(message.from_user.id).get("step")
        if step == "photo":
            bot.send_message(message.chat.id, "⚠️ Ожидалось фото.")
        elif step == "audio":
            bot.send_message(message.chat.id, "⚠️ Ожидался аудиофайл.")
        elif step in ["comment", "correct_answer"]:
            bot.send_message(message.chat.id, "⚠️ Ожидался текст.")