"""
models/pk.py — Pydantic DTO для результатов PK Literature Agent.
Содержит конкретные ФК-параметры, необходимые для проектирования БЭ-исследования.
"""

from pydantic import BaseModel, Field
from typing import List, Optional


class PKSource(BaseModel):
    """Один источник PK-данных (для файла обоснований)."""
    source_type: str = Field(..., description="ohlp / pubmed / fda / ema / clinicaltrials_gov")
    url: Optional[str] = Field(None, description="URL источника")
    pmid: Optional[str] = Field(None, description="PubMed ID")
    doi: Optional[str] = Field(None, description="DOI статьи")
    title: Optional[str] = Field(None, description="Название статьи/документа")
    extracted_quote: Optional[str] = Field(None, description="Цитата, из которой извлечены данные")


class PKParameter(BaseModel):
    """Один ФК-параметр с указанием источника."""
    value: Optional[float] = Field(None, description="Числовое значение")
    unit: str = Field("", description="Единица измерения")
    source: Optional[str] = Field(None, description="Краткая ссылка на источник (PMID, URL)")
    confidence: float = Field(1.0, description="Уверенность 0-1", ge=0, le=1)


class PKResult(BaseModel):
    """Полный результат PK Literature Agent."""

    # === Идентификация ===
    inn_ru: str = Field(..., description="МНН на русском")
    inn_en: str = Field("", description="INN на английском")

    # === Ключевые ФК-параметры (нужны для Design + Sample Size) ===
    cmax: Optional[PKParameter] = Field(None, description="Cmax — максимальная концентрация (нг/мл)")
    auc_0t: Optional[PKParameter] = Field(None, description="AUC0-t — площадь под кривой (нг·ч/мл)")
    auc_0inf: Optional[PKParameter] = Field(None, description="AUC0-∞ (нг·ч/мл)")
    tmax: Optional[PKParameter] = Field(None, description="Tmax — время достижения Cmax (ч)")
    t_half: Optional[PKParameter] = Field(None, description="T½ — период полувыведения (ч)")
    cv_intra_cmax: Optional[PKParameter] = Field(None, description="CVintra для Cmax (%)")
    cv_intra_auc: Optional[PKParameter] = Field(None, description="CVintra для AUC (%)")

    # === Дополнительно ===
    is_hvd: bool = Field(False, description="High Variability Drug (CVintra ≥ 30%)")
    is_nti: bool = Field(False, description="Narrow Therapeutic Index")
    bcs_class: Optional[str] = Field(None, description="BCS класс (I, II, III, IV)")

    # === Референтный препарат (иерархия по Решению №85) ===
    reference_drug: Optional[str] = Field(None, description="Название референтного препарата")
    reference_source: Optional[str] = Field(None, description="Откуда (ЕАЭС, FDA, EMA...)")

    # === Обзор и источники ===
    literature_review: str = Field("", description="Текстовый обзор (2-3 абзаца)")
    sources: List[PKSource] = Field(default_factory=list, description="Все использованные источники")

    @property
    def cv_intra_max(self) -> Optional[float]:
        """Наибольший CVintra (для расчёта выборки берём наибольший)."""
        vals = []
        if self.cv_intra_cmax and self.cv_intra_cmax.value is not None:
            vals.append(self.cv_intra_cmax.value)
        if self.cv_intra_auc and self.cv_intra_auc.value is not None:
            vals.append(self.cv_intra_auc.value)
        return max(vals) if vals else None

    @property
    def t_half_hours(self) -> Optional[float]:
        """T½ в часах (удобный accessor)."""
        return self.t_half.value if self.t_half else None