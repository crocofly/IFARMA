"""
models/common.py — DTO для входных данных пайплайна.

Минимальный ввод пользователя: 4 обязательных поля.
Остальное — опционально (AI ищет сам или задаёт вопрос).

Поля соответствуют:
- Решение ЕАЭС №85
- Встреча с экспертом 16.02.2026
- UX-рекомендации (Progressive Disclosure)
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


# ── Перечисления ──

class ReleaseType(str, Enum):
    IMMEDIATE = "immediate"    # Немедленное высвобождение
    MODIFIED = "modified"      # Модифицированное высвобождение
    DELAYED = "delayed"        # Замедленное высвобождение


class IntakeMode(str, Enum):
    FASTING = "fasting"        # Натощак
    FED = "fed"                # После еды
    BOTH = "both"              # Оба варианта


class SexRestriction(str, Enum):
    MALES_ONLY = "males_only"           # Только мужчины
    FEMALES_ONLY = "females_only"       # Только женщины
    MALES_AND_FEMALES = "males_and_females"  # Мужчины и женщины


class SmokingRestriction(str, Enum):
    NON_SMOKERS = "non_smokers"              # Некурящие (стандарт)
    NON_SMOKERS_COTININE = "non_smokers_cotinine"  # Некурящие + проверка котинином
    NO_RESTRICTION = "no_restriction"         # Без ограничений


# ── Входные данные ──

class PipelineInput(BaseModel):
    """
    Входные данные от пользователя.

    ЭКРАН 1 (обязательные — минимум для старта):
        inn_ru, dosage_form, dosage, release_type

    ЭКРАН 2 (AI предлагает дизайн, пользователь подтверждает):
        AI показывает найденные ФК-параметры и предложенный дизайн.
        Пользователь может переопределить cv_intra, t_half_hours.

    ЭКРАН 3 (decision points — вопросы, которые AI не решает сам):
        sex_restriction, age_min, age_max, smoking_restriction
    """

    # ═══════════════════════════════════════════
    # ЭКРАН 1: Обязательные (4 поля)
    # ═══════════════════════════════════════════

    inn_ru: str = Field(
        ...,
        description="МНН на русском языке",
        examples=["Амлодипин"],
    )
    study_id: Optional[str] = Field(None, description="Идентификационный номер протокола")
    study_id_mode: str = Field("auto", description="Режим ID: manual / auto / empty")
    dosage_form: str = Field(
        ...,
        description="Лекарственная форма",
        examples=["таблетки"],
    )
    dosage: str = Field(
        ...,
        description="Дозировка",
        examples=["10 мг"],
    )
    release_type: ReleaseType = Field(
        default=ReleaseType.IMMEDIATE,
        description="Тип высвобождения — КРИТИЧНО для дизайна",
    )

    # ═══════════════════════════════════════════
    # ЭКРАН 2: Опционально (AI ищет, пользователь может переопределить)
    # ═══════════════════════════════════════════

    inn_en: Optional[str] = Field(
        None,
        description="INN на английском (если не указан — резолвим автоматически)",
        examples=["Amlodipine"],
    )
    drug_name_trade: Optional[str] = Field(
        None,
        description="Торговое название исследуемого препарата (дженерика)",
    )
    reference_drug_name: Optional[str] = Field(
        None,
        description="Торговое название референтного (оригинального) препарата",
    )
    intake_mode: Optional[IntakeMode] = Field(
        None,
        description="Режим приёма. Если None — определяем по инструкции оригинала",
    )
    cv_intra: Optional[float] = Field(
        None,
        description="CVintra (%) — если пользователь уже знает",
        ge=0, le=200,
    )
    t_half_hours: Optional[float] = Field(
        None,
        description="T½ (часы) — если пользователь уже знает",
        ge=0,
    )

    # ═══════════════════════════════════════════
    # ЭКРАН 3: Decision points (AI не решает сам)
    # ═══════════════════════════════════════════

    sex_restriction: Optional[str] = Field(
        default="",
        description="Пол добровольцев. Пустое = AI определит из инструкции. "
                    "Варианты: males_only, females_only, males_and_females",
    )
    age_min: int = Field(
        default=18,
        description="Минимальный возраст добровольцев",
        ge=18,
    )
    age_max: int = Field(
        default=45,
        description="Максимальный возраст добровольцев",
        le=65,
    )
    smoking_restriction: SmokingRestriction = Field(
        default=SmokingRestriction.NON_SMOKERS,
        description="Ограничения по курению",
    )

    # ═══════════════════════════════════════════
    # Организационные данные (для шапки синопсиса)
    # ═══════════════════════════════════════════

    sponsor_name: Optional[str] = Field(None, description="Спонсор исследования")
    sponsor_country: Optional[str] = Field(None, description="Страна спонсора (для поиска адреса)")
    research_center: Optional[str] = Field(None, description="Исследовательский центр")
    bioanalytical_lab: Optional[str] = Field(None, description="Биоаналитическая лаборатория")
    insurance_company: Optional[str] = Field(None, description="Страховая компания")

    # Производитель исследуемого (тестового) препарата
    manufacturer_name: Optional[str] = Field(None, description="Производитель исследуемого препарата (название)")
    manufacturer_country: Optional[str] = Field(None, description="Страна производителя")
    excipients: Optional[str] = Field(None, description="Вспомогательные вещества исследуемого препарата")
    storage_conditions: Optional[str] = Field(
        None,
        description="Условия хранения (напр. 'при температуре не выше 25°C')",
    )
    composition: Optional[str] = Field(
        None,
        description="Состав на 1 единицу лек. формы (напр. '25 мг тенофовира алафенамида')",
    )

    # Данные референтного препарата (R)
    reference_drug_form: Optional[str] = Field(None, description="Лек. форма референтного препарата")
    reference_drug_dose: Optional[str] = Field(None, description="Дозировка референтного препарата")
    reference_drug_manufacturer: Optional[str] = Field(None, description="Производитель референтного препарата")
    ref_ru_number: Optional[str] = Field(None, description="Номер РУ ЛП референтного препарата")
    follow_up_days: Optional[int] = Field(
        None,
        description="Период последующего наблюдения (дни). По умолчанию 7",
        ge=1,
    )

    # ═══════════════════════════════════════════
    # Переопределение констант расчёта
    # (по умолчанию = Решение 85 / ГОСТ Р 57679-2017)
    # ═══════════════════════════════════════════

    override_gmr: Optional[float] = Field(
        None,
        description="Ожидаемое T/R отношение (theta0). "
                    "По умолчанию 0.95. Эталон заказчика может быть 0.90",
        ge=0.8, le=1.2,
    )
    override_power: Optional[float] = Field(
        None,
        description="Мощность теста. По умолчанию 0.80 (Решение 85)",
        ge=0.5, le=0.99,
    )
    override_alpha: Optional[float] = Field(
        None,
        description="Уровень значимости. По умолчанию 0.05 (Решение 85)",
        ge=0.01, le=0.10,
    )
    override_dropout_rate: Optional[float] = Field(
        None,
        description="Dropout rate (доля выбывших). По умолчанию 0.15",
        ge=0.0, le=0.50,
    )
    override_screenfail_rate: Optional[float] = Field(
        None,
        description="Screen failure rate. По умолчанию 0.15",
        ge=0.0, le=0.50,
    )
    override_min_subjects: Optional[int] = Field(
        None,
        description="Минимальное число добровольцев. По умолчанию 18 (ГОСТ)",
        ge=6,
    )
    override_blood_per_point_ml: Optional[float] = Field(
        None,
        description="Объём крови на 1 пробу (мл). По умолчанию 5.0",
        ge=1.0, le=20.0,
    )
    override_max_blood_ml: Optional[float] = Field(
        None,
        description="Максимальный объём крови (мл). По умолчанию 450 (GCP)",
        ge=100.0,
    )
    override_washout_min_days: Optional[int] = Field(
        None,
        description="Минимальный отмывочный период (дни). "
                    "По умолчанию: max(7, ceil(5 × T½ / 24))",
        ge=1,
    )