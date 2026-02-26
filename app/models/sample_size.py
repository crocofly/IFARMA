"""
models/sample_size.py — DTO результата Sample Size Agent.
"""

from pydantic import BaseModel, Field


class SampleSizeResult(BaseModel):
    """Результат расчёта размера выборки."""

    # === Расчётные значения ===
    n_base: int = Field(..., description="Базовый размер по формуле")
    n_with_dropout: int = Field(..., description="С учётом dropout")
    n_with_screenfail: int = Field(..., description="С учётом screen-fail")
    n_total: int = Field(..., description="Итоговый (округлён до чётного, ≥ 12)")

    # === Параметры расчёта ===
    cv_intra_used: float = Field(..., description="CVintra (%), использованный в расчёте")
    power: float = Field(0.80, description="Статистическая мощность")
    alpha: float = Field(0.05, description="Уровень значимости")
    gmr: float = Field(0.95, description="Ожидаемое T/R отношение (GMR)")
    theta: float = Field(1.25, description="Верхняя граница БЭ")
    dropout_rate: float = Field(0.12, description="Доля dropout")
    screenfail_rate: float = Field(0.15, description="Доля screen-fail")

    # === Объём крови ===
    blood_volume_ml: float = Field(0.0, description="Общий объём крови (мл)")
    blood_volume_ok: bool = Field(True, description="Не превышает 450 мл")

    # === Текстовое описание ===
    calculation_description: str = Field("", description="Описание расчёта для синопсиса")
