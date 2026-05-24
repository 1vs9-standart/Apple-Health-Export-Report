"""Агрегации, VO₂-категории, корреляции и текстовые инсайты."""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple


def sum_by_day(points: Sequence[Tuple[date, float]]) -> List[Tuple[date, float]]:
    acc: Dict[date, float] = defaultdict(float)
    for d, v in points:
        acc[d] += v
    return sorted(acc.items())


def mean_by_day(points: Sequence[Tuple[date, float]]) -> List[Tuple[date, float]]:
    acc: Dict[date, List[float]] = defaultdict(list)
    for d, v in points:
        acc[d].append(v)
    return sorted((d, statistics.mean(vs)) for d, vs in acc.items())


def pct100(v: float) -> float:
    return v * 100.0 if v <= 1.5 else v


# VO₂ max (ml/kg/min) — упрощённые возрастные ориентиры (ACSM / Cooper, муж/жен)
# Источник для пользователя: cooperinstitute.org / ACSM Guidelines
VO2_TABLE_MALE: Dict[Tuple[int, int], Tuple[float, float, float, float]] = {
    (20, 29): (38.0, 42.0, 46.0, 52.0),
    (30, 39): (36.0, 40.0, 44.0, 49.0),
    (40, 49): (34.0, 38.0, 42.0, 46.0),
    (50, 59): (31.0, 35.0, 39.0, 43.0),
    (60, 99): (28.0, 32.0, 36.0, 40.0),
}
VO2_TABLE_FEMALE: Dict[Tuple[int, int], Tuple[float, float, float, float]] = {
    (20, 29): (28.0, 32.0, 36.0, 41.0),
    (30, 39): (26.0, 30.0, 34.0, 38.0),
    (40, 49): (24.0, 28.0, 32.0, 36.0),
    (50, 59): (22.0, 26.0, 30.0, 34.0),
    (60, 99): (20.0, 24.0, 28.0, 32.0),
}


def vo2_age_band(age: int) -> Tuple[int, int]:
    for lo, hi in ((20, 29), (30, 39), (40, 49), (50, 59), (60, 99)):
        if lo <= age <= hi:
            return lo, hi
    return 20, 29


def classify_vo2(value: float, age: int, sex_male: bool) -> Tuple[str, str]:
    table = VO2_TABLE_MALE if sex_male else VO2_TABLE_FEMALE
    band = vo2_age_band(age)
    poor, fair, good, excellent = table[band]
    if value >= excellent:
        return "ok", f"Отлично (≥ {excellent:.0f} для {band[0]}–{band[1]} лет)"
    if value >= good:
        return "ok", f"Хорошо ({good:.0f}–{excellent:.0f})"
    if value >= fair:
        return "info", f"Средне ({fair:.0f}–{good:.0f})"
    if value >= poor:
        return "warn", f"Ниже среднего ({poor:.0f}–{fair:.0f})"
    return "warn", f"Низкий (< {poor:.0f})"


def classify_hr_recovery(bpm_drop: float) -> Tuple[str, str]:
    """Чем больше падение пульса за 1 мин — тем лучше (ориентир для тренированности)."""
    if bpm_drop >= 25:
        return "ok", "Хорошее восстановление (≥25 уд/мин)"
    if bpm_drop >= 15:
        return "ok", "Нормальное (15–24 уд/мин)"
    if bpm_drop >= 8:
        return "info", "Умеренное (8–14 уд/мин)"
    return "warn", "Низкое (<8 уд/мин) — возможна усталость или недотренированность"


def split_spo2_day_night(
    spo2_timed: Sequence[Tuple[datetime, float]],
    sleep_intervals: Sequence[Tuple[datetime, datetime]],
) -> Tuple[List[Tuple[date, float]], List[Tuple[date, float]]]:
    day_pts: List[Tuple[date, float]] = []
    night_pts: List[Tuple[date, float]] = []
    for ts, v in spo2_timed:
        is_night = any(s <= ts <= e for s, e in sleep_intervals)
        (night_pts if is_night else day_pts).append((ts.date(), v))
    return mean_by_day(day_pts), mean_by_day(night_pts)


def pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    n = len(xs)
    if n < 5 or n != len(ys):
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
    if den == 0:
        return None
    return num / den


def sleep_hrv_correlation(
    nights_sorted: Sequence[Tuple[date, object]],
    hrv_daily: Sequence[Tuple[date, float]],
) -> Optional[float]:
    hrv_map = dict(hrv_daily)
    xs, ys = [], []
    for d, night in nights_sorted:
        if night.asleep_h <= 0:
            continue
        hrv = hrv_map.get(d)
        if hrv is None:
            hrv = hrv_map.get(d + timedelta(days=1))
        if hrv is not None:
            xs.append(night.asleep_h)
            ys.append(hrv)
    return pearson(xs, ys)


def workout_hrv_correlation(
    workouts: Sequence[object],
    hrv_daily: Sequence[Tuple[date, float]],
) -> Optional[float]:
    hrv_map = dict(hrv_daily)
    load_by_day: Dict[date, float] = defaultdict(float)
    for w in workouts:
        load_by_day[w.start.date()] += w.duration_min
    xs, ys = [], []
    for d, load in sorted(load_by_day.items()):
        nd = d + timedelta(days=1)
        if nd in hrv_map and load > 0:
            xs.append(load)
            ys.append(hrv_map[nd])
    return pearson(xs, ys)


def weekday_weekend_sleep(
    nights_sorted: Sequence[Tuple[date, object]],
) -> Dict[str, float]:
    wd, we = [], []
    for d, n in nights_sorted:
        if n.asleep_h <= 0:
            continue
        (we if d.weekday() >= 5 else wd).append(n.asleep_h)
    return {
        "weekday": statistics.mean(wd) if wd else 0.0,
        "weekend": statistics.mean(we) if we else 0.0,
    }


def zscore_outlier_days(
    daily: Sequence[Tuple[date, float]],
    low_is_bad: bool = True,
) -> List[Tuple[date, float, str]]:
    if len(daily) < 10:
        return []
    vals = [v for _, v in daily]
    mu, sigma = statistics.mean(vals), statistics.pstdev(vals)
    if sigma == 0:
        return []
    out = []
    for d, v in daily:
        z = (v - mu) / sigma
        if low_is_bad and z <= -1.5:
            out.append((d, v, f"ниже обычного (z={z:.1f})"))
        elif not low_is_bad and z >= 1.5:
            out.append((d, v, f"выше обычного (z={z:.1f})"))
        elif low_is_bad and z >= 1.5:
            out.append((d, v, f"лучше обычного (z={z:.1f})"))
    return sorted(out, key=lambda x: x[0])[-8:]


def build_insights(
    *,
    avg_asleep: Optional[float],
    med_hrv: Optional[float],
    sleep_hrv_r: Optional[float],
    workout_hrv_r: Optional[float],
    ww: Dict[str, float],
    vo2_latest: Optional[float],
    vo2_label: Optional[str],
    avg_steps: Optional[float],
    avg_distance_km: Optional[float],
    spo2_night_med: Optional[float],
    mindful_total_min: float,
    asymmetry_med: Optional[float],
    steadiness_med: Optional[float],
    hr_recovery_med: Optional[float],
) -> List[str]:
    lines: List[str] = []
    if sleep_hrv_r is not None:
        if sleep_hrv_r >= 0.25:
            lines.append(f"Сон и HRV положительно связаны (r≈{sleep_hrv_r:.2f}): больше сна — выше SDNN.")
        elif sleep_hrv_r <= -0.15:
            lines.append(f"Сон и HRV слабо отрицательно связаны (r≈{sleep_hrv_r:.2f}) — смотрите контекст (болезнь, алкоголь).")
        else:
            lines.append(f"Связь сна и HRV слабая (r≈{sleep_hrv_r:.2f}) — другие факторы доминируют.")
    if workout_hrv_r is not None and abs(workout_hrv_r) >= 0.2:
        if workout_hrv_r < 0:
            lines.append(f"После дней с большей нагрузкой HRV на следующий день ниже (r≈{workout_hrv_r:.2f}) — следите за восстановлением.")
        else:
            lines.append(f"Нагрузка и HRV на следующий день: r≈{workout_hrv_r:.2f}.")
    if ww.get("weekday") and ww.get("weekend"):
        diff = ww["weekend"] - ww["weekday"]
        if diff >= 0.5:
            lines.append(f"В выходные спите на ~{diff:.1f} ч больше — возможен «долг сна» в будни.")
        elif diff <= -0.5:
            lines.append(f"В выходные сна меньше на ~{abs(diff):.1f} ч, чем в будни.")
    if vo2_latest is not None and vo2_label:
        lines.append(f"VO₂ Max ~{vo2_latest:.1f} мл/кг/мин — {vo2_label}.")
    if avg_steps is not None:
        lines.append(f"В среднем ~{avg_steps:,.0f} шагов/день, ~{avg_distance_km or 0:.1f} км ходьбы/бега.")
    if spo2_night_med is not None:
        if spo2_night_med < 95:
            lines.append(f"Медиана SpO₂ ночью {spo2_night_med:.1f}% — ниже 95%; при храпе/одышке обсудите с врачом.")
        else:
            lines.append(f"SpO₂ ночью в норме (медиана {spo2_night_med:.1f}%).")
    if mindful_total_min > 0:
        lines.append(f"Mindfulness: {mindful_total_min:.0f} мин за период.")
    if asymmetry_med is not None and asymmetry_med > 1.0:
        lines.append(f"Асимметрия ходьбы ~{asymmetry_med:.1f}% — повышена; при неустойчивости — к врачу.")
    if steadiness_med is not None and steadiness_med < 80:
        lines.append(f"Walking Steadiness ~{steadiness_med:.0f}% — Apple отмечает сниженную устойчивость.")
    if hr_recovery_med is not None:
        _, hr_note = classify_hr_recovery(hr_recovery_med)
        lines.append(f"Восстановление пульса (1 мин): {hr_recovery_med:.0f} уд/мин — {hr_note}.")
    if avg_asleep is not None and avg_asleep < 7:
        lines.append(f"Средний сон {avg_asleep:.1f} ч — ниже ориентира CDC (7 ч).")
    return lines
