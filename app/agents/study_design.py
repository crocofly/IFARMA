"""
agents/study_design.py — Study Design Agent.

КЛЮЧЕВОЙ ПРИНЦИП: выбор дизайна — это ДЕТЕРМИНИРОВАННЫЕ ПРАВИЛА (if/elif),
НЕ LLM. LLM используется только для генерации текстового обоснования.

Правила основаны на:
- Решение ЕАЭС №85 от 03.11.2016
- Дополнение №30 от 12.04.2024
- Встреча с экспертом 16.02.2026

Дерево решений:
1. T½ > 24ч → параллельный дизайн (отмывочный слишком длинный для перекрёстного)
2. NTI → репликативный + ужесточённые границы 90.00-111.11%
3. CVintra ≥ 30% → репликативный 4-периодный (TRTR/RTRT)
4. CVintra < 30% → простой перекрёстный 2×2 (TR/RT)
"""

import math
from typing import Any, Dict

from app.agents.base import BaseAgent, AgentResult
from app.models.design import DesignResult, DesignType, IntakeMode


# ── Константы (из Решения №85 и встречи с экспертом) ──

WASHOUT_MULTIPLIER = 5          # Отмывочный = 5 × T½ (минимум)
WASHOUT_MULTIPLIER_SAFE = 6     # 6 × T½ (с запасом на медленных метаболизаторов)
T_HALF_LONG_THRESHOLD = 24.0    # T½ > 24ч → параллельный дизайн
CV_INTRA_HVD_THRESHOLD = 30.0   # CVintra ≥ 30% → высоковариабельный
MAX_SAMPLING_HOURS = 72          # Обычно не больше 72 часов


class StudyDesignAgent(BaseAgent):
    """
    Study Design Agent — выбирает оптимальный дизайн исследования БЭ.
    
    Работает в 2 этапа:
    1. Python-логика: дерево решений → выбор дизайна, расчёт параметров
    2. LLM: генерация текстового обоснования (для синопсиса)
    """

    async def run(self, input_data: Dict[str, Any]) -> AgentResult:
        # ── Шаг 1: Извлекаем входные данные ──
        # Эти данные приходят из PK Agent через Pipeline
        cv_intra = input_data.get("cv_intra")          # float | None
        t_half = input_data.get("t_half_hours")         # float | None
        tmax = input_data.get("tmax_hours")             # float | None
        is_nti = input_data.get("is_nti", False)        # bool
        is_hvd = input_data.get("is_hvd", False)        # bool
        release_type = input_data.get("release_type", "immediate")  # str
        intake_mode_input = input_data.get("intake_mode")           # str | None
        force_adaptive = input_data.get("force_adaptive", False)    # bool — Pipeline ставит True при n_base > 80

        # ── Шаг 2: Дерево решений — выбираем дизайн ──
        if force_adaptive:
            design = self._select_adaptive_design(cv_intra, t_half, is_nti, is_hvd)
        else:
            design = self._select_design(cv_intra, t_half, is_nti, is_hvd)

        # ── Шаг 3: Рассчитываем отмывочный период ──
        washout_days, washout_formula = self._calculate_washout(t_half, design)

        # ── Шаг 4: Определяем режим приёма ──
        intake_mode = self._determine_intake_mode(intake_mode_input, release_type)

        # ── Шаг 6: Определяем dropout rate ──
        dropout_rate, dropout_justification = self._estimate_dropout(design, washout_days)

        # ── Шаг 7: Определяем границы БЭ ──
        be_lower, be_upper, be_can_expand = self._determine_be_limits(is_nti, is_hvd)

        # ── Шаг 8: Определяем последовательности ──
        n_periods, n_sequences, seq_desc = self._describe_sequences(design)

        # ── Шаг 9: Модифицированное высвобождение ──
        is_modified = release_type in ("modified", "delayed")

        # ── Шаг 10: Определяем точки отбора крови и длительность отбора ──
        # (после шага 8, т.к. нужен n_periods для формулы 450 мл)
        n_blood_points, blood_description, sampling_times, sampling_hours = \
            self._plan_blood_sampling(tmax, t_half, n_periods=n_periods, needs_genetics=False)

        # ── Шаг 11: Генерируем текстовое обоснование через LLM ──
        justification = await self._generate_justification(
            design, cv_intra, t_half, is_nti, is_hvd, is_modified
        )

        # ── Шаг 12: Собираем результат ──
        result = DesignResult(
            design_type=design,
            design_justification=justification,
            n_periods=n_periods,
            n_sequences=n_sequences,
            sequences_description=seq_desc,
            washout_days=washout_days,
            washout_formula=washout_formula,
            intake_mode=intake_mode,
            n_blood_points=n_blood_points,
            blood_points_description=blood_description,
            sampling_duration_hours=sampling_hours,
            sampling_times_hours=sampling_times,
            dropout_rate=dropout_rate,
            dropout_justification=dropout_justification,
            be_lower=be_lower,
            be_upper=be_upper,
            be_can_expand=be_can_expand,
            is_hvd=is_hvd or (cv_intra is not None and cv_intra >= CV_INTRA_HVD_THRESHOLD),
            is_nti=is_nti,
            is_modified_release=is_modified,
        )

        return AgentResult(data=result, sources=["decision_tree", "decision_85"])

    # ════════════════════════════════════════════════════════
    # ДЕРЕВО РЕШЕНИЙ (чистый Python, без LLM)
    # ════════════════════════════════════════════════════════

    def _select_design(
        self,
        cv_intra: float | None,
        t_half: float | None,
        is_nti: bool,
        is_hvd: bool,
    ) -> DesignType:
        """
        Главное дерево решений — выбирает тип дизайна.
        
        Приоритет правил (по Решению №85):
        1. T½ > 24ч → параллельный (отмывочный слишком длинный)
        2. NTI → репликативный (нужна высокая точность)
        3. CVintra ≥ 30% → репликативный 4-периодный
        4. Иначе → простой 2×2 перекрёстный
        """

        # Правило 1: Очень длинный T½ → параллельный
        if t_half is not None and t_half > T_HALF_LONG_THRESHOLD:
            return DesignType.PARALLEL

        # Правило 2: NTI → репликативный (нужны ужесточённые границы)
        if is_nti:
            return DesignType.REPLICATE_4

        # Правило 3: Высоковариабельный → репликативный
        if is_hvd or (cv_intra is not None and cv_intra >= CV_INTRA_HVD_THRESHOLD):
            return DesignType.REPLICATE_4

        # Правило 4: Стандартный случай → 2×2 перекрёстный
        return DesignType.CROSSOVER_2X2

    def _select_adaptive_design(
        self,
        cv_intra: float | None,
        t_half: float | None,
        is_nti: bool,
        is_hvd: bool,
    ) -> DesignType:
        """
        Выбирает адаптивный дизайн, когда n_base > 80 добровольцев.

        Pipeline вызывает этот метод через force_adaptive=True,
        если после первого расчёта выборки n_base превысил 80.

        Правила:
        - T½ > 24ч (исходно параллельный) → адаптивный параллельный
        - Остальные случаи → адаптивный перекрёстный
        """
        if t_half is not None and t_half > T_HALF_LONG_THRESHOLD:
            return DesignType.ADAPTIVE_PARALLEL
        return DesignType.ADAPTIVE_CROSSOVER

    def _calculate_washout(
        self,
        t_half: float | None,
        design: DesignType,
    ) -> tuple[int | None, str]:
        """
        Рассчитывает отмывочный период.
        
        Формула: 5-6 × T½ (с запасом на медленных метаболизаторов).
        Для параллельного дизайна отмывочный период не нужен.
        """
        # Параллельный / адаптивный параллельный → нет отмывочного
        if design in (DesignType.PARALLEL, DesignType.ADAPTIVE_PARALLEL):
            return None, "Параллельный дизайн — отмывочный период не требуется"

        # Нет данных о T½
        if t_half is None:
            return None, "T½ не определён — отмывочный период требует уточнения"

        # Расчёт: берём 5 × T½, округляем вверх до целых дней
        washout_hours = t_half * WASHOUT_MULTIPLIER_SAFE  # 6 × T½ для надёжности
        washout_days = math.ceil(washout_hours / 24)

        # Минимум 7 дней (1 неделя) — для удобства логистики
        washout_days = max(7, washout_days)

        formula = (
            f"{WASHOUT_MULTIPLIER_SAFE} × {t_half:.1f}ч = {washout_hours:.0f}ч "
            f"≈ {washout_days} дней"
        )

        return washout_days, formula

    def _plan_blood_sampling(
        self,
        tmax: float | None,
        t_half: float | None,
        n_periods: int = 2,
        needs_genetics: bool = False,
    ) -> tuple[int, str, list, int]:
        """
        Планирует точки отбора крови.

        1. Из формулы 450 мл → макс. точек/период (max_fk_points)
        2. Ограничиваем ≤ 20 точек/период, ≥ 11 точек/период
        3. Генерируем расписание точек по tmax и t_half
        4. Длительность отбора = min(3×t_half + tmax, 72ч)

        Returns:
            (n_points, description, sampling_times_hours, sampling_duration_hours)
        """
        try:
            from app.utils.blood_sampling import calculate_blood_sampling
        except ImportError:
            try:
                from blood_sampling import calculate_blood_sampling
            except ImportError:
                calculate_blood_sampling = None

        _tmax = tmax or 1.0
        _thalf = t_half or 12.0

        if calculate_blood_sampling:
            result = calculate_blood_sampling(
                n_periods=n_periods,
                t_half_hours=_thalf,
                tmax_hours=_tmax,
                needs_genetics=needs_genetics,
            )
            n_points = result.fk_points_per_period
            sampling_times = result.sampling_times_hours
            sampling_hours = result.sampling_duration_hours
            description = (
                f"{n_points} точек/период (макс. из формулы 450 мл). "
                f"Длительность отбора: {sampling_hours}ч. "
                f"Расписание: {', '.join(f'{t}ч' if t >= 1 else f'{int(t*60)}мин' for t in sampling_times[:5])}..."
            )
            return n_points, description, sampling_times, sampling_hours

        # Fallback: эмпирическая формула (старый алгоритм)
        try:
            from app.utils.study_timeline import max_fk_points
        except ImportError:
            try:
                from study_timeline import max_fk_points
            except ImportError:
                max_fk_points = None

        if max_fk_points:
            n_max = max_fk_points(n_periods, needs_genetics)
            n_points = max(11, min(n_max, 20))
        else:
            n_points = 18

        # Длительность: min(3×t_half + tmax, 72)
        import math
        sampling_after_cmax = min(3 * _thalf, 72)
        sampling_duration = _tmax + sampling_after_cmax
        if sampling_duration <= 24:
            sampling_hours = 24
        elif sampling_duration <= 36:
            sampling_hours = 36
        elif sampling_duration <= 48:
            sampling_hours = 48
        else:
            sampling_hours = 72

        description = (
            f"1 до приёма (нулевая) + "
            f"6 на подъёме кривой + "
            f"1 в пике (Cmax) + "
            f"10 в фазе элиминации. "
            f"Итого: {n_points} точек"
        )

        return n_points, description, [], sampling_hours

    def _determine_intake_mode(
        self,
        user_input: str | None,
        release_type: str,
    ) -> IntakeMode:
        """
        Определяет режим приёма.
        
        Правила:
        - Если пользователь указал → используем его выбор
        - Модифицированное высвобождение → оба (натощак + после еды)
        - По умолчанию → натощак (стандарт для БЭ)
        """
        if user_input:
            try:
                return IntakeMode(user_input)
            except ValueError:
                pass

        # Модифицированное высвобождение → всегда оба варианта
        if release_type in ("modified", "delayed"):
            return IntakeMode.BOTH

        # Стандарт → натощак
        return IntakeMode.FASTING

    def _estimate_dropout(
        self,
        design: DesignType,
        washout_days: int | None,
    ) -> tuple[float, str]:
        """
        Оценивает dropout rate по правилам от эксперта:
        - 2 периода, короткий отмывочный → 10-12%
        - 4 периода → 25%
        - Длинный отмывочный (>14 дней) → ещё выше
        """
        if design == DesignType.PARALLEL:
            return 0.10, "Параллельный дизайн, 1 период — минимальный dropout 10%"

        if design == DesignType.ADAPTIVE_PARALLEL:
            return 0.15, "Адаптивный параллельный дизайн (двухэтапный) — dropout 15%"

        if design == DesignType.ADAPTIVE_CROSSOVER:
            return 0.15, "Адаптивный перекрёстный дизайн (двухэтапный) — dropout 15%"

        if design in (DesignType.REPLICATE_3, DesignType.REPLICATE_4):
            rate = 0.25
            text = "Репликативный дизайн (3-4 периода) — dropout не менее 25%"
            if washout_days and washout_days > 14:
                rate = 0.30
                text += f". Длительный отмывочный ({washout_days} дней) — повышен до 30%"
            return rate, text

        # 2×2 crossover
        if washout_days and washout_days > 14:
            return 0.15, f"2 периода, но длительный отмывочный ({washout_days} дней) — dropout 15%"

        return 0.12, "2 периода, стандартный отмывочный — dropout 10-12%"

    def _determine_be_limits(
        self,
        is_nti: bool,
        is_hvd: bool,
    ) -> tuple[float, float, bool]:
        """
        Определяет границы биоэквивалентности.
        
        Правила (Решение №85):
        - Стандарт: 80.00 — 125.00% при 90% ДИ
        - NTI: 90.00 — 111.11%
        - HVD: стандартные, но МОЖНО расширить для Cmax (по таблице из Решения №85)
        """
        if is_nti:
            return 90.0, 111.11, False

        if is_hvd:
            # Стандартные границы, но с флагом что можно расширить
            return 80.0, 125.0, True

        return 80.0, 125.0, False

    def _describe_sequences(
        self,
        design: DesignType,
    ) -> tuple[int, int, str]:
        """Возвращает количество периодов, последовательностей и их описание."""

        if design == DesignType.CROSSOVER_2X2:
            return 2, 2, "Последовательность 1: T→R. Последовательность 2: R→T"

        if design == DesignType.REPLICATE_3:
            return 3, 3, "TRT / RTR / TRR (3-периодный репликативный)"

        if design == DesignType.REPLICATE_4:
            return 4, 2, "Последовательность 1: T→R→T→R. Последовательность 2: R→T→R→T"

        if design == DesignType.PARALLEL:
            return 1, 2, "Группа 1: T (тест). Группа 2: R (референс)"

        if design == DesignType.ADAPTIVE_CROSSOVER:
            return 2, 2, (
                "Двухэтапный адаптивный перекрёстный дизайн. "
                "Этап 1: пилотная группа (TR/RT). "
                "Этап 2: расширенная группа на основе промежуточного анализа"
            )

        if design == DesignType.ADAPTIVE_PARALLEL:
            return 1, 2, (
                "Двухэтапный адаптивный параллельный дизайн. "
                "Этап 1: пилотная группа (T vs R). "
                "Этап 2: расширенная группа на основе промежуточного анализа"
            )

        return 2, 2, ""

    # ════════════════════════════════════════════════════════
    # ГЕНЕРАЦИЯ ТЕКСТА (LLM — только для обоснования)
    # ════════════════════════════════════════════════════════

    async def _generate_justification(
        self,
        design: DesignType,
        cv_intra: float | None,
        t_half: float | None,
        is_nti: bool,
        is_hvd: bool,
        is_modified: bool,
    ) -> str:
        """
        Генерирует текстовое обоснование выбора дизайна для синопсиса.
        Это единственное место, где используется LLM.
        """
        prompt = f"""
Напиши на русском языке обоснование выбора дизайна исследования биоэквивалентности (2-3 предложения).

Параметры:
- Выбранный дизайн: {design.value}
- CVintra: {cv_intra if cv_intra else 'не определён'}%
- T½: {t_half if t_half else 'не определён'} часов
- Узкий терапевтический индекс: {'да' if is_nti else 'нет'}
- Высоковариабельный: {'да' if is_hvd else 'нет'}
- Модифицированное высвобождение: {'да' if is_modified else 'нет'}

Ссылайся на Решение ЕАЭС №85. Пиши кратко, формально, как в протоколе клинического исследования.
"""
        try:
            return await self.llm.generate(prompt)
        except Exception:
            # Fallback если LLM недоступна — формируем текст шаблоном
            return (
                f"Выбран дизайн {design.value} на основании "
                f"CVintra {'≥ 30%' if is_hvd else '< 30%'} "
                f"и T½ {'> 24ч' if (t_half and t_half > 24) else '≤ 24ч'} "
                f"в соответствии с Решением ЕАЭС №85."
            )
