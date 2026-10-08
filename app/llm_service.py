"""
app/llm_service.py — работа с LLM (этап 3: реальный вызов через ProxyAPI).

Единственная точка выхода сервиса во внешний мир. Публичная функция:

    triage_text(text: str, channel: str) -> dict

Возвращает dict с ключами category, draft_reply, confidence, escalate —
ровно те поля, которые ожидает TriageResponse из app/models.py.

ВАЖНО: функция НЕ бросает исключений наружу. Любая неполадка (сеть,
таймаут, 4xx/5xx провайдера, не-JSON в ответе, недопустимые значения
полей) превращается в безопасный fallback с escalate=True — сервис
остаётся работоспособным даже при недоступной модели.

АРХИТЕКТУРНОЕ РЕШЕНИЕ по temperature (зафиксировано на этапе 2):
- Параметр ПЕРЕДАЁТСЯ в запрос (temperature=config.TEMPERATURE) — для
  гибкости при смене модели или провайдера, где temperature поддерживается.
- Модель openai/gpt-5.6-luna через ProxyAPI не поддерживает настройку
  temperature (провайдер использует дефолтное значение 1).
- Если провайдер вернул 400 именно на temperature — запрос повторяется
  БЕЗ него, факт логируется, работа продолжается (см. _create_chat).
"""

import json  # разбор JSON-ответа модели
import re  # снятие markdown-обёртки ```json ... ```

from openai import (  # OpenAI-совместимый клиент ProxyAPI
    APIConnectionError,
    APITimeoutError,
    APIStatusError,
    OpenAI,
)

from app import config  # PROXY_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL, TEMPERATURE
from app.logger import setup_logger  # общий логгер приложения

logger = setup_logger("triage.llm")

# Системный промпт: роль, правила классификации и жёсткое требование к формату.
# Значения category/confidence здесь согласованы с Literal-ами в app/models.py.
SYSTEM_PROMPT = """Ты — ассистент службы поддержки. Твоя задача: классифицировать обращение клиента и написать черновик ответа.
ПРАВИЛА:
1. Отвечай СТРОГО на основе входного текста. Не выдумывай факты, которых нет.
2. Если данных мало или текст непонятен — ставь confidence=low и escalate=true.
3. Если обращение касается оплаты/счетов — category=billing.
4. Если это просьба о помощи/консультации — category=support.
5. Если это жалоба/негатив — category=complaint.
6. Всё остальное — category=other.
7. draft_reply — 1-6 предложений, вежливый ответ клиенту.
8. escalate=true, если confidence=low или обращение требует участия человека.
ФОРМАТ ОТВЕТА (строго JSON, без пояснений):
{
"category": "billing | support | complaint | other",
"draft_reply": "...",
"confidence": "high | medium | low",
"escalate": true | false
}"""

# Допустимые значения полей — зеркало Literal-ов из TriageResponse.
VALID_CATEGORIES = ("billing", "support", "complaint", "other")
VALID_CONFIDENCES = ("high", "medium", "low")

# Безопасный ответ, отдаваемый при любой недоступности/некорректности LLM.
FALLBACK = {
    "category": "other",
    "draft_reply": "Обращение передано оператору.",
    "confidence": "low",
    "escalate": True,
}

# Ограничение на длину сырого ответа модели в логах — защита от переполнения
# файла логов длинными выводами.
MAX_RAW_IN_LOG = 300


def _extract_json(raw: str) -> dict:
    """
    Достать JSON-объект из ответа модели.

    Модель обязана отвечать чистым JSON, но на практике оборачивает ответ
    в ```json ... ``` или добавляет пояснения. Разбираем по шагам, от
    правильного варианта к самому терпимому:

      1. прямой json.loads;
      2. снятие markdown-обёртки и повторный разбор;
      3. подстрока от первой '{' до последней '}'.

    Не сработал ни один шаг — ValueError (вызывающий превратит его в fallback).
    """
    text = raw.strip()

    # Шаг 1: идеальный случай — модель ответила ровно JSON.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Шаг 2: снимаем markdown-блок кода (```...``` или ```json ... ```).
    fence = re.search(r"```(?:[a-zA-Z0-9_+-]*)\s*(.*?)```", text, re.DOTALL)
    if fence:
        try:
            parsed = json.loads(fence.group(1).strip())
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # Шаг 3: грубая страховка — первая '{' и последняя '}'.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    raise ValueError(f"в ответе модели не найден JSON-объект: {raw[:MAX_RAW_IN_LOG]!r}")


def _validate(parsed: dict) -> dict:
    """
    Проверить разобранный JSON и привести к контракту TriageResponse.

    Правила из ТЗ:
    - category должна входить в VALID_CATEGORIES;
    - confidence — в VALID_CONFIDENCES;
    - escalate — строго bool.

    Любое несоответствие — ValueError: вызывающий отдаст fallback целиком,
    а не частично доверенный ответ модели.
    """
    category = parsed.get("category")
    if not isinstance(category, str) or category.strip().lower() not in VALID_CATEGORIES:
        raise ValueError(f"недопустимая category={category!r}")

    confidence = parsed.get("confidence")
    if not isinstance(confidence, str) or confidence.strip().lower() not in VALID_CONFIDENCES:
        raise ValueError(f"недопустимая confidence={confidence!r}")

    escalate = parsed.get("escalate")
    if not isinstance(escalate, bool):
        raise ValueError(f"escalate должен быть bool, получен {type(escalate).__name__}")

    draft_reply = parsed.get("draft_reply")
    if not isinstance(draft_reply, str) or not draft_reply.strip():
        raise ValueError(f"draft_reply должен быть непустой строкой, получен {draft_reply!r}")

    # Нормализуем регистр перечислений к каноническому нижнему.
    return {
        "category": category.strip().lower(),
        "draft_reply": draft_reply.strip(),
        "confidence": confidence.strip().lower(),
        "escalate": escalate,
    }


def _fallback(reason: str) -> dict:
    """
    Безопасный ответ при недоступной/некорректно ответившей LLM.

    Копируем FALLBACK, чтобы вызывающий не мог случайно изменить
    модульную константу, и логируем причину срабатывания.
    """
    logger.warning("LLM fallback сработал: %s", reason)
    return dict(FALLBACK)


def _create_chat(client: OpenAI, messages: list) -> str:
    """
    Отправить запрос модели и вернуть текст ответа.

    Сначала пробуем С temperature=config.TEMPERATURE (архитектурное
    решение этапа 2). Если провайдер ответил 400 именно на temperature
    (модель openai/gpt-5.6-luna его не поддерживает) — повторяем запрос
    без него. Иное исключение пробрасывается наверх, в triage_text.
    """
    try:
        response = client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=messages,
            temperature=config.TEMPERATURE,
        )
    except APIStatusError as exc:
        # 400 и в тексте упоминается temperature → это неподдержка параметра,
        # а не ошибка в нашем запросе. Повторяем без параметра.
        is_temperature_reject = exc.status_code == 400 and "temperature" in str(exc).lower()
        if not is_temperature_reject:
            raise

        logger.warning(
            "Провайдер не поддерживает temperature=%s (400), повторяю запрос без него",
            config.TEMPERATURE,
        )
        response = client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=messages,
        )

    # content может быть None (модель вернула только tool_calls) — считаем это
    # пустым ответом, дальше разберётся _extract_json и уйдёт в fallback.
    return response.choices[0].message.content or ""


def triage_text_with_error(text: str, channel: str) -> tuple[dict, str | None]:
    """
    Тот же triage_text, но вместе с результатом отдаёт причину ошибки.

    Возвращает кортеж (result, error):
      - result — dict с ключами TriageResponse (при проблеме это FALLBACK);
      - error  — текст причины либо None, если LLM отработала штатно.

    Нужен для этапа 4: колонка error в таблице tickets должна хранить текст
    ошибки, а не только факт, что сработал fallback. Раньше причина жила
    только в логе.
    """
    # Логируем запрос: канал и длину текста. Сам текст в лог не пишем —
    # это персональные данные клиента.
    logger.info("Запрос к LLM: channel=%s, длина text=%s", channel, len(text))

    # Клиент создаём на каждый вызов: это дёшево и снимает вопросы о
    # переиспользовании соединения между потоками и воркерами uvicorn.
    client = OpenAI(api_key=config.PROXY_API_KEY, base_url=config.OPENAI_BASE_URL)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Канал: {channel}\nТекст обращения: {text}"},
    ]

    try:
        raw = _create_chat(client, messages)
        # Ответ модели логируем — он нужен для разбора качества триажа.
        logger.info("Ответ LLM: %s", raw[:MAX_RAW_IN_LOG])
        # Штатный путь: причина ошибки отсутствует.
        return _validate(_extract_json(raw)), None

    # Сетевые сбои и таймауты: модель физически недоступна.
    except (APIConnectionError, APITimeoutError) as exc:
        reason = f"LLM недоступна: {type(exc).__name__}: {exc}"
        return _fallback(reason), reason

    # Ответ провайдера с ошибочным статусом (401 ключ, 429 лимит, 5xx и т.п.).
    except APIStatusError as exc:
        reason = f"ошибка провайдера {exc.status_code}: {str(exc)[:MAX_RAW_IN_LOG]}"
        return _fallback(reason), reason

    # Всё остальное: не-JSON, неверные поля, пустой ответ, неожиданные сбои.
    # Наружу ничего не выпускаем — контракт сервиса «всегда отвечаем 200 + fallback».
    except Exception as exc:  # noqa: BLE001 — осознанно: наружу идёт fallback
        reason = f"ошибка разбора ответа: {type(exc).__name__}: {exc}"
        return _fallback(reason), reason


def triage_text(text: str, channel: str) -> dict:
    """
    Классифицировать обращение через LLM и подготовить черновик ответа.

    Аргументы:
        text    — текст обращения клиента;
        channel — канал поступления (email/form/chat), попадает в user prompt.

    Возвращает dict: {"category", "draft_reply", "confidence", "escalate"}.
    Исключений не бросает — при любой ошибке возвращает fallback с
    escalate=True (обращение увидит оператор).

    Сигнатура и поведение этапа 3 сохранены без изменений; если нужна ещё и
    причина ошибки (для записи в БД) — используйте triage_text_with_error.
    """
    result, _ = triage_text_with_error(text, channel)
    return result
