"""
app/llm_service.py — работа с LLM (этап 2: ЗАГЛУШКА).

На этом этапе реальное обращение к LLM НЕ выполняется.
Функция classify_request возвращает фиксированный ответ, который
соответствует модели TriageResponse.

Позже (этап 3+) здесь появится:
- клиент OpenAI (base_url из config.OPENAI_BASE_URL, ключ PROXY_API_KEY);
- загрузка промпта из prompts/;
- вызов модели config.OPENAI_MODEL с параметрами model, messages и
  temperature=config.TEMPERATURE.

АРХИТЕКТУРНОЕ РЕШЕНИЕ по temperature:
- Параметр ПЕРЕДАЁТСЯ в запрос (client.chat.completions.create(...,
  temperature=config.TEMPERATURE)) — для гибкости при смене модели
  или провайдера, где temperature поддерживается.
- Модель openai/gpt-5.6-luna через ProxyAPI не поддерживает настройку
  temperature (провайдер использует дефолтное значение 1).
- Если провайдер вернёт ошибку 400, связанную с temperature — повторить
  запрос БЕЗ temperature, залогировать факт, и продолжить работу.
"""

from app.models import TriageResponse  # контракт ответа

# Фиксированный ответ заглушки (по требованию этапа 2).
_STUB_RESPONSE = TriageResponse(
    category="other",
    draft_reply="Обращение получено, обрабатывается.",
    confidence="low",
    escalate=True,
)


def classify_request(text: str, channel: str, client_id: str) -> TriageResponse:
    """
    Заглушка LLM-обработки обращения.

    Аргументы принимает такие же, какие позже понадобятся реальному
    LLM-сервису (текст, канал, клиент), чтобы сигнатура не менялась.

    Возвращает всегда один и тот же фиксированный ответ.
    """
    # Намеренно игнорируем вход — имитация ответа модели.
    return _STUB_RESPONSE
