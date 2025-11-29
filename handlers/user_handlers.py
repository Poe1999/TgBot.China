from telebot import TeleBot, types
from sqlalchemy.orm import Session
from db import SessionLocal
from models import ExamLevel, Section, Task, UserSession
from llm import analyze_writing_task
from sqlalchemy.orm import joinedload
import logging

# ✅ ЕДИНОЕ СОСТОЯНИЕ
from state import (
    get_user_state,
    set_user_state,
    is_user_mode,
    clear_user_state
)

logger = logging.getLogger(__name__)


def register_user_handlers(bot: TeleBot):

    # --- /start — стартовое меню ---
    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        clear_user_state(message.from_user.id)  # выходим из любого режима
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        levels = ["HSK 1", "HSK 2", "HSK 3", "HSK 4", "HSK 5"]
        markup.add(*[types.KeyboardButton(l) for l in levels])
        bot.send_message(
            message.chat.id,
            "👋 Привет! Я — бот для подготовки к HSK.\n\n"
            "Выберите уровень экзамена:",
            reply_markup=markup
        )

    # --- Выбор уровня ---
    @bot.message_handler(func=lambda msg: (
        msg.text in [f"HSK {i}" for i in range(1, 6)] and
        is_user_mode(msg.from_user.id)
    ))
    def choose_level(message):
        level_name = message.text
        db = SessionLocal()
        try:
            level = db.query(ExamLevel).filter(ExamLevel.name == level_name).first()
            if not level:
                bot.send_message(message.chat.id, "❌ Уровень не найден. Нажмите /start.")
                return

            set_user_state(message.from_user.id, level_id=level.id)
            set_user_state(message.from_user.id, level_name=level_name)

            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            sections = ["Аудирование", "Чтение", "Письмо"]
            markup.add(*[types.KeyboardButton(s) for s in sections])
            bot.send_message(
                message.chat.id,
                f"Вы выбрали {level_name}. Теперь выберите раздел:",
                reply_markup=markup
            )
        finally:
            db.close()

    # --- Выбор раздела ---
    @bot.message_handler(func=lambda msg: (
        msg.text in ["Аудирование", "Чтение", "Письмо"] and
        is_user_mode(msg.from_user.id)
    ))
    def choose_section(message):
        section_name = message.text
        db = SessionLocal()
        try:
            section = db.query(Section).filter(Section.name == section_name).first()
            if not section:
                bot.send_message(message.chat.id, "Раздел не найден.")
                return

            state = get_user_state(message.from_user.id)
            level_id = state.get("level_id")
            if not level_id:
                bot.send_message(message.chat.id, "Сначала выберите уровень (/start)")
                return

            set_user_state(message.from_user.id, section_id=section.id)
            set_user_state(message.from_user.id, section_name=section_name)

            tasks = db.query(Task).filter(
                Task.level_id == level_id,
                Task.section_id == section.id
            ).order_by(Task.task_number).all()

            if not tasks:
                bot.send_message(
                    message.chat.id,
                    f"📌 Пока нет заданий для «{section_name}». Обратитесь к администратору."
                )
                return

            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            for t in tasks:
                markup.add(types.KeyboardButton(f"Задание {t.task_number}"))
            markup.add(types.KeyboardButton("↩️ Назад к уровням"))

            bot.send_message(
                message.chat.id,
                f"📚 Раздел: *{section_name}*\n"
                f"Всего заданий: {len(tasks)}\n"
                f"Выберите номер:",
                parse_mode="Markdown",
                reply_markup=markup
            )
        finally:
            db.close()

    # --- Выбор конкретного задания ---
    @bot.message_handler(func=lambda msg: (
            msg.text and
            msg.text.startswith("Задание ") and
            len(msg.text.split()) == 2 and
            msg.text.split()[1].isdigit() and
            is_user_mode(msg.from_user.id)
    ))
    def send_task(message):
        try:
            task_num = int(message.text.split()[1])
        except (ValueError, IndexError):
            bot.send_message(message.chat.id, "Некорректный номер задания.")
            return

        user_id = message.from_user.id
        state = get_user_state(user_id)
        level_id = state.get("level_id")
        section_id = state.get("section_id")

        if not (level_id and section_id):
            bot.send_message(message.chat.id, "Сессия устарела. Начните с /start")
            return

        db = SessionLocal()
        try:
            task = db.query(Task).options(joinedload(Task.section),joinedload(Task.level)).filter(
                Task.level_id == level_id,
                Task.section_id == section_id,
                Task.task_number == task_num
            ).first()

            if not task:
                bot.send_message(message.chat.id, f"Задание {task_num} не найдено.")
                return

            set_user_state(user_id, current_task_id=task.id)

            # 1. Фото
            bot.send_photo(message.chat.id, task.photo_file_id, caption="📎 Задание:")

            # 2. Аудио (если есть)
            if task.audio_file_id:
                bot.send_audio(message.chat.id, task.audio_file_id, caption="🎧 Аудио:")

            # 3. Текст и ввод ответа
            bot.send_message(
                message.chat.id,
                f"{task.comment_text}\n\nВведите ответ:",
                reply_markup=types.ReplyKeyboardRemove()
            )

            bot.register_next_step_handler(message, process_answer, task)

        except Exception as e:
            logger.error(f"Ошибка в send_task: {e}")
            bot.send_message(message.chat.id, "Ошибка при загрузке задания.")
        finally:
            db.close()


    # --- Обработка ответа пользователя ---

    def process_answer(message, task):
        user_id = message.from_user.id
        user_answer = message.text.strip()

        db = SessionLocal()
        try:
            session = UserSession(
                user_id=user_id,
                task_id=task.id,
                user_answer=user_answer
            )
            is_complex = "задания 1-5" in task.comment_text.lower() or "вопросы 1-5" in task.comment_text.lower()

            if task.section.name == "Письмо":
                bot.send_message(user_id, "🧠 Анализирую ваш текст с помощью ИИ…")
                try:
                    feedback = analyze_writing_task(
                        level_name=task.level.name,
                        comment=task.comment_text,
                        user_text=user_answer
                    )
                except Exception as e:
                    logger.error(f"LLM error: {e}")
                    feedback = "Не удалось проанализировать текст. Попробуйте позже."
                session.is_correct = None

            else:
                if is_complex:
                    expected = task.correct_answer.strip().upper()
                    if len(user_answer) == len(expected) and all(c in "AB" for c in user_answer):
                        if user_answer == expected:
                            feedback = "Все ответы верны! Отлично!"
                        else:
                            # Подсветим ошибки
                            result = []
                            for i, (u, e) in enumerate(zip(user_answer, expected), 1):
                                result.append(f"{i}. {'✅' if u == e else f'❌ ({e})'}")
                            feedback = "Проверьте ответы:\n" + "\n".join(result)
                    else:
                        feedback = (
                            "Неверный формат ответа.\n"
                            "Для заданий 1-5 введите 5 букв (A/B) слитно, например: ABBBA"
                        )
                    session.is_correct = (user_answer == expected)
                else:
                    is_correct = user_answer == task.correct_answer
                    session.is_correct = is_correct
                    feedback = "Правильно!" if is_correct else f"Неверно. Правильный ответ: {task.correct_answer}"

            db.add(session)
            db.commit()

            # Отправляем фидбек
            bot.send_message(user_id, feedback, parse_mode="Markdown")

            # Кнопки навигации
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add("Следующее задание")
            markup.add("К списку заданий", "🏠 В главное меню")
            bot.send_message(user_id, "Что делаем дальше?", reply_markup=markup)

        except Exception as e:
            logger.error(f"Error in process_answer: {e}")
            bot.send_message(user_id, "Произошла ошибка. Попробуйте снова.")
        finally:
            db.close()

    # --- Навигация после ответа ---
    @bot.message_handler(func=lambda msg: (
        msg.text in ["Следующее задание", "К списку заданий", "🏠 В главное меню"] and
        is_user_mode(msg.from_user.id)
    ))
    def handle_navigation(message):
        user_id = message.from_user.id
        text = message.text

        if text == "🏠 В главное меню":
            send_welcome(message)
            return

        state = get_user_state(user_id)
        level_id = state.get("level_id")
        section_id = state.get("section_id")

        if not (level_id and section_id):
            bot.send_message(message.chat.id, "Сначала выберите уровень (/start)")
            return

        db = SessionLocal()
        try:
            if text == "К списку заданий":
                section = db.query(Section).filter(Section.id == section_id).first()
                level = db.query(ExamLevel).filter(ExamLevel.id == level_id).first()
                if not section or not level:
                    bot.send_message(message.chat.id, "Ошибка состояния. Начните с /start.")
                    return

                tasks = db.query(Task).filter(
                    Task.level_id == level_id,
                    Task.section_id == section_id
                ).order_by(Task.task_number).all()

                markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
                for t in tasks:
                    markup.add(types.KeyboardButton(f"Задание {t.task_number}"))
                markup.add("Назад к уровням")

                bot.send_message(
                    message.chat.id,
                    f"📚 {level.name} → {section.name}\n"
                    f"Выберите задание:",
                    reply_markup=markup
                )

            elif text == "Следующее задание":
                current_task_id = state.get("current_task_id")
                if not current_task_id:
                    bot.send_message(message.chat.id, "Не удалось определить текущее задание.")
                    return

                # Получаем следующее задание в том же уровне и разделе
                current_task = db.query(Task).options(joinedload(Task.section),joinedload(Task.level)).filter(Task.id == current_task_id).first()
                if not current_task:
                    bot.send_message(message.chat.id, "Задание не найдено.")
                    return

                next_task = db.query(Task).options(joinedload(Task.section),joinedload(Task.level)).filter(
                    Task.level_id == current_task.level_id,
                    Task.section_id == current_task.section_id,
                    Task.task_number > current_task.task_number
                ).order_by(Task.task_number).first()

                if next_task:
                    # Эмулируем выбор следующего задания
                    set_user_state(user_id, current_task_id=next_task.id)

                    bot.send_photo(message.chat.id, next_task.photo_file_id, caption="📎 Задание:")
                    if next_task.audio_file_id:
                        bot.send_audio(message.chat.id, next_task.audio_file_id, caption="🎧 Прослушайте:")
                    bot.send_message(
                        message.chat.id,
                        f"{next_task.comment_text}\n\nВведите ваш ответ:",
                        reply_markup=types.ReplyKeyboardRemove()
                    )
                    bot.register_next_step_handler(message, process_answer, next_task)
                else:
                    bot.send_message(
                        message.chat.id,
                        "🏁 Это было последнее задание в разделе.\n"
                        "Возвращайтесь за новыми!",
                        reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True)
                            .add("К списку заданий", "🏠 В главное меню")
                    )

        finally:
            db.close()

    # --- Возврат к выбору уровня ---
    @bot.message_handler(func=lambda msg: (
        msg.text == "Назад к уровням" and
        is_user_mode(msg.from_user.id)
    ))
    def back_to_levels(message):
        send_welcome(message)
