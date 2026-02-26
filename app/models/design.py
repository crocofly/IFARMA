"""
models/design.py — DTO результата Study Design Agent.

Описывает полный дизайн исследования БЭ, который определяется
на основе CVintra и T½ по правилам Решения №85.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


# ── Перечисления (enum) для типизированных значений ──

class DesignType(str, Enum):
    """Тип дизайна исследования."""
    CROSSOVER_2X2 = "2x2_crossover"           # Простой перекрёстный: 2 периода, 2 последовательности
    REPLICATE_3 = "replicate_3_period"         # Репликативный 3-периодный (TRT/RTR)
    REPLICATE_4 = "replicate_4_period"         # Репликативный 4-периодный (TRTR/RTRT)
    PARALLEL = "parallel"                       # Параллельный: 2 группы, нет перекреста


class IntakeMode(str, Enum):
    """Режим приёма препарата."""
    FASTING = "fasting"     # Натощак (≥8ч без еды до, 4ч после)
    FED = "fed"             # После еды (стандартизированный рацион)
    BOTH = "both"           # Оба варианта (для модифицированного высвобождения)


# ── Основная модель результата ──

class DesignResult(BaseModel):
    """
    Полный результат Study Design Agent.
    
    Содержит все параметры дизайна, которые нужны для:
    - Sample Size Agent (design_type, n_periods → формула расчёта)
    - Synopsis Generator (все поля → текст синопсиса)
    - Regulatory Agent (проверка соответствия Решению №85)
    """

    # === Тип дизайна ===
    design_type: DesignType = Field(
        ...,
        description="Тип дизайна исследования",
    )
    design_justification: str = Field(
        "",
        description="Текстовое обоснование выбора дизайна (для синопсиса)",
    )

    # === Периоды ===
    n_periods: int = Field(
        ...,
        description="Количество периодов: 2 (стандарт), 3 или 4 (репликативный)",
    )
    n_sequences: int = Field(
        ...,
        description="Количество последовательностей: 2 (2x2, параллельный), 3 или 4 (репликативный)",
    )
    sequences_description: str = Field(
        "",
        description="Описание последовательностей, например 'TR/RT' или 'TRTR/RTRT'",
    )

    # === Отмывочный период ===
    washout_days: Optional[int] = Field(
        None,
        description="Отмывочный период в днях (5-6 × T½). None для параллельного дизайна",
    )
    washout_formula: str = Field(
        "",
        description="Формула расчёта, например '5 × 35ч = 175ч ≈ 8 дней'",
    )

    # === Режим приёма ===
    intake_mode: IntakeMode = Field(
        IntakeMode.FASTING,
        description="Натощак / после еды / оба",
    )

    # === Точки отбора крови ===
    n_blood_points: int = Field(
        18,
        description="Общее количество точек отбора крови (~16-20)",
    )
    blood_points_description: str = Field(
        "",
        description="Описание: '1 до приёма + 5-7 подъём + 1 пик + 9-11 элиминация'",
    )
    sampling_duration_hours: int = Field(
        72,
        description="Общая длительность отбора проб (часы, обычно ≤72ч)",
    )
    sampling_times_hours: list = Field(
        default_factory=list,
        description="Расписание точек ФК в часах: [0, 0.25, 0.5, 1, ...]",
    )

    # === Dropout ===
    dropout_rate: float = Field(
        0.12,
        description="Ожидаемый dropout: 0.10-0.12 (2 периода), 0.25 (4 периода)",
    )
    dropout_justification: str = Field(
        "",
        description="Обоснование dropout rate",
    )

    # === Границы биоэквивалентности ===
    be_lower: float = Field(
        80.0,
        description="Нижняя граница ДИ (%): 80.00 (стандарт) или 90.00 (NTI)",
    )
    be_upper: float = Field(
        125.0,
        description="Верхняя граница ДИ (%): 125.00 (стандарт) или 111.11 (NTI)",
    )
    be_can_expand: bool = Field(
        False,
        description="Можно ли расширить границы для Cmax (для HVD по таблице Решения №85)",
    )

    # === Флаги ===
    is_hvd: bool = Field(False, description="Высоковариабельный препарат")
    is_nti: bool = Field(False, description="Узкий терапевтический индекс")
    is_modified_release: bool = Field(False, description="Модифицированное высвобождение")