import os
from langchain_gigachat import GigaChat
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser


# Инициализация GigaChat
def get_gigachat_client():
    auth = os.getenv("GIGACHAT_AUTH")
    return GigaChat(
        credentials=auth,
        verify_ssl_certs=False,
        scope="GIGACHAT_API_PERS",
        model="GigaChat",
        timeout=60,
    )


def analyze_writing_task(level_name: str, comment: str, user_text: str) -> str:
    chat = get_gigachat_client()

    prompt_template = """
Ты — строгий, но доброжелательный преподаватель китайского языка, эксперт по экзамену HSK.
Пользователь выполнил задание по письму для уровня {level_name}.
Задание было таким:
«{comment}»

Его ответ:
«{user_text}»

Проанализируй ответ по критериям HSK:
1. Грамматика (порядок слов, частицы, времена)
2. Лексика (подходящие слова, разнообразие)
3. Соответствие заданию (тема, объём, стиль)
4. Орфография (иероглифы, знаки препинания)

Дай фидбек на РУССКОМ языке в формате:
Сильные стороны: ...
Ошибки (макс. 3): ...
Улучшенный вариант (на китайском + перевод на русский): ...
 Совет для подготовки: ...

Если текст слишком короткий или не по теме — скажи об этом вежливо.
"""

    prompt = ChatPromptTemplate.from_template(prompt_template)
    chain = prompt | chat | StrOutputParser()

    try:
        result = chain.invoke({
            "level_name": level_name,
            "comment": comment,
            "user_text": user_text
        })
        return result
    except Exception as e:
        return f"⚠️ Извините, не удалось проанализировать текст. Ошибка: {str(e)[:100]}"