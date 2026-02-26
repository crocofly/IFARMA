"""
services/pk/pk_curve.py — Генератор теоретической PK-кривой.

Строит кривую «концентрация — время» по однокомпартментной модели
с абсорбцией первого порядка (Bateman function):

    C(t) = (F × D × ka) / (Vd × (ka − kel)) × (e^(−kel×t) − e^(−ka×t))

где:
    ka  — константа абсорбции (рассчитывается из tmax и kel)
    kel — константа элиминации = ln(2) / T½
    F   — биодоступность (нормализуется для Cmax)
    D   — доза
    Vd  — объём распределения (нормализуется для Cmax)

Упрощение: нормализуем кривую так, чтобы максимум = Cmax (литературное).
Это позволяет строить кривую БЕЗ знания F, D, Vd.

Использование:
    curve = generate_pk_curve(cmax=292, tmax=0.48, t_half=0.51)
    curve.save_plot("pk_curve.png")
    auc = curve.auc_0t
"""

import math
import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np


@dataclass
class PKCurveResult:
    """Результат генерации PK-кривой."""
    # Массивы данных
    time_points: List[float] = field(default_factory=list)
    concentrations: List[float] = field(default_factory=list)

    # PK параметры (из кривой)
    cmax: float = 0.0          # нг/мл
    tmax: float = 0.0          # ч
    t_half: float = 0.0        # ч
    kel: float = 0.0           # 1/ч
    ka: float = 0.0            # 1/ч
    auc_0t: float = 0.0        # нг·ч/мл (метод трапеций)
    auc_0inf: float = 0.0      # нг·ч/мл (экстраполированная)
    auc_residual_pct: float = 0.0  # % остаточной AUC

    # Точки отбора крови (предложенные)
    sampling_times: List[float] = field(default_factory=list)
    sampling_description: str = ""

    # Путь к графику
    plot_path: Optional[str] = None

    def save_plot(
        self,
        filepath: str,
        title: str = "",
        inn: str = "",
        dose: str = "",
        show_sampling: bool = True,
        show_auc: bool = True,
        lang: str = "ru",
    ) -> str:
        """
        Сохраняет график PK-кривой в PNG.

        Args:
            filepath: путь к файлу .png
            title: заголовок графика
            inn: МНН для подписи
            dose: доза для подписи
            show_sampling: показать точки отбора крови
            show_auc: заштриховать AUC
            lang: 'ru' или 'en'

        Returns:
            filepath
        """
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.ticker import MaxNLocator

        fig, ax = plt.subplots(1, 1, figsize=(10, 6), dpi=150)

        t = np.array(self.time_points)
        c = np.array(self.concentrations)

        # AUC заливка
        if show_auc:
            ax.fill_between(t, 0, c, alpha=0.15, color="#2196F3",
                            label=f"AUC₀₋ₜ = {self.auc_0t:.1f} нг·ч/мл")

        # Основная кривая
        ax.plot(t, c, color="#1565C0", linewidth=2.0, label="C(t) — теоретический профиль")

        # Cmax / tmax
        ax.axhline(y=self.cmax, color="#E53935", linestyle="--", linewidth=0.8, alpha=0.6)
        ax.axvline(x=self.tmax, color="#E53935", linestyle="--", linewidth=0.8, alpha=0.6)
        ax.plot(self.tmax, self.cmax, "o", color="#E53935", markersize=8, zorder=5)
        ax.annotate(
            f"Cmax = {self.cmax:.0f} нг/мл\ntmax = {self.tmax:.2f} ч",
            xy=(self.tmax, self.cmax),
            xytext=(self.tmax + (t[-1] - t[0]) * 0.08, self.cmax * 0.90),
            fontsize=9,
            arrowprops=dict(arrowstyle="->", color="#E53935", lw=1.2),
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="#E53935", alpha=0.9),
        )

        # T½ отметка
        c_half = self.cmax / 2
        # Найдём время, когда C = Cmax/2 (на фазе элиминации)
        elim_idx = np.argmax(c)
        elim_t = t[elim_idx:]
        elim_c = c[elim_idx:]
        t_half_mark = None
        for i in range(len(elim_c) - 1):
            if elim_c[i] >= c_half >= elim_c[i + 1]:
                # Линейная интерполяция
                frac = (c_half - elim_c[i + 1]) / (elim_c[i] - elim_c[i + 1])
                t_half_mark = elim_t[i + 1] - frac * (elim_t[i + 1] - elim_t[i])
                break

        if t_half_mark is not None:
            ax.axhline(y=c_half, color="#FF9800", linestyle=":", linewidth=0.8, alpha=0.5)
            ax.annotate(
                f"T½ = {self.t_half:.2f} ч",
                xy=(t_half_mark, c_half),
                xytext=(t_half_mark + (t[-1] - t[0]) * 0.05, c_half * 1.15),
                fontsize=8, color="#FF9800",
            )

        # Точки отбора крови
        if show_sampling and self.sampling_times:
            for st in self.sampling_times:
                idx = np.argmin(np.abs(t - st))
                ax.plot(st, c[idx], "v", color="#4CAF50", markersize=6, zorder=4)
            # Легенда для sampling
            ax.plot([], [], "v", color="#4CAF50", markersize=6,
                    label=f"Точки отбора крови (n={len(self.sampling_times)})")

        # Подписи
        if lang == "ru":
            xlabel = "Время после приёма (ч)"
            ylabel = "Концентрация (нг/мл)"
        else:
            xlabel = "Time post-dose (h)"
            ylabel = "Concentration (ng/mL)"

        ax.set_xlabel(xlabel, fontsize=11)
        ax.set_ylabel(ylabel, fontsize=11)

        if not title:
            title = f"Теоретический фармакокинетический профиль"
            if inn:
                title += f"\n{inn}"
            if dose:
                title += f", {dose}"

        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.set_xlim(left=0)
        ax.set_ylim(bottom=0)
        ax.legend(loc="upper right", fontsize=9)
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_locator(MaxNLocator(integer=False, nbins=12))

        # Параметры в текстовом блоке
        param_text = (
            f"kel = {self.kel:.4f} ч⁻¹\n"
            f"ka = {self.ka:.4f} ч⁻¹\n"
            f"AUC₀₋ₜ = {self.auc_0t:.1f} нг·ч/мл\n"
            f"AUC₀₋∞ = {self.auc_0inf:.1f} нг·ч/мл\n"
            f"Остаточная AUC = {self.auc_residual_pct:.1f}%"
        )
        ax.text(
            0.98, 0.55, param_text,
            transform=ax.transAxes, fontsize=8,
            verticalalignment="top", horizontalalignment="right",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="lightyellow",
                      edgecolor="gray", alpha=0.9),
        )

        plt.tight_layout()
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        fig.savefig(filepath, dpi=150, bbox_inches="tight")
        plt.close(fig)

        self.plot_path = filepath
        return filepath


def generate_pk_curve(
    cmax: float,
    tmax: float,
    t_half: float,
    cmax_unit: str = "нг/мл",
    duration_hours: float = 0,
    n_points: int = 500,
    blood_sampling_points: Optional[List[float]] = None,
) -> PKCurveResult:
    """
    Генерирует теоретическую PK-кривую.

    Модель: однокомпартментная с абсорбцией первого порядка (Bateman).

    Args:
        cmax: максимальная концентрация (нг/мл)
        tmax: время достижения Cmax (ч)
        t_half: период полувыведения (ч)
        duration_hours: длительность графика (0 = авто: 5×T½ или 72ч)
        n_points: количество точек кривой
        blood_sampling_points: заданные точки отбора крови (ч)

    Returns:
        PKCurveResult с данными и вычисленными параметрами
    """
    # ── Константа элиминации ──
    kel = math.log(2) / t_half  # kel = ln(2) / T½

    # ── Константа абсорбции ──
    # Из условия dC/dt = 0 при t = tmax:
    #   ka = kel × e^(kel×tmax) / (e^(kel×tmax) − 1)  — приблизительно
    # Или точнее через Lambert W: tmax = ln(ka/kel) / (ka - kel)
    # Используем итеративный метод
    ka = _estimate_ka(kel, tmax)

    # ── Длительность графика ──
    if duration_hours <= 0:
        # Авто: max(5×T½, 3×tmax, 4ч), но не более 72ч
        duration_hours = max(5 * t_half, 3 * tmax, 4.0)
        duration_hours = min(duration_hours, 72.0)

    # ── Генерируем кривую ──
    t = np.linspace(0, duration_hours, n_points)

    # Bateman function (ненормализованная)
    if abs(ka - kel) < 1e-10:
        # Вырожденный случай ka ≈ kel
        c_raw = t * np.exp(-kel * t)
    else:
        c_raw = (ka / (ka - kel)) * (np.exp(-kel * t) - np.exp(-ka * t))

    # Нормализуем чтобы max = Cmax
    c_max_raw = np.max(c_raw)
    if c_max_raw > 0:
        c = c_raw * (cmax / c_max_raw)
    else:
        c = c_raw

    # Убираем отрицательные значения (численные артефакты)
    c = np.maximum(c, 0)

    # ── AUC методом трапеций ──
    # Совместимость: numpy >= 2.0 → trapezoid, старые → trapz
    _trapz = getattr(np, "trapezoid", None) or getattr(np, "trapz")
    auc_0t = float(_trapz(c, t))

    # ── AUC₀₋∞ (экстраполяция) ──
    c_last = float(c[-1])
    if c_last > 0 and kel > 0:
        auc_extra = c_last / kel
        auc_0inf = auc_0t + auc_extra
        auc_residual_pct = (auc_extra / auc_0inf) * 100
    else:
        auc_0inf = auc_0t
        auc_residual_pct = 0.0

    # ── Точки отбора крови ──
    if blood_sampling_points is None:
        sampling_times = _suggest_sampling_times(tmax, t_half, duration_hours)
    else:
        sampling_times = blood_sampling_points

    sampling_desc = _describe_sampling(sampling_times, tmax)

    return PKCurveResult(
        time_points=t.tolist(),
        concentrations=c.tolist(),
        cmax=cmax,
        tmax=tmax,
        t_half=t_half,
        kel=kel,
        ka=ka,
        auc_0t=round(auc_0t, 2),
        auc_0inf=round(auc_0inf, 2),
        auc_residual_pct=round(auc_residual_pct, 1),
        sampling_times=sampling_times,
        sampling_description=sampling_desc,
    )


def _estimate_ka(kel: float, tmax: float) -> float:
    """
    Оценивает константу абсорбции (ka) по kel и tmax.

    Из Bateman: tmax = ln(ka/kel) / (ka − kel)
    Решаем итеративно.
    """
    if tmax <= 0:
        return kel * 5  # fallback

    # Начальное приближение: ka ≈ 2-10 × kel
    ka = kel * 5

    for _ in range(100):
        if abs(ka - kel) < 1e-10:
            ka = kel * 1.01
            continue

        # f(ka) = ln(ka/kel)/(ka-kel) - tmax = 0
        f = math.log(ka / kel) / (ka - kel) - tmax

        # f'(ka) = [1/ka × (ka-kel) - ln(ka/kel)] / (ka-kel)²
        denom = (ka - kel) ** 2
        if denom < 1e-20:
            break
        df = (1.0 / ka * (ka - kel) - math.log(ka / kel)) / denom

        if abs(df) < 1e-20:
            break

        ka_new = ka - f / df

        # Ограничиваем ka > kel (иначе нефизично)
        if ka_new <= kel:
            ka_new = kel * 1.01

        if abs(ka_new - ka) < 1e-8:
            ka = ka_new
            break
        ka = ka_new

    return max(ka, kel * 1.01)


def _suggest_sampling_times(
    tmax: float,
    t_half: float,
    duration: float,
) -> List[float]:
    """
    Предлагает точки отбора крови по Решению 85.

    Правила:
    - 1 точка до приёма (t=0, предозовая)
    - 3+ точки до tmax (фаза абсорбции)
    - 3+ точки около tmax (пик)
    - 4+ точки в фазе элиминации
    - Минимум 3-4 точки в терминальной фазе
    - Всего 15-20 точек
    """
    points = set()

    # Предозовая точка
    points.add(0.0)

    # Фаза абсорбции (0 → tmax)
    if tmax > 0:
        # Равномерно 4-5 точек до tmax
        step_abs = tmax / 5
        for i in range(1, 5):
            t = round(i * step_abs, 3)
            if t > 0:
                points.add(t)

    # Около tmax (±20%)
    points.add(round(tmax, 3))
    points.add(round(tmax * 1.15, 3))
    points.add(round(tmax * 1.35, 3))

    # Фаза элиминации: логарифмическое распределение
    # От 1.5×tmax до 5×T½
    elim_start = max(tmax * 1.5, tmax + 0.25)
    elim_end = min(5 * t_half, duration)
    if elim_end > elim_start:
        n_elim = 8
        for i in range(n_elim):
            frac = i / (n_elim - 1)
            t = elim_start + frac * (elim_end - elim_start)
            points.add(round(t, 3))

    # Терминальная фаза (3-4 точки в конце)
    for mult in [3.0, 3.5, 4.0, 4.5, 5.0]:
        t = mult * t_half
        if t <= duration:
            points.add(round(t, 3))

    # Сортируем и ограничиваем
    # Округляем до 0.05 ч (3 мин) для практичности
    sorted_points = sorted(set(round(t * 20) / 20 for t in points))

    # Убираем слишком близкие точки (< 3 мин разницы)
    filtered = [sorted_points[0]]
    for t in sorted_points[1:]:
        if t - filtered[-1] >= 0.04:  # минимум ~2.5 мин между точками
            filtered.append(t)
    sorted_points = filtered

    # Ограничиваем 18-20 точек
    if len(sorted_points) > 20:
        sorted_points = sorted_points[:20]

    return sorted_points


def _describe_sampling(times: List[float], tmax: float) -> str:
    """Описание схемы отбора крови для синопсиса."""
    n_total = len(times)
    pre_dose = len([t for t in times if t == 0])
    pre_tmax = len([t for t in times if 0 < t < tmax * 0.8])
    around_tmax = len([t for t in times if tmax * 0.8 <= t <= tmax * 1.5])
    post_tmax = len([t for t in times if t > tmax * 1.5])

    # Форматируем времена
    def fmt(t):
        if t == 0:
            return "0"
        if t < 1:
            return f"{t * 60:.0f} мин"
        if t == int(t):
            return f"{int(t)} ч"
        return f"{t:.2f} ч"

    times_str = ", ".join(fmt(t) for t in times)

    desc = (
        f"Схема отбора {n_total} образцов крови: "
        f"{pre_dose} предозовая, "
        f"{pre_tmax} в фазе абсорбции, "
        f"{around_tmax} около tmax, "
        f"{post_tmax} в фазе элиминации.\n"
        f"Время отбора: {times_str}."
    )
    return desc