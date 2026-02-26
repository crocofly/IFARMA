"""
agents/blood_sampling.py — Расчёт точек забора крови на ФК.

Алгоритм:
1. Из формулы 450 мл = лаб + ФК + заполнение [+ генетика]
   → вычисляем максимальное кол-во точек ФК на 1 период.
2. Ограничиваем ≤ 20 точек/период.
3. Генерируем расписание точек по tmax и t_half:
   - 1 точка до приёма (0 мин, преддозовая)
   - 3 точки до ожидаемого tmax
   - 3 точки после tmax
   - 3-4 точки терминальной фазы (до min(3×t_half, 72ч) после Cmax)
   - Заполняем оставшиеся точки равномерно

Источники:
- Забор_крови.docx (формулы объёма крови)
- Решение ЕАЭС №85 п.38 (схема отбора образцов)
- ГОСТ Р 57679-2017 (общие требования)
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ═══════════════════════════════════════════════════════════
# КОНСТАНТЫ
# ═══════════════════════════════════════════════════════════

MAX_BLOOD_PER_SUBJECT_ML = 450.0   # Максимум крови за исследование
FK_SAMPLE_ML = 5.0                 # мл крови на 1 точку ФК
FLUSH_ML = 0.5                     # мл на заполнение системы (catheter)
BHAK_SAMPLE_ML = 10.0              # Биохимический анализ крови
KAK_SAMPLE_ML = 4.0                # Клинический (общий) анализ крови
SEROLOGY_ML = 10.0                 # Серология (ВИЧ, гепатит B/C, сифилис)
GENETICS_ML = 10.0                 # Генотипирование (если нужно)
MAX_POINTS_PER_PERIOD = 20         # Верхняя граница точек ФК на 1 период
MIN_POINTS_PER_PERIOD = 11         # Минимум для надёжного описания ФК кривой
MAX_SAMPLING_HOURS = 72            # Максимум отбора проб (п.38 Решения №85)
MIN_SAMPLING_T_HALF = 3            # Минимум 3 периода полувыведения после Cmax


# ═══════════════════════════════════════════════════════════
# РЕЗУЛЬТАТ
# ═══════════════════════════════════════════════════════════

@dataclass
class BloodSamplingResult:
    """Результат расчёта схемы забора крови."""

    # Расчёт из формулы крови
    n_periods: int                          # Кол-во ФК периодов
    fk_points_per_period: int               # Точек ФК на 1 период
    fk_total_points: int                    # Всего точек ФК (все периоды)
    needs_genetics: bool                    # Нужен генетический скрининг

    # Объёмы
    fk_volume_ml: float                     # Объём крови на ФК
    flush_volume_ml: float                  # Заполнение системы
    lab_volume_ml: float                    # Лабораторные анализы (БХАК+КАК+серология)
    genetics_volume_ml: float               # Генетика (0 если не нужна)
    total_volume_ml: float                  # Итого на 1 добровольца

    # Формулы для текста
    lab_formula: str                        # "(2+4)×10 + (2+4)×4 + 10 = 94 мл"
    total_formula: str                      # "94 + 320 + 31.5 + 0 = 445.5 мл"

    # Расписание точек
    sampling_times_hours: List[float]       # Часы: [0, 0.25, 0.5, 0.75, 1, ...]
    sampling_times_text: str                # "за 30 мин до приема и через 15, 30, ..."
    sampling_duration_hours: int            # Длительность отбора (часов)

    # Для docx
    n_lab_visits: int                       # Кол-во визитов с лабораторией (2+n_periods)
    biosamples_total: int                   # Всего биообразцов в лабораторию


# ═══════════════════════════════════════════════════════════
# ОСНОВНАЯ ФУНКЦИЯ
# ═══════════════════════════════════════════════════════════

def calculate_blood_sampling(
    n_periods: int,
    t_half_hours: float,
    tmax_hours: float = 1.0,
    n_subjects: int = 24,
    fk_sample_ml: float = FK_SAMPLE_ML,
    needs_genetics: bool = False,
    max_blood_ml: float = MAX_BLOOD_PER_SUBJECT_ML,
) -> BloodSamplingResult:
    """
    Рассчитывает схему забора крови на ФК.

    Args:
        n_periods: Количество ФК периодов (1-4)
        t_half_hours: Период полувыведения (часов)
        tmax_hours: Время достижения Cmax (часов)
        n_subjects: Число добровольцев (без screenfail/dropout)
        fk_sample_ml: мл крови на 1 точку ФК (обычно 5)
        needs_genetics: Нужен ли генотипирование/фенотипирование
        max_blood_ml: Максимум крови (450 мл)

    Returns:
        BloodSamplingResult
    """

    # ── 1. Лабораторные анализы ──
    # Формула из Забор_крови.docx:
    # (2 + n_periods) × 10 + (2 + n_periods) × 4 + 10 [+ 10 если генетика]
    # Где:
    #   (2+n_periods) = кол-во визитов с лаб. анализами
    #     (скрининг + накануне 1-го дозирования + через 24ч в каждом ФК периоде + наблюдение)
    #   ×10 = БХАК, ×4 = КАК, +10 = серология (однократно)
    n_lab_visits = 2 + n_periods
    bhak_total = n_lab_visits * BHAK_SAMPLE_ML
    kak_total = n_lab_visits * KAK_SAMPLE_ML
    serology_total = SEROLOGY_ML
    genetics_total = GENETICS_ML if needs_genetics else 0.0
    lab_volume = bhak_total + kak_total + serology_total + genetics_total

    lab_formula_parts = [
        f"({n_lab_visits})×{BHAK_SAMPLE_ML:.0f}",
        f"({n_lab_visits})×{KAK_SAMPLE_ML:.0f}",
        f"{SEROLOGY_ML:.0f}",
    ]
    if needs_genetics:
        lab_formula_parts.append(f"{GENETICS_ML:.0f}")
    lab_formula = " + ".join(lab_formula_parts) + f" = {lab_volume:.0f} мл"

    # ── 2. Максимальное кол-во точек ФК ──
    # max_blood = lab + fk_points×n_periods×fk_sample + (fk_points×n_periods - n_periods)×0.5
    # 450 = lab + fk_pts × n_per × 5 + (fk_pts × n_per - n_per) × 0.5
    # 450 = lab + fk_pts × n_per × 5 + fk_pts × n_per × 0.5 - n_per × 0.5
    # 450 - lab + n_per×0.5 = fk_pts × n_per × (5 + 0.5)
    # fk_pts = (450 - lab + n_per×0.5) / (n_per × 5.5)
    available_for_fk = max_blood_ml - lab_volume + n_periods * FLUSH_ML
    fk_per_period_max = available_for_fk / (n_periods * (fk_sample_ml + FLUSH_ML))
    fk_per_period_max = math.floor(fk_per_period_max)  # Округляем вниз

    # Ограничения
    fk_per_period = min(fk_per_period_max, MAX_POINTS_PER_PERIOD)
    fk_per_period = max(fk_per_period, MIN_POINTS_PER_PERIOD)

    # ── 3. Объёмы с выбранным кол-вом точек ──
    fk_total_points = fk_per_period * n_periods
    fk_volume = fk_total_points * fk_sample_ml
    # Заполнение системы: 0.5 мл × (всего точек - n_periods)
    # (первая точка в каждом периоде не требует заполнения — катетер только установлен)
    flush_count = fk_total_points - n_periods
    flush_volume = flush_count * FLUSH_ML

    total_volume = lab_volume + fk_volume + flush_volume

    total_formula = (
        f"{lab_volume:.0f} + {fk_volume:.0f} + {flush_volume:.1f}"
        f"{f' + {genetics_total:.0f}' if needs_genetics else ''}"
        f" = {total_volume:.1f} мл"
    )

    # ── 4. Длительность отбора проб ──
    # Минимум 3 × t_half после Cmax, но не более 72ч
    sampling_after_cmax = min(MIN_SAMPLING_T_HALF * t_half_hours, MAX_SAMPLING_HOURS)
    sampling_duration = tmax_hours + sampling_after_cmax
    # Округляем до стандартных: 24, 36, 48, 72
    if sampling_duration <= 24:
        sampling_duration_hours = 24
    elif sampling_duration <= 36:
        sampling_duration_hours = 36
    elif sampling_duration <= 48:
        sampling_duration_hours = 48
    else:
        sampling_duration_hours = 72

    # ── 5. Расписание точек ──
    sampling_times = _generate_sampling_schedule(
        n_points=fk_per_period,
        tmax_hours=tmax_hours,
        t_half_hours=t_half_hours,
        max_hours=sampling_duration_hours,
    )

    sampling_text = _format_sampling_times(sampling_times)

    # ── 6. Биообразцы ──
    biosamples_total = fk_per_period * n_periods * n_subjects

    return BloodSamplingResult(
        n_periods=n_periods,
        fk_points_per_period=fk_per_period,
        fk_total_points=fk_total_points,
        needs_genetics=needs_genetics,
        fk_volume_ml=fk_volume,
        flush_volume_ml=flush_volume,
        lab_volume_ml=lab_volume,
        genetics_volume_ml=genetics_total,
        total_volume_ml=total_volume,
        lab_formula=lab_formula,
        total_formula=total_formula,
        sampling_times_hours=sampling_times,
        sampling_times_text=sampling_text,
        sampling_duration_hours=sampling_duration_hours,
        n_lab_visits=n_lab_visits,
        biosamples_total=biosamples_total,
    )


# ═══════════════════════════════════════════════════════════
# ГЕНЕРАЦИЯ РАСПИСАНИЯ ТОЧЕК
# ═══════════════════════════════════════════════════════════

def _generate_sampling_schedule(
    n_points: int,
    tmax_hours: float,
    t_half_hours: float,
    max_hours: float = 72.0,
) -> List[float]:
    """
    Генерирует расписание точек забора крови.

    Правила (из Забор_крови.docx + Решение №85 п.38):
    1. Точка 0 — преддозовая (0ч = до приёма)
    2. 3 точки до tmax (≠ 0), с учащением к tmax
    3. Точка tmax
    4. 3 точки после tmax
    5. 3-4 точки терминальной фазы элиминации
    6. Последняя точка ≈ min(3×t_half, 72ч)
    7. Остальные точки — равномерно между фазами

    Стандартные временные точки (округляются до ближайших):
    0, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4, 5, 6, 8, 10, 12, 16, 24, 36, 48, 72
    """

    # Стандартная сетка возможных точек
    standard_grid = [
        0, 0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10, 12,
        16, 20, 24, 30, 36, 48, 60, 72,
    ]
    # Фильтруем по max_hours
    grid = [t for t in standard_grid if t <= max_hours]

    # Обязательные точки
    must_have = set()

    # 0 — преддозовая
    must_have.add(0)

    # Ближайшие к tmax из сетки
    tmax_snap = _snap_to_grid(tmax_hours, grid)
    must_have.add(tmax_snap)

    # 3 точки до tmax (исключая 0)
    before_tmax = [t for t in grid if 0 < t < tmax_snap]
    # Берём 3 ближайших к tmax (плотно)
    if len(before_tmax) >= 3:
        before_selected = before_tmax[-3:]
    else:
        before_selected = before_tmax
    must_have.update(before_selected)

    # 3 точки после tmax
    after_tmax = [t for t in grid if t > tmax_snap]
    if len(after_tmax) >= 3:
        after_selected = after_tmax[:3]
    else:
        after_selected = after_tmax
    must_have.update(after_selected)

    # Терминальная фаза: последняя точка
    last_time = min(3 * t_half_hours, max_hours)
    last_snap = _snap_to_grid(last_time, grid)
    if last_snap <= tmax_snap:
        last_snap = grid[-1] if grid else max_hours
    must_have.add(last_snap)

    # Конечная точка sampling_duration (если отличается от last_snap)
    endpoint_snap = _snap_to_grid(max_hours, grid)
    if endpoint_snap > last_snap:
        must_have.add(endpoint_snap)

    # 3-4 точки в терминальной фазе (между последней after_tmax и last_snap)
    terminal_start = max(after_selected) if after_selected else tmax_snap
    terminal_candidates = [t for t in grid if terminal_start < t <= last_snap]
    # Равномерно выбираем 3-4
    if len(terminal_candidates) > 4:
        step = len(terminal_candidates) / 4
        terminal_selected = [terminal_candidates[int(i * step)] for i in range(4)]
        if last_snap not in terminal_selected:
            terminal_selected[-1] = last_snap
    else:
        terminal_selected = terminal_candidates
    must_have.update(terminal_selected)

    # Собираем и сортируем
    selected = sorted(must_have)

    # Если точек меньше n_points — добавляем из оставшихся
    remaining = [t for t in grid if t not in selected]
    while len(selected) < n_points and remaining:
        # Добавляем точки равномерно: ищем наибольший gap
        best_gap = 0
        best_insert = None
        for i in range(len(selected) - 1):
            gap = selected[i + 1] - selected[i]
            if gap > best_gap:
                # Ищем точку из remaining в этом gap
                candidates = [t for t in remaining if selected[i] < t < selected[i + 1]]
                if candidates:
                    # Берём среднюю
                    mid = (selected[i] + selected[i + 1]) / 2
                    best_candidate = min(candidates, key=lambda x: abs(x - mid))
                    best_gap = gap
                    best_insert = best_candidate
        if best_insert is not None:
            selected.append(best_insert)
            selected.sort()
            remaining.remove(best_insert)
        else:
            break

    # Если точек больше n_points — обрезаем менее важные
    while len(selected) > n_points:
        # Не убираем: 0, tmax_snap, last_snap, before_selected, after_selected
        protected = {0, tmax_snap, last_snap}
        protected.update(before_selected[:2])  # Минимум 2 до tmax
        protected.update(after_selected[:2])   # Минимум 2 после tmax

        removable = [t for t in selected if t not in protected]
        if not removable:
            break
        # Убираем точку с наименьшим вкладом (минимальный gap между соседями)
        min_impact = float('inf')
        worst = None
        for t in removable:
            idx = selected.index(t)
            if 0 < idx < len(selected) - 1:
                impact = selected[idx + 1] - selected[idx - 1]
                if impact < min_impact:
                    min_impact = impact
                    worst = t
        if worst is not None:
            selected.remove(worst)
        else:
            break

    return selected


def _snap_to_grid(value: float, grid: List[float]) -> float:
    """Ближайшее значение из сетки."""
    if not grid:
        return value
    return min(grid, key=lambda x: abs(x - value))


def _format_sampling_times(times: List[float]) -> str:
    """
    Форматирует расписание в текст для синопсиса.

    Формат: "за 30 мин до приема исследуемого препарата/референтного
    препарата и через 15, 30, 45 минут, 1, 1.5, 2, 3, 4, 6, 8, 10,
    12, 16, 24 часов после приема препарата."
    """
    if not times:
        return ""

    # Разделяем: преддозовая (0) и постдозовые
    pre_dose = [t for t in times if t == 0]
    post_dose = [t for t in times if t > 0]

    # Преддозовая
    pre_text = "за 30 мин до приема исследуемого препарата/референтного препарата"

    # Постдозовые
    post_parts = []
    minutes_part = []
    hours_part = []

    for t in post_dose:
        if t < 1:
            # Минуты
            mins = int(t * 60)
            minutes_part.append(str(mins))
        else:
            # Часы
            if t == int(t):
                hours_part.append(str(int(t)))
            else:
                hours_part.append(str(t))

    post_items = []
    if minutes_part:
        post_items.append(", ".join(minutes_part) + " минут")
    if hours_part:
        post_items.append(", ".join(hours_part) + " часов")

    post_text = ", ".join(post_items) + " после приема препарата"

    return f"{pre_text} и через {post_text}"


# ═══════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЕ
# ═══════════════════════════════════════════════════════════

def max_fk_points_per_period(
    n_periods: int,
    needs_genetics: bool = False,
    fk_sample_ml: float = FK_SAMPLE_ML,
    max_blood_ml: float = MAX_BLOOD_PER_SUBJECT_ML,
) -> int:
    """Вычисляет максимально допустимое кол-во точек ФК на 1 период."""
    n_lab = 2 + n_periods
    lab_vol = n_lab * BHAK_SAMPLE_ML + n_lab * KAK_SAMPLE_ML + SEROLOGY_ML
    if needs_genetics:
        lab_vol += GENETICS_ML
    available = max_blood_ml - lab_vol + n_periods * FLUSH_ML
    pts = available / (n_periods * (fk_sample_ml + FLUSH_ML))
    return min(math.floor(pts), MAX_POINTS_PER_PERIOD)


def result_to_dict(r: BloodSamplingResult) -> dict:
    """Конвертирует результат в dict для передачи в docx_exporter."""
    return {
        "n_blood_points": r.fk_points_per_period,
        "fk_total_points": r.fk_total_points,
        "fk_volume_ml": r.fk_volume_ml,
        "flush_volume_ml": r.flush_volume_ml,
        "lab_volume_ml": r.lab_volume_ml,
        "total_blood_volume_ml": r.total_volume_ml,
        "lab_formula": r.lab_formula,
        "total_formula": r.total_formula,
        "sampling_times_hours": r.sampling_times_hours,
        "sampling_times_text": r.sampling_times_text,
        "sampling_duration_hours": r.sampling_duration_hours,
        "n_lab_visits": r.n_lab_visits,
        "biosamples_total": r.biosamples_total,
        "needs_genetics": r.needs_genetics,
    }