# ✅ state.py — ПОЛНАЯ ВЕРСИЯ ДЛЯ СПОСОБА 1
from threading import Lock
from typing import Any, Dict

_state: Dict[int, Dict[str, Any]] = {}
_lock = Lock()


def get_user_state(user_id: int) -> Dict[str, Any]:
    """Получить словарь состояния пользователя"""
    with _lock:
        return _state.get(user_id, {})


def set_user_state(user_id: int, **kwargs) -> None:
    """
    Установить поля состояния пользователя.
    Примеры:
        set_user_state(123, mode="admin", step="choose_level")
        set_user_state(123, data={"level": "HSK 1"})
    """
    with _lock:
        if user_id not in _state:
            _state[user_id] = {}
        _state[user_id].update(kwargs)


def is_user_mode(user_id: int) -> bool:
    """Проверить, в пользовательском ли режиме пользователь"""
    state = get_user_state(user_id)
    return state.get("mode", "user") == "user"


def is_admin_mode(user_id: int) -> bool:
    """✅ ДОБАВЛЕНО: Проверить, в админ-режиме ли пользователь"""
    state = get_user_state(user_id)
    return state.get("mode") == "admin"


def clear_user_state(user_id: int) -> None:
    """Очистить всё состояние пользователя"""
    with _lock:
        _state.pop(user_id, None)