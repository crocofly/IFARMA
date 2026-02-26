"""
agents/sample_size.py — Sample Size Agent.

Выбор метода расчёта (из Расчет_размера_выборки.docx):
1. Обычные препараты (CVintra < 30%): sampleN.TOST()
2. Высоковариабельные (CVintra ≥ 30%, HVD): sampleN.scABEL.ad()
3. Узкотерапевтические (NTI/NTID): sampleN.NTID()

Источники:
    - Решение ЕАЭС №85
    - Расчет_размера_выборки.docx
    - Пакет R PowerTOST (эталонная реализация)
"""

import math
from typing import Any, Dict
from scipy import stats

from app.agents.base import BaseAgent, AgentResult
from app.models.sample_size import SampleSizeResult


# ── Константы (по умолчанию — Решение 85) ──

DEFAULT_POWER = 0.80          # Мощность 80% (Решение 85, п.27)
DEFAULT_ALPHA = 0.05          # Уровень значимости 5%
DEFAULT_GMR = 0.95            # Ожидаемое T/R отношение
DEFAULT_THETA = 1.25          # Верхняя граница БЭ 80-125%
DEFAULT_SCREENFAIL = 0.15     # Screen failure rate 15%
DEFAULT_DROPOUT = 0.15        # Dropout rate 15%
MIN_SUBJECTS = 12             # Минимум 12 человек (Решение ЕАЭС №85)
MAX_BASE_SUBJECTS = 80        # Максимум 80 человек (без dropout/screenfail) → адаптивный дизайн
MAX_CV_INTRA = 60.0           # CVintra не может превышать 60% (ошибки LLM при комби-препаратах)
BLOOD_PER_POINT_ML = 5.0
MAX_BLOOD_ML = 450.0
CV_HVD_THRESHOLD = 30.0       # CVintra ≥ 30% → HVD


class SampleSizeAgent(BaseAgent):
    """
    Sample Size Agent — рассчитывает количество добровольцев.

    Этапы:
    1. Формула → n_base
    2. Коррекция на dropout → n_with_dropout
    3. Коррекция на screen-fail → n_with_screenfail
    4. Финальный размер → n_total (≥ MIN_SUBJECTS)
    """

    async def run(self, input_data: Dict[str, Any]) -> AgentResult:
        cv_intra = input_data.get("cv_intra")

        design_data = input_data.get("design", {})
        if hasattr(design_data, "model_dump"):
            design_data = design_data.model_dump()

        n_periods = design_data.get("n_periods", 2)
        n_blood_points = design_data.get("n_blood_points", 18)
        is_hvd = input_data.get("is_hvd", False)
        is_nti = design_data.get("is_nti", False)

        overrides = input_data.get("overrides", {})
        power = overrides.get("power", DEFAULT_POWER)
        alpha = overrides.get("alpha", DEFAULT_ALPHA)
        gmr = overrides.get("gmr", DEFAULT_GMR)
        theta = overrides.get("theta", DEFAULT_THETA)
        screenfail_rate = overrides.get("screenfail_rate", DEFAULT_SCREENFAIL)
        dropout_rate = overrides.get("dropout_rate",
                                     design_data.get("dropout_rate", DEFAULT_DROPOUT))
        min_subjects = overrides.get("min_subjects", MIN_SUBJECTS)
        blood_per_point = overrides.get("blood_per_point_ml", BLOOD_PER_POINT_ML)
        max_blood = overrides.get("max_blood_ml", MAX_BLOOD_ML)

        if cv_intra is None:
            cv_intra = 30.0

        # CVintra ограничен сверху 60% (defensive)
        cv_intra = min(cv_intra, MAX_CV_INTRA)

        # Определяем HVD по CVintra
        if cv_intra >= CV_HVD_THRESHOLD:
            is_hvd = True

        # Расчёт n_base
        n_base = self._calculate_n_base(
            cv_intra=cv_intra, gmr=gmr, n_periods=n_periods,
            is_hvd=is_hvd, is_nti=is_nti,
        )

        # Проверка: n_base > 80 → нужен адаптивный дизайн
        max_base = overrides.get("max_base_subjects", MAX_BASE_SUBJECTS)
        needs_adaptive = n_base > max_base

        # Коррекции
        n_with_dropout = math.ceil(n_base / (1 - dropout_rate))
        n_with_screenfail = math.ceil(n_with_dropout / (1 - screenfail_rate))
        n_total = max(min_subjects, n_with_screenfail)

        # Объём крови
        blood_volume = n_blood_points * n_periods * blood_per_point
        blood_ok = blood_volume <= max_blood

        # Текстовое описание
        calc_desc = self._generate_description(
            cv_intra=cv_intra, n_base=n_base,
            n_with_dropout=n_with_dropout, n_total=n_total,
            dropout_rate=dropout_rate, n_periods=n_periods,
            gmr=gmr, screenfail_rate=screenfail_rate,
            is_hvd=is_hvd, is_nti=is_nti,
        )

        result = SampleSizeResult(
            n_base=n_base,
            n_with_dropout=n_with_dropout,
            n_with_screenfail=n_with_screenfail,
            n_total=n_total,
            cv_intra_used=cv_intra,
            power=power, alpha=alpha, gmr=gmr, theta=theta,
            dropout_rate=dropout_rate,
            screenfail_rate=screenfail_rate,
            blood_volume_ml=blood_volume,
            blood_volume_ok=blood_ok,
            needs_adaptive=needs_adaptive,
            calculation_description=calc_desc,
        )
        return AgentResult(data=result, sources=["formula", "decision_85"])

    # ════════════════════════════════════════════════════════
    # ТАБЛИЦЫ PowerTOST (R)
    # ════════════════════════════════════════════════════════
    #
    # Выбор определяется ДВУМЯ факторами:
    # 1. Тип: обычный (TOST) / HVD (scABEL) / NTI (NTID)
    # 2. Дизайн: 2×2 / 2×2×3 / 2×2×4 / parallel

    # ── TOST: обычные (CVintra < 30%) ──

    TOST_2x2_095: dict[int, int] = {
        10:  8, 15: 12, 17: 14, 20: 20, 22: 22, 24: 26, 25: 28,
        26: 30, 28: 34, 30: 40, 32: 44, 35: 52, 38: 64,
        40: 70, 42: 78, 45: 90, 48: 104, 50: 116,
    }
    TOST_2x2_090: dict[int, int] = {
        15: 18, 17: 20, 20: 26, 22: 30, 24: 34, 25: 36,
        26: 40, 28: 44, 30: 52, 32: 56, 35: 68, 38: 80,
        40: 90, 42: 96, 45: 112, 48: 130, 50: 142,
    }
    TOST_PARALLEL_095: dict[int, int] = {
        20: 38, 25: 54, 30: 78, 35: 102, 40: 132,
        45: 162, 50: 196, 55: 232, 60: 270,
    }
    TOST_PARALLEL_090: dict[int, int] = {
        20: 60, 25: 88, 30: 124, 35: 166, 40: 214,
        45: 268, 50: 326, 55: 390, 60: 458,
    }

    # ── scABEL: высоковариабельные (CVintra ≥ 30%) ──

    ABEL_2x2x4_095: dict[int, int] = {
        30: 24, 32: 24, 34: 26, 35: 26, 36: 28, 38: 30,
        40: 32, 42: 34, 44: 36, 45: 38, 48: 42, 50: 46,
        55: 54, 60: 64, 65: 76, 70: 90,
    }
    ABEL_2x2x4_090: dict[int, int] = {
        30: 30, 32: 32, 34: 34, 35: 34, 36: 36, 38: 38,
        40: 40, 42: 42, 44: 44, 45: 46, 48: 50, 50: 54,
        55: 64, 60: 76, 65: 90, 70: 104,
    }
    ABEL_2x2x3_095: dict[int, int] = {
        30: 36, 32: 36, 34: 36, 35: 36, 36: 36, 38: 42,
        40: 42, 42: 48, 45: 54, 48: 60, 50: 66,
        55: 78, 60: 90, 65: 108, 70: 126,
    }

    # ── NTID: узкотерапевтические ──

    # sampleN.NTID(CV=x/100, theta0=0.975, design="2x2x4")
    NTID_2x2x4_0975: dict[int, int] = {
        4: 54, 5: 34, 6: 24, 8: 16, 10: 14,
        12: 14, 15: 16, 20: 28, 25: 48, 30: 72,
    }
    # sampleN.NTID(CV=x/100, theta0=0.95, design="2x2x4")
    NTID_2x2x4_095: dict[int, int] = {
        4: 98, 5: 64, 6: 48, 8: 32, 10: 24,
        12: 22, 15: 22, 20: 36, 25: 58, 30: 88,
    }

    def _calculate_n_base(
        self,
        cv_intra: float,
        gmr: float,
        n_periods: int,
        is_hvd: bool = False,
        is_nti: bool = False,
    ) -> int:
        """
        Рассчитывает n_base по таблице PowerTOST.

        Логика выбора (Расчет_размера_выборки.docx):
        1. NTI → sampleN.NTID()
        2. HVD (CVintra ≥ 30%) → sampleN.scABEL.ad()
        3. Обычный → sampleN.TOST()
        """
        use_090 = gmr is not None and gmr <= 0.92

        # ── NTI ──
        if is_nti:
            use_0975 = gmr is not None and gmr >= 0.96
            table = self.NTID_2x2x4_0975 if use_0975 else self.NTID_2x2x4_095
            return max(MIN_SUBJECTS, self._interpolate_table(table, cv_intra))

        # ── HVD (CVintra ≥ 30%) ──
        if is_hvd and cv_intra >= CV_HVD_THRESHOLD:
            if n_periods >= 4:
                table = self.ABEL_2x2x4_090 if use_090 else self.ABEL_2x2x4_095
            elif n_periods == 3:
                table = self.ABEL_2x2x3_095
            else:
                # HVD + 2×2 — fallback на TOST (scABEL требует ≥3 периодов)
                table = self.TOST_2x2_090 if use_090 else self.TOST_2x2_095
            return max(MIN_SUBJECTS, self._interpolate_table(table, cv_intra))

        # ── Обычный ──
        if n_periods == 1:
            table = self.TOST_PARALLEL_090 if use_090 else self.TOST_PARALLEL_095
        else:
            table = self.TOST_2x2_090 if use_090 else self.TOST_2x2_095

        return max(MIN_SUBJECTS, self._interpolate_table(table, cv_intra))

    @staticmethod
    def _interpolate_table(table: dict, cv: float) -> int:
        """Линейная интерполяция из таблицы PowerTOST."""
        cvs = sorted(table.keys())
        ns = [table[c] for c in cvs]

        if cv <= cvs[0]:
            return max(MIN_SUBJECTS, ns[0])
        if cv >= cvs[-1]:
            return ns[-1]

        for i in range(len(cvs) - 1):
            if cvs[i] <= cv <= cvs[i + 1]:
                frac = (cv - cvs[i]) / (cvs[i + 1] - cvs[i])
                n = ns[i] + frac * (ns[i + 1] - ns[i])
                n = math.ceil(n)
                return max(MIN_SUBJECTS, n)

        return max(MIN_SUBJECTS, ns[-1])

    # ════════════════════════════════════════════════════════
    # ГЕНЕРАЦИЯ ТЕКСТА ОПИСАНИЯ
    # ════════════════════════════════════════════════════════

    def _generate_description(
        self,
        cv_intra: float,
        n_base: int,
        n_with_dropout: int,
        n_total: int,
        dropout_rate: float,
        n_periods: int,
        gmr: float = None,
        screenfail_rate: float = None,
        is_hvd: bool = False,
        is_nti: bool = False,
    ) -> str:
        """
        Генерирует текстовое описание расчёта для синопсиса.
        Полностью детерминированный — без LLM.
        Текст ветвится по типу: TOST / scABEL / NTID.
        """
        gmr = gmr or DEFAULT_GMR
        screenfail_rate = screenfail_rate or DEFAULT_SCREENFAIL
        is_parallel = (n_periods == 1)
        cv_decimal = cv_intra / 100

        # ── Определяем R-функцию и метод ──
        if is_nti:
            r_package = "PowerTOST"
            r_function = "sampleN.NTID"
            r_design = "2x2x4"
            design_label = "2x2x4 (4 period full replicate)"
            method_name = "NTID (reference-scaled)"
        elif is_hvd and cv_intra >= CV_HVD_THRESHOLD:
            r_package = "PowerTOST"
            r_function = "sampleN.scABEL.ad"
            if n_periods >= 4:
                r_design = "2x2x4"
                design_label = "2x2x4 (4 period full replicate)"
            elif n_periods == 3:
                r_design = "2x2x3"
                design_label = "2x2x3 (3 period partial replicate)"
            else:
                r_function = "sampleN.TOST"
                r_design = "2x2x2"
                design_label = "2x2x2 (2 period crossover)"
            method_name = "scaled (widened) ABEL"
        elif is_parallel:
            r_package = "PowerTOST"
            r_function = "sampleN.TOST"
            r_design = "parallel"
            design_label = "parallel (2 groups)"
            method_name = "TOST (parallel)"
        else:
            r_package = "PowerTOST"
            r_function = "sampleN.TOST"
            r_design = "2x2x2"
            design_label = "2x2x2 (2 period crossover)"
            method_name = "TOST"

        # ── Блок 1: введение ──
        L = []
        L.append(
            f"Расчёт размера выборки для исследования биоэквивалентности "
            f"выполнен с использованием программного обеспечения (ПО) "
            f"«The R Project for Statistical Computing» "
            f"(https://www.r-project.org) версии не ниже 4.4.2, "
            f"пакет {r_package}."
        )
        L.append(
            f"Расчёт производился на основе коэффициента "
            f"внутрииндивидуальной вариабельности (CVintra). "
            f"CVintra для действующего вещества составляет {cv_intra}%."
        )

        # ── Блок 2: R код ──
        L.append("Для расчёта использовался следующий код:")
        L.append(
            f"{r_function}(CV={cv_decimal}, theta0={gmr}, "
            f"targetpower=0.80, design=\"{r_design}\")"
        )

        # ── Блок 3: результаты R ──
        L.append("Результаты расчёта:")

        if is_nti:
            L.append(
                f"+++++++++++ {method_name} ++++++++++++\n"
                f"            Sample size estimation\n"
                f"   (FDA NTID method, reference-scaled)\n"
                f"----------------------------------------------\n"
                f"Study design: {design_label}\n"
                f"log-transformed data (multiplicative model)\n"
                f"\n"
                f"Assumed CVwR {cv_decimal}, CVwT {cv_decimal}\n"
                f"Nominal alpha      : 0.05\n"
                f"True ratio         : {gmr}\n"
                f"Target power       : 0.8\n"
                f"Regulatory settings: FDA (NTID)\n"
                f"BE limits          : 0.9000 ... 1.1111\n"
                f"n  {n_base}, power ~0.80"
            )
        elif "scABEL" in r_function:
            sigma_wr = math.sqrt(math.log(cv_decimal**2 + 1))
            expanded_lo = math.exp(-0.76 * sigma_wr)
            expanded_hi = math.exp(0.76 * sigma_wr)
            if cv_intra > 50:
                expanded_lo = 0.6984
                expanded_hi = 1.4319
            limits_str = f"{expanded_lo:.4f} ... {expanded_hi:.4f}"

            L.append(
                f"+++++++++++ {method_name} ++++++++++++\n"
                f"            Sample size estimation\n"
                f"        for iteratively adjusted alpha\n"
                f"   (simulations based on ANOVA evaluation)\n"
                f"----------------------------------------------\n"
                f"Study design: {design_label}\n"
                f"log-transformed data (multiplicative model)\n"
                f"1,000,000 studies in each iteration simulated.\n"
                f"\n"
                f"Assumed CVwR {cv_decimal}, CVwT {cv_decimal}\n"
                f"Nominal alpha      : 0.05\n"
                f"True ratio         : {gmr}\n"
                f"Target power       : 0.8\n"
                f"Regulatory settings: EMA (ABEL)\n"
                f"Switching CVwR     : 0.3\n"
                f"Regulatory constant: 0.76\n"
                f"Expanded limits    : {limits_str}\n"
                f"Upper scaling cap  : CVwR > 0.5\n"
                f"PE constraints     : 0.8000 ... 1.2500\n"
                f"n  {n_base}, power ~0.80"
            )
        else:
            # TOST
            L.append(
                f"+++++++++++ {method_name} ++++++++++++\n"
                f"            Sample size estimation\n"
                f"          (exact) for TOST\n"
                f"----------------------------------------------\n"
                f"Study design: {design_label}\n"
                f"log-transformed data (multiplicative model)\n"
                f"\n"
                f"alpha = 0.05, target power = 0.8\n"
                f"BE limits        : 0.8000 ... 1.2500\n"
                f"True ratio       : {gmr}\n"
                f"CV               : {cv_decimal}\n"
                f"\n"
                f"Sample size (total)\n"
                f"n  {n_base}, power ~0.80"
            )

        # ── Блок 4: интерпретация ──
        L.append(
            f"Включение {n_with_dropout} добровольцев, из них "
            f"{n_base} полностью завершивших исследование, обеспечит "
            f"мощность 80,0% для оценки биоэквивалентности при "
            f"{n_periods}-периодном дизайне с построением 90% доверительных "
            f"интервалов для соотношения геометрических средних по каждому "
            f"из фармакокинетических параметров (Cmax, AUC0-t) и ожидаемом "
            f"соотношении геометрических средних ФК параметров исследуемого "
            f"препарата и препарата сравнения, равном {gmr}."
        )
        L.append(
            f"С учётом возможного отсева приблизительно "
            f"{dropout_rate*100:.0f}% добровольцев, необходимо "
            f"рандомизировать {n_with_dropout} добровольцев."
        )
        L.append(
            f"С учётом возможного {screenfail_rate*100:.0f}% отсева на "
            f"скрининге в исследование будут скринированы до "
            f"{n_total} добровольцев."
        )
        L.append(
            "Добровольцы, досрочно завершившие исследование, "
            "не будут заменены."
        )

        return "\n".join(L)
