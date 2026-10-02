"""
app/models.py — Pydantic-модели запросов и ответов эндпоинта /triage.

Модели описывают контракт API:
- TriageRequest — входной JSON (проверяется длиной и допустимыми значениями);
- TriageResponse — выходной JSON (формат ответа triage-сервиса).

Нарушение любой из проверок FastAPI автоматически превращает в ответ 422.
"""

from typing import Literal  # строковые литералы для перечислений

from pydantic import BaseModel, Field  # базовая модель и описание полей

from app import config  # MAX_TEXT_LENGTH из настроек (.env)


class TriageRequest(BaseModel):
    """Входное обращение от клиента."""

    # Текст обращения: обязателен, непустой, длина 1..MAX_TEXT_LENGTH символов.
    # MAX_TEXT_LENGTH подтягивается из .env (по образцу — 2000).
    text: str = Field(
        ...,
        min_length=1,
        max_length=config.MAX_TEXT_LENGTH,
        description="Текст обращения клиента",
        examples=["Не работает личный кабинет, ошибка 500 при входе"],
    )

    # Канал обращения: строго одно из трёх значений.
    channel: Literal["email", "form", "chat"] = Field(
        ...,
        description="Канал поступления обращения",
        examples=["email"],
    )

    # Идентификатор клиента: обязателен, непустой.
    client_id: str = Field(
        ...,
        min_length=1,
        description="Идентификатор клиента",
        examples=["client-001"],
    )


class TriageResponse(BaseModel):
    """Результат обработки обращения (триаж)."""

    # Категория обращения.
    category: Literal["billing", "support", "complaint", "other"] = Field(
        ..., description="Определённая категория обращения"
    )

    # Черный ответ клиенту (1–6 предложений по регламенту).
    draft_reply: str = Field(..., description="Черновик ответа клиенту")

    # Уверенность модели в определении категории.
    confidence: Literal["high", "medium", "low"] = Field(
        ..., description="Уровень уверенности в ответе"
    )

    # Признак необходимости эскалации обращения оператору.
    escalate: bool = Field(
        ..., description="Нужно ли передать обращение оператору"
    )
