"""
agents/protocol_validator.py — Validation Agent.

Проверяет данные из найденного протокола БЭ на соответствие:
- Решению ЕАЭС №85
- ФК-параметрам препарата (CVintra, T½, HVD/NTI)
- Инструкции по применению (режим приёма)

Логика:
- Если всё ОК → ACCEPT (используем дизайн из протокола)
- Если мелкие расхождения → ACCEPT_WITH_CORRECTIONS (используем, но правим)
- Если критические ошибки → REJECT (рассчитываем сами)
"""

from typing import Any, Dict, List
from dataclasses import dataclass, field
from enum import Enum


class ValidationVerdict(str, Enum):
    ACCEPT = "accept"                           # Всё корректно
    ACCEPT_WITH_CORRECTIONS = "accept_corrected"  # Есть мелкие расхождения
    REJECT = "reject"                           # Критические ошибки


@dataclass
class ValidationIssue:
    field: str          # Какое поле
    severity: str       # "critical" | "warning" | "info"
    message: str        # Описание проблемы
    correction: str = ""  # Рекомендуемая коррекция


@dataclass
class ValidationResult:
    verdict: ValidationVerdict
    issues: List[ValidationIssue] = field(default_factory=list)
    corrected_data: Dict[str, Any] = field(default_factory=dict)

    @property
    def n_critical(self) -> int:
        return sum(1 for i in self.issues if i.severity == "critical")

    @property
    def n_warnings(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    def summary(self) -> str:
        return (
            f"Verdict: {self.verdict.value} | "
            f"Critical: {self.n_critical}, Warnings: {self.n_warnings}, "
            f"Info: {sum(1 for i in self.issues if i.severity == 'info')}"
        )


# ── Константы из Решения 85 ──
MIN_SUBJECTS = 12
CV_HVD_THRESHOLD = 30.0
T_HALF_PARALLEL_THRESHOLD = 24.0
WASHOUT_MULTIPLIER_MIN = 5
BE_LOWER_STANDARD = 80.0
BE_UPPER_STANDARD = 125.0
BE_LOWER_NTI = 90.0
BE_UPPER_NTI = 111.11


class ProtocolValidator:
    """
    Валидатор существующих протоколов БЭ.

    Проверяет данные из ClinicalTrials.gov/PubMed
    на соответствие Решению 85 и ФК-параметрам.
    """

    def validate(
        self,
        protocol: Dict[str, Any],
        pk_data: Dict[str, Any],
        intake_mode_from_instruction: str = "",
    ) -> ValidationResult:
        """
        Проверяет протокол.

        Args:
            protocol: данные из protocol_search
                - design_type: str
                - n_periods: int
                - n_subjects: int
                - cv_intra: float
                - intake_mode: str
            pk_data: данные из PK Agent
                - cv_intra_max: float
                - t_half_hours: float
                - is_hvd: bool
                - is_nti: bool
            intake_mode_from_instruction: режим из инструкции ("fasting"/"fed"/"both")

        Returns:
            ValidationResult
        """
        issues = []
        corrected = {}

        # Извлекаем данные
        proto_design = protocol.get("design_type")
        proto_periods = protocol.get("n_periods")
        proto_n = protocol.get("n_subjects")
        proto_cv = protocol.get("cv_intra")
        proto_intake = protocol.get("intake_mode")

        pk_cv = pk_data.get("cv_intra_max")
        pk_t_half = pk_data.get("t_half_hours")
        pk_is_hvd = pk_data.get("is_hvd", False)
        pk_is_nti = pk_data.get("is_nti", False)

        # Лучшая оценка CVintra (из PK или из протокола)
        cv_best = pk_cv or proto_cv

        # ═══════════════════════════════════════
        # ПРОВЕРКА 1: Дизайн соответствует CVintra
        # ═══════════════════════════════════════
        if proto_design and cv_best:
            is_hvd = pk_is_hvd or (cv_best >= CV_HVD_THRESHOLD)

            if is_hvd and proto_design == "2x2_crossover":
                issues.append(ValidationIssue(
                    field="design_type",
                    severity="critical",
                    message=(
                        f"CVintra={cv_best:.1f}% ≥ 30% → препарат высоковариабельный, "
                        f"но протокол использует стандартный 2×2 дизайн. "
                        f"Требуется репликативный дизайн (Решение 85, п.85-86)."
                    ),
                    correction="replicate_4_period",
                ))
                corrected["design_type"] = "replicate_4_period"
                corrected["n_periods"] = 4

            elif not is_hvd and proto_design in ("replicate_4_period", "replicate_3_period"):
                # Не критично — репликативный допустим и для обычных
                issues.append(ValidationIssue(
                    field="design_type",
                    severity="info",
                    message=(
                        f"CVintra={cv_best:.1f}% < 30% — препарат не высоковариабельный. "
                        f"Репликативный дизайн допустим, но стандартный 2×2 достаточен."
                    ),
                ))

        # ═══════════════════════════════════════
        # ПРОВЕРКА 2: Параллельный дизайн
        # ═══════════════════════════════════════
        if proto_design == "parallel" and pk_t_half and pk_t_half <= T_HALF_PARALLEL_THRESHOLD:
            issues.append(ValidationIssue(
                field="design_type",
                severity="warning",
                message=(
                    f"T½={pk_t_half:.1f}ч ≤ 24ч — параллельный дизайн не обязателен. "
                    f"Перекрёстный более мощный (меньше добровольцев)."
                ),
                correction="2x2_crossover",
            ))

        if proto_design != "parallel" and pk_t_half and pk_t_half > T_HALF_PARALLEL_THRESHOLD:
            issues.append(ValidationIssue(
                field="design_type",
                severity="critical",
                message=(
                    f"T½={pk_t_half:.1f}ч > 24ч — требуется параллельный дизайн "
                    f"(Решение 85, п.16). Перекрёстный неприменим."
                ),
                correction="parallel",
            ))
            corrected["design_type"] = "parallel"
            corrected["n_periods"] = 1

        # ═══════════════════════════════════════
        # ПРОВЕРКА 3: Размер выборки
        # ═══════════════════════════════════════
        if proto_n is not None:
            if proto_n < MIN_SUBJECTS:
                issues.append(ValidationIssue(
                    field="n_subjects",
                    severity="critical",
                    message=(
                        f"Размер выборки N={proto_n} < {MIN_SUBJECTS} "
                        f"(минимум по Решению 85, п.26)."
                    ),
                    correction=f"n_subjects >= {MIN_SUBJECTS}",
                ))
            elif proto_n < 18:
                issues.append(ValidationIssue(
                    field="n_subjects",
                    severity="warning",
                    message=(
                        f"Размер выборки N={proto_n} — маловато. "
                        f"Рекомендуется ≥18 для надёжной мощности."
                    ),
                ))

        # ═══════════════════════════════════════
        # ПРОВЕРКА 4: Режим приёма
        # ═══════════════════════════════════════
        if proto_intake and intake_mode_from_instruction:
            if proto_intake != intake_mode_from_instruction:
                # Режим из инструкции приоритетнее
                if intake_mode_from_instruction == "fed" and proto_intake == "fasting":
                    issues.append(ValidationIssue(
                        field="intake_mode",
                        severity="warning",
                        message=(
                            f"Протокол указывает '{proto_intake}', "
                            f"но инструкция по применению требует прием с пищей."
                        ),
                        correction=intake_mode_from_instruction,
                    ))
                    corrected["intake_mode"] = intake_mode_from_instruction
                elif intake_mode_from_instruction == "fasting" and proto_intake == "fed":
                    issues.append(ValidationIssue(
                        field="intake_mode",
                        severity="info",
                        message=(
                            f"Протокол указывает '{proto_intake}', "
                            f"инструкция допускает приём натощак."
                        ),
                    ))

        # ═══════════════════════════════════════
        # ПРОВЕРКА 5: NTI — границы
        # ═══════════════════════════════════════
        if pk_is_nti:
            issues.append(ValidationIssue(
                field="be_limits",
                severity="info",
                message=(
                    "Препарат с узким терапевтическим диапазоном (NTI). "
                    "Границы БЭ: 90.00–111.11% (п.84 Решения 85)."
                ),
            ))

        # ═══════════════════════════════════════
        # ВЕРДИКТ
        # ═══════════════════════════════════════
        n_critical = sum(1 for i in issues if i.severity == "critical")

        if n_critical == 0:
            if corrected:
                verdict = ValidationVerdict.ACCEPT_WITH_CORRECTIONS
            else:
                verdict = ValidationVerdict.ACCEPT
        else:
            verdict = ValidationVerdict.REJECT

        return ValidationResult(
            verdict=verdict,
            issues=issues,
            corrected_data=corrected,
        )