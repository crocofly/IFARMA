"""
Regulatory Agent — Checklist for EAEU Council Decision No. 85
"Rules for Conducting Bioequivalence Studies of Medicinal Products within the EAEU"

Architecture: Deterministic rule engine (no LLM).
Each check returns: CheckResult(id, section, description, status, detail)
Statuses: PASS | FAIL | WARNING | NA | MISSING_DATA
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
import json
import math


# ────────────────────────────────────────────────────────────────
# Core data types
# ────────────────────────────────────────────────────────────────

class Status(str, Enum):
    PASS         = "PASS"
    FAIL         = "FAIL"
    WARNING      = "WARNING"
    NA           = "NA"
    MISSING_DATA = "MISSING_DATA"


@dataclass
class CheckResult:
    id: str
    section: str
    rule: str
    status: Status
    detail: str
    reference: str = ""   # paragraph / article in Decision 85


@dataclass
class StudyData:
    """
    All input data for a single bioequivalence study.
    Pass None for any field that is not known — the agent will emit MISSING_DATA.
    """
    # ── 1. Drug / dosage form ─────────────────────────────────
    dosage_form: Optional[str] = None          # e.g. "tablet_ir", "tablet_mr", "capsule_ir", "solution", "transdermal", "inhalation"
    is_generic: Optional[bool] = None          # True = воспроизведённый, False = гибридный
    is_biological: Optional[bool] = None
    is_botanical: Optional[bool] = None
    is_narrow_therapeutic: Optional[bool] = None   # узкий терапевтический диапазон
    bcs_class: Optional[int] = None            # 1-4 (BCS класс)
    drug_substance_solubility_high: Optional[bool] = None
    drug_substance_permeability_high: Optional[bool] = None
    is_endogenous: Optional[bool] = None       # эндогенное вещество
    is_prodrug_inactive: Optional[bool] = None # неактивное пролекарство

    # ── 2. Study design ──────────────────────────────────────
    design: Optional[str] = None               # "crossover_2period", "parallel", "replicate_3period", "replicate_4period"
    n_subjects_enrolled: Optional[int] = None
    n_subjects_completed: Optional[int] = None
    n_subjects_in_analysis: Optional[int] = None
    washout_periods: Optional[int] = None       # number of half-lives
    washout_days: Optional[float] = None
    drug_halflife_h: Optional[float] = None    # T½ часов

    # ── 3. Subjects ───────────────────────────────────────────
    subject_age_min: Optional[int] = None
    subject_age_max: Optional[int] = None
    bmi_min: Optional[float] = None
    bmi_max: Optional[float] = None
    both_sexes_included: Optional[bool] = None
    subjects_healthy: Optional[bool] = None    # здоровые добровольцы vs пациенты

    # ── 4. Conditions ─────────────────────────────────────────
    fasting_hours_before: Optional[float] = None   # голодание перед приемом
    water_ml_with_dose: Optional[float] = None      # мл воды при приеме
    food_restriction_hours_after: Optional[float] = None  # ограничение пищи после
    standardised_diet: Optional[bool] = None
    fed_study_done: Optional[bool] = None
    fasted_study_done: Optional[bool] = None
    reference_smpc_fasting: Optional[str] = None   # "fasting", "fed", "both", "any"

    # ── 5. Reference product ─────────────────────────────────
    reference_product_defined: Optional[bool] = None
    reference_is_originator: Optional[bool] = None
    reference_batch_tested: Optional[bool] = None  # ТСКР (ИВКР) для серии
    reference_within_expiry: Optional[bool] = None

    # ── 6. Test product ──────────────────────────────────────
    test_gmp_confirmed: Optional[bool] = None
    test_batch_size_industrial: Optional[bool] = None  # промышленная серия или пилотная
    test_batch_dissolution_tested: Optional[bool] = None

    # ── 7. Sampling / PK ─────────────────────────────────────
    sampling_points_n: Optional[int] = None       # число временных точек
    sampling_covers_80pct_auc: Optional[bool] = None  # AUC(0-t) ≥ 80% AUC(0-∞)
    terminal_samples_n: Optional[int] = None       # точек в терминальной фазе
    biological_matrix: Optional[str] = None        # "plasma", "blood", "urine", "serum"
    analyte: Optional[str] = None                  # "parent", "active_metabolite", "inactive_metabolite"

    # ── 8. PK parameters & statistics ───────────────────────
    pk_auc_0t_ratio: Optional[float] = None        # GMR Test/Ref AUC(0-t), %
    pk_cmax_ratio: Optional[float] = None          # GMR Cmax, %
    pk_auc_0inf_ratio: Optional[float] = None      # GMR AUC(0-∞), %
    ci_auc_lower: Optional[float] = None           # нижняя граница 90% ДИ AUC, %
    ci_auc_upper: Optional[float] = None           # верхняя граница 90% ДИ AUC, %
    ci_cmax_lower: Optional[float] = None
    ci_cmax_upper: Optional[float] = None
    statistical_method: Optional[str] = None       # "anova_log", "other"
    ci_level_pct: Optional[float] = None           # 90 or 95

    # ── 9. High-variability / NTI adjustments ────────────────
    intrasubject_cv_auc_pct: Optional[float] = None
    intrasubject_cv_cmax_pct: Optional[float] = None
    expanded_limits_justified: Optional[bool] = None  # расширенные границы обоснованы
    ci_cmax_lower_expanded: Optional[float] = None
    ci_cmax_upper_expanded: Optional[float] = None
    nti_ci_auc_lower: Optional[float] = None   # для NTI
    nti_ci_auc_upper: Optional[float] = None
    nti_ci_cmax_lower: Optional[float] = None
    nti_ci_cmax_upper: Optional[float] = None

    # ── 10. In-vitro dissolution (ТСКР) ──────────────────────
    ivivc_f2_ph12: Optional[float] = None
    ivivc_f2_ph45: Optional[float] = None
    ivivc_f2_ph68: Optional[float] = None
    dissolution_85pct_in_15min: Optional[bool] = None  # ≥85% за 15 мин → f2 не нужен

    # ── 11. Biowaiver ────────────────────────────────────────
    biowaiver_requested: Optional[bool] = None
    biowaiver_basis: Optional[str] = None      # "bcs", "additional_strength", "post_approval_change"
    bcs_biowaiver_eligible: Optional[bool] = None

    # ── 12. Study report ─────────────────────────────────────
    report_signed_by_investigator: Optional[bool] = None
    report_contains_protocol: Optional[bool] = None
    report_contains_bioanalytical_report: Optional[bool] = None
    raw_data_available: Optional[bool] = None
    individual_pk_curves_provided: Optional[bool] = None
    outlier_handling_prespecified: Optional[bool] = None
    exclusion_criteria_prespecified: Optional[bool] = None

    # ── 13. Bioanalytical method ─────────────────────────────
    bioanalytical_method_validated: Optional[bool] = None
    incurred_sample_reanalysis_done: Optional[bool] = None

    # ── 14. GMP / manufacturing ──────────────────────────────
    studies_outside_union: Optional[bool] = None  # проведены за пределами ЕАЭС
    studies_outside_comply: Optional[bool] = None  # соответствуют требованиям

    # ── 15. Modifications (Section VI) ───────────────────────
    post_approval_change: Optional[bool] = None
    change_type: Optional[str] = None   # "excipient", "manufacturing", "site", "scale", "dosage_form"


# ────────────────────────────────────────────────────────────────
# Helper
# ────────────────────────────────────────────────────────────────

def _check(id_, section, rule, ref, condition: Optional[bool], detail_pass="", detail_fail="",
           detail_missing="Данные не предоставлены") -> CheckResult:
    if condition is None:
        return CheckResult(id_, section, rule, Status.MISSING_DATA, detail_missing, ref)
    if condition:
        return CheckResult(id_, section, rule, Status.PASS, detail_pass or "Соответствует", ref)
    return CheckResult(id_, section, rule, Status.FAIL, detail_fail or "Не соответствует", ref)


def _warn(id_, section, rule, ref, condition: Optional[bool], detail_warn="", detail_ok="") -> CheckResult:
    if condition is None:
        return CheckResult(id_, section, rule, Status.MISSING_DATA, "Данные не предоставлены", ref)
    if condition:
        return CheckResult(id_, section, rule, Status.WARNING, detail_warn or "Требует внимания", ref)
    return CheckResult(id_, section, rule, Status.PASS, detail_ok or "Соответствует", ref)


def _na(id_, section, rule, ref, reason="Не применимо для данного препарата/дизайна") -> CheckResult:
    return CheckResult(id_, section, rule, Status.NA, reason, ref)


# ────────────────────────────────────────────────────────────────
# Rule modules
# ────────────────────────────────────────────────────────────────

class RulesSection1_General:
    """Раздел I. Общие положения (пп. 1–10)"""

    @staticmethod
    def check_scope(d: StudyData) -> list[CheckResult]:
        results = []
        # п.7: биологические препараты — иные правила
        if d.is_biological:
            results.append(CheckResult("GEN-001", "I. Общие положения", 
                "Биологические препараты",
                Status.WARNING,
                "Биологические ЛП: настоящие Правила не применяются. "
                "Требуются отдельные правила для биологических ЛП ЕАЭС.",
                "п. 7 Правил"))
        # п.9: GMP
        results.append(_check("GEN-002", "I. Общие положения",
            "GMP-подтверждение для исследуемого ЛП",
            "п. 9 Правил",
            d.test_gmp_confirmed,
            "GMP-соответствие подтверждено",
            "GMP-соответствие НЕ подтверждено — обязательно для регистрационного досье"))
        # п.9: внешние исследования
        if d.studies_outside_union:
            results.append(_check("GEN-003", "I. Общие положения",
                "Исследования за пределами ЕАЭС соответствуют Правилам 85",
                "п. 9 Правил",
                d.studies_outside_comply,
                "Исследования вне ЕАЭС соответствуют Правилам 85",
                "Исследования вне ЕАЭС должны соответствовать Правилам 85 и праву Союза"))
        return results


class RulesSection3_Design:
    """Раздел III. Требования к дизайну исследований"""

    @staticmethod
    def check_design(d: StudyData) -> list[CheckResult]:
        results = []

        # п.13: стандартный дизайн — перекрёстный 2-периодный
        if d.design is not None:
            parallel = d.design == "parallel"
            crossover = "crossover" in (d.design or "")
            replicate = "replicate" in (d.design or "")

            if parallel:
                results.append(CheckResult("DES-001", "III. Дизайн",
                    "Параллельный дизайн — обоснование",
                    Status.WARNING,
                    "Параллельный дизайн применяется только при невозможности перекрёстного "
                    "(длительный T½, специфический ЛП). Требуется обоснование.",
                    "п. 14 Правил"))
            elif crossover:
                results.append(CheckResult("DES-001", "III. Дизайн",
                    "Перекрёстный дизайн",
                    Status.PASS,
                    "Стандартный перекрёстный дизайн соответствует требованиям",
                    "п. 13 Правил"))
            elif replicate:
                results.append(CheckResult("DES-001", "III. Дизайн",
                    "Повторный (replicate) дизайн",
                    Status.PASS,
                    "Повторный дизайн применим для ВВП-препаратов (п. 109)",
                    "п. 109, 110 Правил"))

        # Washout period ≥ 5 T½ (п.13)
        if d.washout_periods is not None:
            results.append(_check("DES-002", "III. Дизайн",
                "Отмывочный период ≥ 5 периодов полувыведения",
                "п. 13 Правил",
                d.washout_periods >= 5,
                f"Отмывочный период: {d.washout_periods} T½ — соответствует",
                f"Отмывочный период: {d.washout_periods} T½ — недостаточно (нужно ≥ 5 T½)"))
        elif d.washout_days is not None and d.drug_halflife_h is not None:
            t_half_days = d.drug_halflife_h / 24
            required_days = 5 * t_half_days
            ok = d.washout_days >= required_days
            results.append(_check("DES-002", "III. Дизайн",
                "Отмывочный период ≥ 5 периодов полувыведения",
                "п. 13 Правил",
                ok,
                f"Отмывочный период {d.washout_days:.1f} дн ≥ {required_days:.1f} дн (5×T½) — OK",
                f"Отмывочный период {d.washout_days:.1f} дн < {required_days:.1f} дн (5×T½) — FAIL"))

        return results

    @staticmethod
    def check_subjects(d: StudyData) -> list[CheckResult]:
        results = []

        # Минимальное число субъектов в анализе ≥ 12 (п.27 Правил)
        if d.n_subjects_in_analysis is not None:
            results.append(_check("SUB-001", "III. Субъекты",
                "Минимальное число субъектов в анализе ≥ 12",
                "п. 27 Правил",
                d.n_subjects_in_analysis >= 12,
                f"Субъектов в анализе: {d.n_subjects_in_analysis} ≥ 12 — OK",
                f"Субъектов в анализе: {d.n_subjects_in_analysis} < 12 — нарушение минимума"))

        # Возраст ≥ 18 лет (п.29)
        if d.subject_age_min is not None:
            results.append(_check("SUB-002", "III. Субъекты",
                "Минимальный возраст субъектов ≥ 18 лет",
                "п. 29 Правил",
                d.subject_age_min >= 18,
                f"Мин. возраст: {d.subject_age_min} лет — OK",
                f"Мин. возраст: {d.subject_age_min} лет < 18 — FAIL"))

        # ИМТ 18.5–30 кг/м² (п.28)
        if d.bmi_min is not None and d.bmi_max is not None:
            bmi_ok = d.bmi_min >= 18.5 and d.bmi_max <= 30
            results.append(_check("SUB-003", "III. Субъекты",
                "ИМТ субъектов в диапазоне 18,5–30 кг/м²",
                "п. 28 Правил",
                bmi_ok,
                f"ИМТ {d.bmi_min}–{d.bmi_max} кг/м² — OK",
                f"ИМТ {d.bmi_min}–{d.bmi_max} кг/м² — выходит за пределы 18,5–30"))

        # Здоровые добровольцы (п.26)
        if d.subjects_healthy is not None:
            if not d.subjects_healthy:
                results.append(CheckResult("SUB-004", "III. Субъекты",
                    "Пациенты вместо здоровых добровольцев",
                    Status.WARNING,
                    "Участие пациентов вместо здоровых добровольцев требует обоснования "
                    "(соображения безопасности, фармакокинетика)",
                    "п. 26 Правил"))
            else:
                results.append(CheckResult("SUB-004", "III. Субъекты",
                    "Здоровые добровольцы",
                    Status.PASS, "Здоровые добровольцы — соответствует стандарту", "п. 26 Правил"))

        return results

    @staticmethod
    def check_conditions(d: StudyData) -> list[CheckResult]:
        results = []

        # Голодание ≥ 8 часов (п.29)
        if d.fasting_hours_before is not None:
            results.append(_check("CON-001", "III. Условия",
                "Голодание перед приёмом ЛП ≥ 8 часов",
                "п. 29 Правил",
                d.fasting_hours_before >= 8,
                f"Голодание: {d.fasting_hours_before} ч — OK",
                f"Голодание: {d.fasting_hours_before} ч < 8 ч — нарушение"))

        # Вода при приёме — 150–240 мл (п.29, стандарт ≈ 240 мл; документ упоминает 20 мл для ТДП)
        if d.water_ml_with_dose is not None:
            if d.dosage_form in ("odt", "film_odt"):
                # для ТДП — 20 мл
                ok = d.water_ml_with_dose == 20
                results.append(_check("CON-002", "III. Условия",
                    "Объём воды при приёме ТДП = 20 мл",
                    "Приложение 1, п. III Правил",
                    ok,
                    f"{d.water_ml_with_dose} мл — OK",
                    f"{d.water_ml_with_dose} мл — ожидалось 20 мл для ТДП"))
            else:
                ok = 150 <= d.water_ml_with_dose <= 250
                results.append(_check("CON-002", "III. Условия",
                    "Объём воды при приёме ЛП 150–250 мл",
                    "п. 29 Правил",
                    ok,
                    f"{d.water_ml_with_dose} мл — OK",
                    f"{d.water_ml_with_dose} мл — выходит за стандартный диапазон 150–250 мл"))

        # Ограничение пищи после приёма ≥ 4 часа (п.30)
        if d.food_restriction_hours_after is not None:
            results.append(_check("CON-003", "III. Условия",
                "Ограничение приёма пищи после ЛП ≥ 4 часа",
                "п. 30 Правил",
                d.food_restriction_hours_after >= 4,
                f"Ограничение пищи: {d.food_restriction_hours_after} ч — OK",
                f"Ограничение пищи: {d.food_restriction_hours_after} ч < 4 ч — FAIL"))

        # Стандартизированный рацион (п.30)
        results.append(_check("CON-004", "III. Условия",
            "Рацион питания стандартизирован",
            "п. 30 Правил",
            d.standardised_diet,
            "Рацион стандартизирован — OK",
            "Рацион питания НЕ стандартизирован"))

        # Выбор исследования натощак/после еды согласно СмПК (пп.31–34)
        if d.reference_smpc_fasting is not None:
            if d.reference_smpc_fasting == "fasting":
                if d.fasted_study_done is not None:
                    results.append(_check("CON-005", "III. Условия",
                        "Исследование натощак проведено (СмПК: натощак)",
                        "п. 31 Правил",
                        d.fasted_study_done,
                        "Исследование натощак — OK", "Исследование натощак НЕ проведено — FAIL"))
            elif d.reference_smpc_fasting == "fed":
                if d.fed_study_done is not None:
                    results.append(_check("CON-005", "III. Условия",
                        "Исследование после еды проведено (СмПК: после еды)",
                        "п. 32 Правил",
                        d.fed_study_done,
                        "Исследование после еды — OK", "Исследование после еды НЕ проведено — FAIL"))
            elif d.reference_smpc_fasting == "both":
                both = bool(d.fed_study_done and d.fasted_study_done)
                results.append(_check("CON-005", "III. Условия",
                    "Оба исследования (натощак и после еды) проведены",
                    "п. 31–32 Правил",
                    both,
                    "Оба исследования проведены — OK",
                    "Не оба исследования проведены — FAIL"))

        return results

    @staticmethod
    def check_sampling_pk(d: StudyData) -> list[CheckResult]:
        results = []

        # ≥ 3 точек в терминальной фазе (п.36)
        if d.terminal_samples_n is not None:
            results.append(_check("SAM-001", "III. Отбор образцов",
                "≥ 3–4 точки в терминальной фазе элиминации",
                "п. 36 Правил",
                d.terminal_samples_n >= 3,
                f"Терминальных точек: {d.terminal_samples_n} — OK",
                f"Терминальных точек: {d.terminal_samples_n} < 3 — FAIL"))

        # AUC(0-t) ≥ 80% AUC(0-∞) (п.36)
        if d.sampling_covers_80pct_auc is not None:
            results.append(_check("SAM-002", "III. Отбор образцов",
                "AUC(0–t) охватывает ≥ 80% AUC(0–∞)",
                "п. 36 Правил",
                d.sampling_covers_80pct_auc,
                "AUC(0–t)/AUC(0–∞) ≥ 80% — OK",
                "AUC(0–t)/AUC(0–∞) < 80% — недостаточный период наблюдения"))

        # Плазма крови — предпочтительный матрикс (п.39)
        if d.biological_matrix is not None:
            if d.biological_matrix != "plasma":
                results.append(CheckResult("SAM-003", "III. Биологический матрикс",
                    "Использование матрикса, отличного от плазмы",
                    Status.WARNING,
                    f"Матрикс: '{d.biological_matrix}'. Плазма — предпочтительный матрикс. "
                    "Требуется обоснование выбора альтернативного матрикса.",
                    "п. 39 Правил"))
            else:
                results.append(CheckResult("SAM-003", "III. Биологический матрикс",
                    "Плазма крови как биологический матрикс",
                    Status.PASS, "Плазма — предпочтительный матрикс — OK", "п. 39 Правил"))

        # Аналит: исходное соединение vs. метаболит (п.40)
        if d.analyte is not None:
            if d.analyte == "inactive_metabolite":
                results.append(CheckResult("SAM-004", "III. Аналит",
                    "Использование неактивного метаболита вместо исходного соединения",
                    Status.WARNING,
                    "Замена исходного соединения его неактивным метаболитом требует "
                    "специального обоснования согласно п. 42–44 Правил.",
                    "п. 42–44 Правил"))
            elif d.analyte == "active_metabolite" and not (d.is_prodrug_inactive or False):
                results.append(CheckResult("SAM-004", "III. Аналит",
                    "Активный метаболит вместо исходного соединения",
                    Status.WARNING,
                    "Использование только активного метаболита допустимо лишь в случаях, "
                    "указанных в п. 43 Правил (нечувствительность метода и др.).",
                    "п. 43 Правил"))

        return results

    @staticmethod
    def check_reference_product(d: StudyData) -> list[CheckResult]:
        results = []

        results.append(_check("REF-001", "III. Референтный ЛП",
            "Референтный ЛП идентифицирован",
            "п. 18 Правил",
            d.reference_product_defined,
            "Референтный ЛП определён — OK",
            "Референтный ЛП НЕ определён"))

        results.append(_check("REF-002", "III. Референтный ЛП",
            "Серия референтного ЛП в пределах срока годности",
            "п. 22 Правил",
            d.reference_within_expiry,
            "Серия в пределах срока годности — OK",
            "Серия референтного ЛП с истёкшим сроком годности — FAIL"))

        results.append(_check("REF-003", "III. Референтный ЛП",
            "ТСКР серии референтного ЛП выполнен",
            "п. 22 Правил",
            d.reference_batch_tested,
            "ТСКР выполнен — OK",
            "ТСКР серии референтного ЛП НЕ выполнен"))

        return results


class RulesSection3_Statistics:
    """Раздел III. Статистическая оценка (пп. 86–110)"""

    @staticmethod
    def check_ci_method(d: StudyData) -> list[CheckResult]:
        results = []

        # Метод: ANOVA с лог-преобразованием + 90% ДИ (п.86–90)
        if d.statistical_method is not None:
            results.append(_check("STAT-001", "III. Статистика",
                "Метод анализа: ANOVA с лог-преобразованием",
                "п. 87–90 Правил",
                d.statistical_method == "anova_log",
                "ANOVA с лог-преобразованием — OK",
                f"Метод '{d.statistical_method}' — ожидается ANOVA с лог-преобразованием. "
                "Непараметрические методы не допускаются (п. 89 Правил)"))

        if d.ci_level_pct is not None:
            if d.is_narrow_therapeutic:
                ok = d.ci_level_pct == 90  # фактически 90% ДИ, но более узкие границы
            else:
                ok = d.ci_level_pct == 90
            results.append(_check("STAT-002", "III. Статистика",
                "Уровень доверительного интервала 90%",
                "п. 86 Правил",
                ok,
                f"ДИ {d.ci_level_pct}% — OK",
                f"ДИ {d.ci_level_pct}% — требуется 90%"))

        return results

    @staticmethod
    def check_acceptance_limits(d: StudyData) -> list[CheckResult]:
        """
        Стандартные пределы 80,00–125,00% (п. 86).
        NTI: 90,00–111,11% (п. 100).
        HVD (высоко-вариабельные): расширение Cmax, но AUC всегда 80–125%.
        """
        results = []

        # --- Determine which limits apply ---
        is_nti = bool(d.is_narrow_therapeutic)
        is_hv_cmax = (d.intrasubject_cv_cmax_pct or 0) >= 30
        is_hv_auc  = (d.intrasubject_cv_auc_pct or 0) >= 30

        # ── AUC limits ──────────────────────────────────────────
        if d.ci_auc_lower is not None and d.ci_auc_upper is not None:
            if is_nti:
                lo, hi = 90.00, 111.11
                rule_ref = "п. 100 Правил (NTI)"
            else:
                lo, hi = 80.00, 125.00
                rule_ref = "п. 86 Правил"

            auc_ok = d.ci_auc_lower >= lo and d.ci_auc_upper <= hi
            results.append(_check("ACC-001", "III. Допустимые пределы",
                f"90% ДИ AUC в пределах {lo:.2f}–{hi:.2f}%",
                rule_ref,
                auc_ok,
                f"90% ДИ AUC [{d.ci_auc_lower:.2f}; {d.ci_auc_upper:.2f}]% ∈ [{lo:.2f}; {hi:.2f}]% — PASS",
                f"90% ДИ AUC [{d.ci_auc_lower:.2f}; {d.ci_auc_upper:.2f}]% ∉ [{lo:.2f}; {hi:.2f}]% — FAIL"))

        # ── Cmax limits ─────────────────────────────────────────
        if d.ci_cmax_lower is not None and d.ci_cmax_upper is not None:
            if is_nti:
                lo_c, hi_c = 90.00, 111.11
                rule_ref_c = "п. 100 Правил (NTI)"
                ci_l = d.nti_ci_cmax_lower if d.nti_ci_cmax_lower else d.ci_cmax_lower
                ci_u = d.nti_ci_cmax_upper if d.nti_ci_cmax_upper else d.ci_cmax_upper
            elif is_hv_cmax and d.expanded_limits_justified:
                # Expanded limits based on CV (п.104–109), max 69.84–143.19%
                cv = d.intrasubject_cv_cmax_pct
                lo_c, hi_c = _expanded_cmax_limits(cv)
                ci_l = d.ci_cmax_lower_expanded or d.ci_cmax_lower
                ci_u = d.ci_cmax_upper_expanded or d.ci_cmax_upper
                rule_ref_c = f"п. 109 Правил (HVD, CV={cv:.0f}%): [{lo_c:.2f}; {hi_c:.2f}]%"
            else:
                lo_c, hi_c = 80.00, 125.00
                ci_l = d.ci_cmax_lower
                ci_u = d.ci_cmax_upper
                rule_ref_c = "п. 86 Правил"

            cmax_ok = ci_l >= lo_c and ci_u <= hi_c
            results.append(_check("ACC-002", "III. Допустимые пределы",
                f"90% ДИ Cmax в пределах {lo_c:.2f}–{hi_c:.2f}%",
                rule_ref_c,
                cmax_ok,
                f"90% ДИ Cmax [{ci_l:.2f}; {ci_u:.2f}]% ∈ [{lo_c:.2f}; {hi_c:.2f}]% — PASS",
                f"90% ДИ Cmax [{ci_l:.2f}; {ci_u:.2f}]% ∉ [{lo_c:.2f}; {hi_c:.2f}]% — FAIL"))

        # HVD warning
        if is_hv_cmax and not d.expanded_limits_justified:
            results.append(CheckResult("ACC-003", "III. Допустимые пределы",
                "Высоковариабельный ЛП: расширение пределов Cmax",
                Status.WARNING,
                f"Внутрииндивидуальный CV Cmax = {d.intrasubject_cv_cmax_pct:.0f}% ≥ 30%: "
                "возможно расширение пределов Cmax (п. 104). Требуется повторный дизайн и обоснование.",
                "п. 104–109 Правил"))

        # AUC never expanded even for HVD
        if is_hv_auc and d.expanded_limits_justified:
            results.append(CheckResult("ACC-004", "III. Допустимые пределы",
                "AUC: расширение пределов не применяется даже для HVD",
                Status.WARNING,
                "Расширение пределов биодоступности на основе вариабельности НЕ распространяется на AUC: "
                "границы AUC всегда 80,00–125,00% (п. 109 Правил).",
                "п. 109 Правил"))

        return results


def _expanded_cmax_limits(cv_pct: float) -> tuple[float, float]:
    """
    Таблица расширенных пределов Cmax (п. 109, Правила 85).
    CV (%) → (нижняя, верхняя) в %.
    """
    table = [
        (30, 80.00, 125.00),
        (35, 77.23, 129.48),
        (40, 74.62, 134.02),
        (45, 72.15, 138.59),
        (50, 69.84, 143.19),
    ]
    for cv_t, lo, hi in reversed(table):
        if cv_pct >= cv_t:
            return lo, hi
    return 80.00, 125.00


class RulesSection4_IVIVC:
    """Раздел IV. Тест сравнительной кинетики растворения (ТСКР)"""

    @staticmethod
    def check_f2(d: StudyData) -> list[CheckResult]:
        results = []

        # Если ≥ 85% растворяется за 15 мин → f2 не нужен (п.41)
        if d.dissolution_85pct_in_15min:
            results.append(CheckResult("IV-001", "IV. ТСКР",
                "Растворение ≥ 85% за 15 мин → f2 не требуется",
                Status.PASS,
                "≥85% действующего вещества растворяется за 15 мин — расчёт f2 не нужен.",
                "п. 41 Правил"))
            return results

        # f2 ≥ 50 для каждого pH (п.41)
        for ph_label, f2_val in [
            ("pH 1,2", d.ivivc_f2_ph12),
            ("pH 4,5", d.ivivc_f2_ph45),
            ("pH 6,8", d.ivivc_f2_ph68),
        ]:
            if f2_val is not None:
                results.append(_check(f"IV-001-{ph_label}", "IV. ТСКР",
                    f"f2 ≥ 50 при {ph_label}",
                    "п. 41 Правил",
                    f2_val >= 50,
                    f"f2({ph_label}) = {f2_val:.1f} ≥ 50 — OK",
                    f"f2({ph_label}) = {f2_val:.1f} < 50 — профили растворения НЕ подобны"))

        return results


class RulesSection5_Report:
    """Раздел V. Отчёт об исследовании"""

    @staticmethod
    def check_report(d: StudyData) -> list[CheckResult]:
        results = []

        results.append(_check("RPT-001", "V. Отчёт",
            "Отчёт подписан ответственным исследователем",
            "п. 118 Правил",
            d.report_signed_by_investigator,
            "Отчёт подписан — OK",
            "Отчёт НЕ подписан исследователем — FAIL"))

        results.append(_check("RPT-002", "V. Отчёт",
            "Отчёт содержит протокол исследования",
            "п. 118 Правил",
            d.report_contains_protocol,
            "Протокол включён в отчёт — OK",
            "Протокол НЕ включён в отчёт"))

        results.append(_check("RPT-003", "V. Отчёт",
            "Биоаналитический отчёт и валидация приложены",
            "п. 119 Правил",
            d.report_contains_bioanalytical_report,
            "Биоаналитический отчёт приложен — OK",
            "Биоаналитический отчёт отсутствует"))

        results.append(_check("RPT-004", "V. Отчёт",
            "Индивидуальные ФК-кривые предоставлены",
            "п. 116 Правил",
            d.individual_pk_curves_provided,
            "Индивидуальные кривые приложены — OK",
            "Индивидуальные ФК-кривые отсутствуют"))

        results.append(_check("RPT-005", "V. Отчёт",
            "Исходные данные доступны по запросу",
            "п. 120 Правил",
            d.raw_data_available,
            "Исходные данные доступны — OK",
            "Исходные данные недоступны"))

        results.append(_check("RPT-006", "V. Отчёт",
            "Критерии исключения субъектов заранее прописаны в протоколе",
            "п. 71, 72 Правил",
            d.exclusion_criteria_prespecified,
            "Критерии исключения преспецифицированы — OK",
            "Критерии исключения НЕ преспецифицированы — FAIL"))

        results.append(_check("RPT-007", "V. Отчёт",
            "Алгоритм работы с выбросами описан в протоколе заранее",
            "п. 96 Правил",
            d.outlier_handling_prespecified,
            "Работа с выбросами преспецифицирована — OK",
            "Работа с выбросами НЕ преспецифицирована в протоколе"))

        return results


class RulesBioanalytical:
    """Биоаналитическая методология"""

    @staticmethod
    def check(d: StudyData) -> list[CheckResult]:
        results = []

        results.append(_check("BIO-001", "III. Биоаналитика",
            "Биоаналитическая методика валидирована",
            "п. 64 Правил",
            d.bioanalytical_method_validated,
            "Методика валидирована — OK",
            "Биоаналитическая методика НЕ валидирована — FAIL"))

        results.append(_check("BIO-002", "III. Биоаналитика",
            "Повторный анализ инкурированных образцов (ISR) выполнен",
            "п. 66 Правил",
            d.incurred_sample_reanalysis_done,
            "ISR выполнен — OK",
            "ISR (повторный анализ) НЕ выполнен"))

        return results


class RulesBiowaiver:
    """Биовейвер (п. 5, приложение 4)"""

    @staticmethod
    def check(d: StudyData) -> list[CheckResult]:
        results = []
        if not d.biowaiver_requested:
            return results

        # NTI → биовейвер BCS не применим (приложение 4)
        if d.is_narrow_therapeutic and d.biowaiver_basis == "bcs":
            results.append(CheckResult("BIO-W001", "Биовейвер",
                "NTI-препараты: биовейвер BCS не применяется",
                Status.FAIL,
                "Для лекарственных препаратов с узким терапевтическим диапазоном "
                "биовейвер на основе БКС НЕ допускается (приложение 4, п. 8).",
                "Приложение 4, п. 8 Правил"))

        # BCS класс 1 или 3 → потенциально применим
        if d.bcs_class is not None:
            if d.bcs_class in (1, 3):
                results.append(CheckResult("BIO-W002", "Биовейвер",
                    f"BCS класс {d.bcs_class}: биовейвер потенциально применим",
                    Status.PASS,
                    f"BCS класс {d.bcs_class} — соответствует критериям биовейвера. "
                    "Требуется подтверждение растворимости и проницаемости.",
                    "Приложение 4 Правил"))
            else:
                results.append(CheckResult("BIO-W002", "Биовейвер",
                    f"BCS класс {d.bcs_class}: биовейвер НЕ применим",
                    Status.FAIL,
                    f"BCS класс {d.bcs_class} не соответствует критериям биовейвера "
                    "(применимо только для классов 1 и 3).",
                    "Приложение 4 Правил"))

        return results


# ────────────────────────────────────────────────────────────────
# Main Agent
# ────────────────────────────────────────────────────────────────

class RegulatoryAgent85:
    """
    Regulatory Agent — Decision EAEU No. 85.
    Checks a StudyData object against all rules and returns a checklist.
    """

    def run(self, data: StudyData) -> dict:
        results: list[CheckResult] = []

        results += RulesSection1_General.check_scope(data)
        results += RulesSection3_Design.check_design(data)
        results += RulesSection3_Design.check_subjects(data)
        results += RulesSection3_Design.check_conditions(data)
        results += RulesSection3_Design.check_sampling_pk(data)
        results += RulesSection3_Design.check_reference_product(data)
        results += RulesSection3_Statistics.check_ci_method(data)
        results += RulesSection3_Statistics.check_acceptance_limits(data)
        results += RulesSection4_IVIVC.check_f2(data)
        results += RulesBioanalytical.check(data)
        results += RulesSection5_Report.check_report(data)
        results += RulesBiowaiver.check(data)

        summary = self._summarise(results)
        return {"summary": summary, "checks": [self._to_dict(r) for r in results]}

    @staticmethod
    def _summarise(results: list[CheckResult]) -> dict:
        counts = {s: 0 for s in Status}
        for r in results:
            counts[r.status] += 1
        total = len(results)
        evaluated = total - counts[Status.NA] - counts[Status.MISSING_DATA]
        passed = counts[Status.PASS]
        failed = counts[Status.FAIL]
        warnings = counts[Status.WARNING]
        verdict = "PASS" if failed == 0 and evaluated > 0 else ("FAIL" if failed > 0 else "INSUFFICIENT_DATA")
        return {
            "verdict": verdict,
            "total_checks": total,
            "pass": passed,
            "fail": failed,
            "warning": warnings,
            "na": counts[Status.NA],
            "missing_data": counts[Status.MISSING_DATA],
        }

    @staticmethod
    def _to_dict(r: CheckResult) -> dict:
        return {
            "id": r.id,
            "section": r.section,
            "rule": r.rule,
            "status": r.status.value,
            "detail": r.detail,
            "reference": r.reference,
        }


# ────────────────────────────────────────────────────────────────
# CLI / demo
# ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1].endswith(".json"):
        with open(sys.argv[1]) as f:
            raw = json.load(f)
        raw = {k: v for k, v in raw.items() if not k.startswith("_")}
        data = StudyData(**raw)
    else:
        # Built-in demo — typical crossover BE study
        data = StudyData(
            dosage_form="tablet_ir",
            is_generic=True,
            is_biological=False,
            is_narrow_therapeutic=False,
            design="crossover_2period",
            n_subjects_enrolled=24,
            n_subjects_in_analysis=22,
            washout_periods=7,
            subject_age_min=18,
            subject_age_max=45,
            bmi_min=19.0,
            bmi_max=28.0,
            subjects_healthy=True,
            fasting_hours_before=8,
            water_ml_with_dose=240,
            food_restriction_hours_after=4,
            standardised_diet=True,
            reference_smpc_fasting="fasting",
            fasted_study_done=True,
            reference_product_defined=True,
            reference_is_originator=True,
            reference_batch_tested=True,
            reference_within_expiry=True,
            test_gmp_confirmed=True,
            sampling_points_n=18,
            sampling_covers_80pct_auc=True,
            terminal_samples_n=4,
            biological_matrix="plasma",
            analyte="parent",
            pk_auc_0t_ratio=103.2,
            pk_cmax_ratio=98.7,
            ci_auc_lower=94.5,
            ci_auc_upper=112.3,
            ci_cmax_lower=88.1,
            ci_cmax_upper=110.4,
            statistical_method="anova_log",
            ci_level_pct=90,
            intrasubject_cv_auc_pct=15.0,
            intrasubject_cv_cmax_pct=18.0,
            ivivc_f2_ph12=62.0,
            ivivc_f2_ph45=58.0,
            ivivc_f2_ph68=55.0,
            bioanalytical_method_validated=True,
            incurred_sample_reanalysis_done=True,
            report_signed_by_investigator=True,
            report_contains_protocol=True,
            report_contains_bioanalytical_report=True,
            individual_pk_curves_provided=True,
            raw_data_available=True,
            outlier_handling_prespecified=True,
            exclusion_criteria_prespecified=True,
        )

    agent = RegulatoryAgent85()
    report = agent.run(data)

    # Pretty print
    s = report["summary"]
    print("=" * 65)
    print("  REGULATORY CHECKLIST — EAEU Decision No. 85")
    print("=" * 65)
    print(f"  VERDICT        : {s['verdict']}")
    print(f"  Total checks   : {s['total_checks']}")
    print(f"  ✅ PASS         : {s['pass']}")
    print(f"  ❌ FAIL         : {s['fail']}")
    print(f"  ⚠️  WARNING      : {s['warning']}")
    print(f"  ➖ N/A          : {s['na']}")
    print(f"  ❓ MISSING DATA : {s['missing_data']}")
    print("=" * 65)
    print()

    icons = {
        "PASS": "✅", "FAIL": "❌", "WARNING": "⚠️ ",
        "NA": "➖", "MISSING_DATA": "❓"
    }
    current_section = None
    for c in report["checks"]:
        if c["section"] != current_section:
            current_section = c["section"]
            print(f"\n── {current_section} ──")
        icon = icons.get(c["status"], "?")
        print(f"  {icon} [{c['id']}] {c['rule']}")
        print(f"       {c['detail']}")
        if c["reference"]:
            print(f"       📎 {c['reference']}")
