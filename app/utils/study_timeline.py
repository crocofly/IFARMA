"""
utils/study_timeline.py — Вычислитель временной структуры исследования.

Чистая арифметика, без LLM. Берёт выход Design Agent + Sample Size Agent
и раскладывает на конкретные дни, визиты, объёмы крови.

Используется для заполнения Row 11 «Методология исследования» в синопсисе.

Источники формул:
- Забор_крови.docx — формулы объёма крови
- шаблон_для_заполнения.docx — структура визитов
- Решение ЕАЭС №85, п.38 — длительность отбора проб
- входящие_параметры_1.docx — описание полей
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


# ── Константы ──

SCREENING_DAYS_DEFAULT = 14       # Скрининг — стандарт 14 дней
FOLLOW_UP_DAYS_DEFAULT = 7        # Последующее наблюдение — 7 дней
BLOOD_PER_SAMPLE_ML = 5.0         # 5 мл крови на 1 ФК-пробу
BLOOD_FLUSH_ML = 0.5              # 0.5 мл на заполнение системы (кроме первой в периоде)
BLOOD_KAK_ML = 10.0               # Клинический анализ крови — 10 мл за 1 раз
BLOOD_BHAK_ML = 4.0               # Биохимический анализ — 4 мл за 1 раз
BLOOD_SEROLOGY_ML = 10.0          # Серологический анализ — 10 мл (однократно, скрининг)
BLOOD_GENETICS_ML = 10.0          # Генетический скрининг — 10 мл (если нужен)
MAX_BLOOD_PER_SUBJECT_ML = 450.0  # Максимум крови за всё исследование (донорский лимит)
MAX_BLOOD_POINTS_PER_PERIOD = 20  # Не более 20 точек ФК на 1 период
FASTING_HOURS = 8                 # Минимум голодания до приёма
WATER_ML = 200                    # Объём воды при приёме


@dataclass
class Visit:
    """Один визит в исследовании."""
    number: int               # Номер визита (1, 2, 3...)
    name: str                 # "Скрининг", "Период 1 ФК", "Отмывочный", "Наблюдение"
    day_start: int            # День начала (сквозная нумерация)
    day_end: int              # День окончания
    description: str = ""     # Описание визита


@dataclass
class PeriodFK:
    """Один период ФК исследования."""
    number: int               # 1, 2, 3, 4
    visit_number: int         # Номер визита
    hospitalization_day: int  # День госпитализации (вечер)
    dosing_day: int           # День приёма препарата
    sampling_start_day: int   # День начала отбора крови
    sampling_end_day: int     # День окончания отбора
    discharge_day: int        # День выписки


@dataclass
class BloodVolume:
    """Расчёт объёма крови."""
    # ФК
    fk_points_per_period: int    # Точек ФК за 1 период
    fk_total_points: int         # Всего точек ФК (все периоды)
    fk_volume_ml: float          # Объём крови на ФК
    flush_volume_ml: float       # Заполнение системы
    fk_total_ml: float           # ФК + заполнение

    # Лабораторные анализы
    n_lab_visits: int             # Кол-во визитов с лабораторией
    kak_total_ml: float           # Клинический анализ крови
    bhak_total_ml: float          # Биохимический анализ
    serology_ml: float            # Серология (однократно)
    genetics_ml: float            # Генетика (если есть)
    lab_total_ml: float           # Итого лабораторные

    # Биообразцы
    biosamples_total: int         # Всего биообразцов в лабораторию
    biosamples_formula: str       # "18 точек × 4 периода × 38 добровольцев"

    # Итого
    total_per_subject_ml: float   # Итого на 1 добровольца
    total_ok: bool                # Не превышает 450 мл
    total_formula: str            # Разбивка формулы


@dataclass
class StudyTimeline:
    """Полная временная структура исследования."""

    # Параметры
    n_periods: int
    washout_days: int
    screening_days: int
    follow_up_days: int
    sampling_hours: int
    fk_period_days: int           # Длительность 1 периода ФК (дней госпитализации)

    # Визиты
    visits: List[Visit] = field(default_factory=list)

    # Периоды ФК
    fk_periods: List[PeriodFK] = field(default_factory=list)

    # Дни приёма препарата (сквозная нумерация)
    dosing_days: List[int] = field(default_factory=list)

    # Объём крови
    blood: Optional[BloodVolume] = None

    # Общая длительность
    total_days_min: int = 0       # Минимум (скрининг 1 день)
    total_days_max: int = 0       # Максимум (скрининг 14 дней)

    # Текстовые описания для шаблона
    periods_word: str = ""        # "двух периодах" / "четырёх периодах"
    groups_description: str = ""  # "Группа 1 (n=19): T-R / Группа 2 (n=19): R-T"


def calculate_timeline(
    n_periods: int,
    washout_days: int,
    sampling_hours: int,
    n_blood_points: int,
    n_total: int,
    n_sequences: int = 2,
    sequences_description: str = "",
    screening_days: int = SCREENING_DAYS_DEFAULT,
    follow_up_days: int = FOLLOW_UP_DAYS_DEFAULT,
    needs_genetics: bool = False,
) -> StudyTimeline:
    """
    Рассчитывает полную временную структуру исследования.

    Args:
        n_periods: Количество периодов ФК (2, 3, 4)
        washout_days: Отмывочный период (дней)
        sampling_hours: Длительность отбора проб (часов)
        n_blood_points: Точек отбора крови за 1 период
        n_total: Общее число добровольцев (с dropout + screenfail)
        n_sequences: Кол-во последовательностей (2, 3, 4)
        sequences_description: "TR/RT", "TRTR/RTRT" и т.д.
        screening_days: Длительность скрининга (дней)
        follow_up_days: Наблюдение после последнего приёма (дней)
        needs_genetics: Нужен ли генетический скрининг

    Returns:
        StudyTimeline с полной разбивкой
    """

    # ── Длительность 1 периода ФК (дней госпитализации) ──
    # Госпитализация вечером → отбор проб sampling_hours часов → выписка
    # Пример: sampling=24ч → госп. вечером День 0, приём утром День 1,
    #         отбор 24ч = до Дня 2, выписка День 2 = 3 дня (0,1,2)
    # Пример: sampling=48ч → госп. День 0, приём День 1,
    #         отбор 48ч = до Дня 3, выписка День 3 = 4 дня
    # Количество календарных дней отбора проб (включая день приёма):
    # 24ч = День 1 (приём+отбор) + День 2 (отбор до утра) = 2 дня
    # 48ч = 3 дня, 72ч = 4 дня
    sampling_calendar_days = math.ceil(sampling_hours / 24) + 1 if sampling_hours > 0 else 1
    fk_period_days = sampling_calendar_days  # госпитализация = отбор

    # Ограничиваем точки ФК — не больше чем влезает в 450 мл
    fk_points_max = max_fk_points(n_periods, needs_genetics)
    fk_points = min(n_blood_points, MAX_BLOOD_POINTS_PER_PERIOD, fk_points_max)
    if fk_points < n_blood_points:
        print(f"  ⚠️  Точки ФК снижены: {n_blood_points} → {fk_points}/период "
              f"(лимит крови {MAX_BLOOD_PER_SUBJECT_ML:.0f} мл)")

    # ── Визиты и сквозная нумерация дней ──
    visits = []
    fk_periods = []
    dosing_days = []
    visit_num = 1

    # Визит 1: Скрининг (День -14 .. День -1)
    visits.append(Visit(
        number=visit_num,
        name="Скрининг",
        day_start=-screening_days,
        day_end=-1,
        description=f"Визит {visit_num}. (День -{screening_days} – День -1).",
    ))
    visit_num += 1

    # Периоды ФК
    current_day = 0  # День 0 = первая госпитализация

    for period_idx in range(n_periods):
        period_num = period_idx + 1

        hosp_day = current_day          # Госпитализация вечером
        dose_day = current_day + 1      # Приём утром следующего дня
        sampling_start = dose_day       # Отбор начинается в день приёма
        sampling_end = dose_day + sampling_calendar_days - 1
        discharge_day = sampling_end    # Выписка в последний день отбора

        fk_periods.append(PeriodFK(
            number=period_num,
            visit_number=visit_num,
            hospitalization_day=hosp_day,
            dosing_day=dose_day,
            sampling_start_day=sampling_start,
            sampling_end_day=sampling_end,
            discharge_day=discharge_day,
        ))
        dosing_days.append(dose_day)

        visits.append(Visit(
            number=visit_num,
            name=f"Период {period_num} ФК исследования",
            day_start=hosp_day,
            day_end=discharge_day,
            description=(
                f"Визит {visit_num}. День {hosp_day} – День {discharge_day} "
                f"(госпитализация)"
            ),
        ))
        visit_num += 1

        # Отмывочный период (кроме последнего)
        if period_idx < n_periods - 1:
            washout_start = dose_day + 1
            # Отмывочный = от приёма до приёма (washout_days дней)
            # Следующий приём = dose_day + washout_days
            # Следующая госпитализация = накануне = dose_day + washout_days - 1
            next_hosp = dose_day + washout_days - 1
            current_day = next_hosp
        else:
            # После последнего периода — наблюдение
            last_dose_day = dose_day

    # Визит последующего наблюдения
    followup_day = last_dose_day + follow_up_days
    visits.append(Visit(
        number=visit_num,
        name="Период последующего наблюдения",
        day_start=followup_day,
        day_end=followup_day,
        description=(
            f"Визит {visit_num}. День {followup_day} "
            f"(окно визита +2 дня)"
        ),
    ))

    # ── Общая длительность ──
    total_days_max = screening_days + followup_day  # от начала скрининга
    total_days_min = 1 + followup_day               # скрининг за 1 день

    # ── Объём крови ──
    blood = _calculate_blood_volume(
        fk_points_per_period=fk_points,
        n_periods=n_periods,
        n_total=n_total,
        needs_genetics=needs_genetics,
    )

    # ── Текстовые формы ──
    periods_words = {
        2: "двух периодах",
        3: "трёх периодах",
        4: "четырёх периодах",
    }
    periods_word = periods_words.get(n_periods, f"{n_periods} периодах")

    # Группы
    n_per_group = n_total // n_sequences
    if sequences_description:
        seqs = sequences_description.split("/")
        groups_lines = []
        for i, seq in enumerate(seqs):
            groups_lines.append(
                f"Группа {i+1} (n={n_per_group}): "
                f"получает препараты в последовательности {seq}"
            )
        groups_description = "; ".join(groups_lines)
    else:
        groups_description = (
            f"Группа 1 (n={n_per_group}): T→R; "
            f"Группа 2 (n={n_per_group}): R→T"
        )

    return StudyTimeline(
        n_periods=n_periods,
        washout_days=washout_days,
        screening_days=screening_days,
        follow_up_days=follow_up_days,
        sampling_hours=sampling_hours,
        fk_period_days=fk_period_days,
        visits=visits,
        fk_periods=fk_periods,
        dosing_days=dosing_days,
        blood=blood,
        total_days_min=total_days_min,
        total_days_max=total_days_max,
        periods_word=periods_word,
        groups_description=groups_description,
    )


def _calculate_blood_volume(
    fk_points_per_period: int,
    n_periods: int,
    n_total: int,
    needs_genetics: bool = False,
) -> BloodVolume:
    """
    Рассчитывает объём крови по формулам из Забор_крови.docx.

    Большая формула:
        (2 + n_periods) × 10  — КАК (клинический анализ)
      + (2 + n_periods) × 4   — БАК (биохимический)
      + 10                    — серология (однократно)
      + fk_total × 5          — ФК-пробы
      + (fk_total - n_periods) × 0.5  — заполнение системы
      + 10 (если генетика)
      ≤ 450 мл

    Визиты с лабораторией: скрининг + накануне каждого периода +
    последнее наблюдение = 2 + n_periods
    """
    fk_total_points = fk_points_per_period * n_periods

    # ФК
    fk_volume = fk_total_points * BLOOD_PER_SAMPLE_ML
    # Заполнение системы: 0.5 мл на каждую пробу кроме первой в каждом периоде
    flush_points = fk_total_points - n_periods
    flush_volume = max(0, flush_points) * BLOOD_FLUSH_ML
    fk_total = fk_volume + flush_volume

    # Лабораторные визиты: скрининг(1) + накануне каждого периода(n_periods) + наблюдение(1)
    n_lab_visits = 2 + n_periods

    # КАК — 10 мл × визитов
    kak_total = n_lab_visits * BLOOD_KAK_ML

    # БАК — 4 мл × визитов
    bhak_total = n_lab_visits * BLOOD_BHAK_ML

    # Серология — 10 мл однократно (скрининг)
    serology = BLOOD_SEROLOGY_ML

    # Генетика
    genetics = BLOOD_GENETICS_ML if needs_genetics else 0.0

    lab_total = kak_total + bhak_total + serology + genetics

    # Итого
    total = fk_total + lab_total
    total_ok = total <= MAX_BLOOD_PER_SUBJECT_ML

    # Биообразцы в лабораторию
    # n_base = n_total без screenfail — но мы считаем по n_total
    # (медик говорит: "без скринфейлеров, дропаутов, дублеров")
    # Для синопсиса используем n_total (завершившие), но это упрощение
    biosamples = fk_points_per_period * n_periods * n_total
    biosamples_formula = (
        f"{fk_points_per_period} точек × {n_periods} "
        f"{'периода' if n_periods < 5 else 'периодов'} × "
        f"{n_total} добровольцев"
    )

    # Формула итого
    parts = [
        f"ФК: {fk_volume:.0f} мл ({fk_total_points} проб × {BLOOD_PER_SAMPLE_ML:.0f} мл)",
        f"Заполнение: {flush_volume:.1f} мл ({flush_points} × {BLOOD_FLUSH_ML} мл)",
        f"КАК: {kak_total:.0f} мл ({n_lab_visits} × {BLOOD_KAK_ML:.0f} мл)",
        f"БАК: {bhak_total:.0f} мл ({n_lab_visits} × {BLOOD_BHAK_ML:.0f} мл)",
        f"Серология: {serology:.0f} мл",
    ]
    if needs_genetics:
        parts.append(f"Генетика: {genetics:.0f} мл")
    parts.append(f"ИТОГО: {total:.1f} мл {'✅' if total_ok else '❌ ПРЕВЫШЕНИЕ!'}")
    total_formula = "\n".join(parts)

    return BloodVolume(
        fk_points_per_period=fk_points_per_period,
        fk_total_points=fk_total_points,
        fk_volume_ml=fk_volume,
        flush_volume_ml=flush_volume,
        fk_total_ml=fk_total,
        n_lab_visits=n_lab_visits,
        kak_total_ml=kak_total,
        bhak_total_ml=bhak_total,
        serology_ml=serology,
        genetics_ml=genetics,
        lab_total_ml=lab_total,
        biosamples_total=biosamples,
        biosamples_formula=biosamples_formula,
        total_per_subject_ml=total,
        total_ok=total_ok,
        total_formula=total_formula,
    )


def max_fk_points(
    n_periods: int,
    needs_genetics: bool = False,
    max_blood_ml: float = MAX_BLOOD_PER_SUBJECT_ML,
) -> int:
    """
    Вычисляет максимальное кол-во точек ФК за 1 период,
    чтобы не превысить лимит крови.

    Из большой формулы (Забор_крови.docx):
        (2+P)×10 + (2+P)×4 + 10 + N×P×5 + (N×P - P)×0.5 + [10] = max_blood_ml

        Где N = fk_points_per_period, P = n_periods

        Раскрываем:
        lab = (2+P)*14 + 10 + (10 if genetics else 0)
        fk = N*P*5 + (N*P - P)*0.5 = N*P*5.5 - P*0.5

        max_blood = lab + fk
        fk_budget = max_blood - lab
        N*P*5.5 - P*0.5 = fk_budget
        N = (fk_budget + P*0.5) / (P * 5.5)
    """
    lab = (2 + n_periods) * 14 + 10
    if needs_genetics:
        lab += 10

    fk_budget = max_blood_ml - lab
    if fk_budget <= 0:
        return 0

    n_max = (fk_budget + n_periods * 0.5) / (n_periods * 5.5)
    n_max = int(n_max)  # Округление вниз

    # Не более 20 на период
    n_max = min(n_max, MAX_BLOOD_POINTS_PER_PERIOD)

    return n_max


def timeline_to_dict(tl: StudyTimeline) -> Dict[str, Any]:
    """Конвертирует StudyTimeline в dict для подстановки в шаблон."""
    b = tl.blood

    d = {
        # Длительности
        "screening_days": tl.screening_days,
        "fk_period_days": tl.fk_period_days,
        "washout_days": tl.washout_days,
        "follow_up_days": tl.follow_up_days,
        "total_days_min": tl.total_days_min,
        "total_days_max": tl.total_days_max,
        "n_periods": tl.n_periods,
        "sampling_hours": tl.sampling_hours,

        # Дни приёма
        "dosing_days": tl.dosing_days,
        "dosing_days_str": ", ".join(f"День {d}" for d in tl.dosing_days),

        # Визиты
        "n_visits": len(tl.visits),
        "visits": [
            {
                "number": v.number,
                "name": v.name,
                "day_start": v.day_start,
                "day_end": v.day_end,
                "description": v.description,
            }
            for v in tl.visits
        ],

        # Периоды ФК
        "fk_periods": [
            {
                "number": p.number,
                "visit_number": p.visit_number,
                "hospitalization_day": p.hospitalization_day,
                "dosing_day": p.dosing_day,
                "sampling_start_day": p.sampling_start_day,
                "sampling_end_day": p.sampling_end_day,
                "discharge_day": p.discharge_day,
            }
            for p in tl.fk_periods
        ],

        # Текст
        "periods_word": tl.periods_word,
        "groups_description": tl.groups_description,
        "fasting_hours": FASTING_HOURS,
        "water_ml": WATER_ML,
    }

    # Кровь
    if b:
        d.update({
            "fk_points_per_period": b.fk_points_per_period,
            "fk_total_points": b.fk_total_points,
            "fk_volume_ml": b.fk_volume_ml,
            "flush_volume_ml": b.flush_volume_ml,
            "fk_total_ml": b.fk_total_ml,
            "lab_total_ml": b.lab_total_ml,
            "kak_total_ml": b.kak_total_ml,
            "bhak_total_ml": b.bhak_total_ml,
            "serology_ml": b.serology_ml,
            "genetics_ml": b.genetics_ml,
            "biosamples_total": b.biosamples_total,
            "biosamples_formula": b.biosamples_formula,
            "total_blood_per_subject_ml": b.total_per_subject_ml,
            "total_blood_ok": b.total_ok,
            "total_blood_formula": b.total_formula,
        })

    return d