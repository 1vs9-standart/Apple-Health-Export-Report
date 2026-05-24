"""
Многофакторная оценка нагрузки и восстановления (стресс-индекс).

ВАЖНО: это НЕ медицинский диагноз и НЕ замена осмотра врача.
Модель опирается на публичные исследования вариабельности сердечного ритма (HRV),
сна и пульса в покое как маркеров автonomic balance / allostatic load.

Ключевые ориентиры в литературе:
- Task Force ESC/NASPE (1996) — стандарты измерения HRV
- Thayer JF et al. — HRV как маркер регуляции стрессом
- McEwen BS — allostatic load (суммарная «износная» нагрузка)
- Overtraining: снижение HRV + повышение RHR ( Plews et al., Bellenger et al.)
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class EvidenceRef:
    label: str
    url: str


EVIDENCE = {
    "hrv": EvidenceRef(
        "Task Force — Heart rate variability (ESC/NASPE)",
        "https://pubmed.ncbi.nlm.nih.gov/8737210/",
    ),
    "sleep": EvidenceRef(
        "CDC — Sleep duration adults",
        "https://www.cdc.gov/sleep/about/index.html",
    ),
    "rhr": EvidenceRef(
        "AHA — Resting heart rate",
        "https://www.heart.org/en/health-topics/high-blood-pressure/the-facts-about-high-blood-pressure/all-about-heart-rate-pulse",
    ),
    "allostatic": EvidenceRef(
        "McEwen — Allostatic load concept",
        "https://pubmed.ncbi.nlm.nih.gov/11720445/",
    ),
}


@dataclass
class DomainScore:
    key: str
    name_ru: str
    weight: float
    stress_0_100: float  # выше = больше нагрузки / хуже восстановление
    your_value: str
    personal_baseline: str
    z_vs_baseline: Optional[float]
    interpretation_ru: str
    evidence_key: str


@dataclass
class SleepHrvAnalysis:
    same_day_r: Optional[float]
    next_day_r: Optional[float]
    lag2_r: Optional[float]
    best_lag_days: int
    n_pairs: int
    slope_ms_per_hour: Optional[float]
    short_sleep_threshold_h: float
    hrv_short_sleep_mean: Optional[float]
    hrv_adequate_sleep_mean: Optional[float]
    effect_pct: Optional[float]
    deep_sleep_r: Optional[float]
    rem_sleep_r: Optional[float]
    sleep_efficiency_r: Optional[float]
    hrv_sleep_q1_mean: Optional[float]
    hrv_sleep_q4_mean: Optional[float]
    quartile_effect_pct: Optional[float]
    recovery_sleep_threshold_h: Optional[float]
    accumulated_sleep_debt_h: Optional[float]
    consecutive_low_hrv_days: int
    autonomic_pattern: str
    narrative: List[str] = field(default_factory=list)


@dataclass
class StressAssessment:
    daily_stress: List[Tuple[date, float]]
    daily_recovery: List[Tuple[date, float]]
    rolling7_stress: List[Tuple[date, float]]
    domain_scores: List[DomainScore]
    overall_stress_0_100: float
    overall_label: str
    overall_recovery: float
    pattern_acute: str
    pattern_chronic: str
    acute_chronic_ratio: Optional[float]
    sleep_hrv: SleepHrvAnalysis
    clinical_narrative: List[str]
    red_flags: List[str]
    limitations: List[str]
    methodology: List[str]


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    n = len(xs)
    if n < 5 or n != len(ys):
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
    return None if den == 0 else num / den


def _median_std(vals: Sequence[float]) -> Tuple[Optional[float], Optional[float]]:
    if not vals:
        return None, None
    med = statistics.median(vals)
    if len(vals) < 2:
        return med, max(abs(med) * 0.1, 1.0)
    return med, statistics.pstdev(vals)


def _z_low_is_stress(value: float, baseline: float, sigma: float, invert: bool = False) -> float:
    """Положительный z = отклонение в «стрессовую» сторону."""
    if sigma <= 0:
        sigma = max(abs(baseline) * 0.1, 1.0)
    if invert:
        z = (value - baseline) / sigma
    else:
        z = (baseline - value) / sigma
    return max(0.0, z)


def _stress_from_z(z: float) -> float:
    """z=0 -> 0 stress, z>=2.5 -> ~100."""
    return min(100.0, max(0.0, (z / 2.5) * 100.0))


def _label_stress(score: float) -> str:
    if score < 25:
        return "низкая нагрузка / хорошее восстановление"
    if score < 45:
        return "умеренная нагрузка"
    if score < 65:
        return "повышенная нагрузка — обратите внимание на отдых"
    return "высокая нагрузка — высокий риск перетренированности или стресса"


def _linear_slope(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    r = _pearson(xs, ys)
    if r is None or len(xs) < 5:
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    return None if den == 0 else num / den


def _deep_h(night: object) -> float:
    sh = getattr(night, "stages_h", {}) or {}
    return sh.get("HKCategoryValueSleepAnalysisAsleepDeep", 0.0)


def _rem_h(night: object) -> float:
    sh = getattr(night, "stages_h", {}) or {}
    return sh.get("HKCategoryValueSleepAnalysisAsleepREM", 0.0)


def _sleep_efficiency(night: object) -> Optional[float]:
    asleep = getattr(night, "asleep_h", 0.0)
    inbed = getattr(night, "inbed_h", 0.0)
    if inbed <= 0 or asleep <= 0:
        return None
    return min(100.0, asleep / inbed * 100.0)


def _metric_pairs(
    nights_sorted: Sequence[Tuple[date, object]],
    hrv_map: Dict[date, float],
    lag: int,
    metric_fn,
) -> Tuple[List[float], List[float]]:
    xs, ys = [], []
    for d, night in nights_sorted:
        m = metric_fn(night)
        if m is None or m <= 0:
            continue
        target = d + timedelta(days=lag)
        h = hrv_map.get(target)
        if h is not None:
            xs.append(m)
            ys.append(h)
    return xs, ys


def _quartile_means(pairs: Sequence[Tuple[float, float]]) -> Tuple[Optional[float], Optional[float]]:
    """HRV mean for lowest vs highest sleep quartile."""
    if len(pairs) < 8:
        return None, None
    sorted_pairs = sorted(pairs, key=lambda p: p[0])
    q = max(1, len(sorted_pairs) // 4)
    q1 = statistics.mean(h for _, h in sorted_pairs[:q])
    q4 = statistics.mean(h for _, h in sorted_pairs[-q:])
    return q1, q4


def _recovery_sleep_threshold(
    nights_sorted: Sequence[Tuple[date, object]],
    hrv_map: Dict[date, float],
    hrv_baseline: Optional[float],
    lag: int = 1,
) -> Optional[float]:
    """Минимальная длительность сна, при которой HRV (lag+1) ≥ персональной медианы."""
    if hrv_baseline is None:
        return None
    buckets: Dict[int, List[float]] = {}
    for d, night in nights_sorted:
        if night.asleep_h <= 0:
            continue
        h = hrv_map.get(d + timedelta(days=lag))
        if h is None:
            continue
        key = int(night.asleep_h * 2)
        buckets.setdefault(key, []).append(h)
    for key in sorted(buckets):
        if len(buckets[key]) < 5:
            continue
        if statistics.mean(buckets[key]) >= hrv_baseline:
            return key / 2.0
    return None


def _accumulated_sleep_debt(
    nights_sorted: Sequence[Tuple[date, object]],
    target_h: float,
    last_n_days: int = 14,
) -> Optional[float]:
    if not nights_sorted:
        return None
    recent = nights_sorted[-last_n_days:]
    debt = sum(max(0.0, target_h - n.asleep_h) for _, n in recent if n.asleep_h > 0)
    return debt if debt > 0 else 0.0


def _consecutive_low_hrv(hrv_daily: Sequence[Tuple[date, float]], baseline: Optional[float]) -> int:
    if baseline is None or not hrv_daily:
        return 0
    streak = 0
    for _, v in reversed(hrv_daily):
        if v < baseline * 0.85:
            streak += 1
        else:
            break
    return streak


def _autonomic_pattern_label(
    hrv_stress: Optional[float],
    rhr_stress: Optional[float],
    sleep_stress: Optional[float],
) -> str:
    if hrv_stress is None or rhr_stress is None:
        return "недостаточно данных для autonomic pattern"
    if hrv_stress > 55 and rhr_stress > 55:
        return (
            "sympathetic dominance — низкий парасимпатический тонус "
            "(HRV↓ + RHR↑). Типично при остром стрессе, болезни, перегрузке или хроническом недосыпе."
        )
    if hrv_stress < 35 and rhr_stress < 35:
        return "parasympathetic recovery — HRV и RHR в зоне восстановления относительно вашей базы."
    if sleep_stress is not None and sleep_stress > 50 and hrv_stress > 45:
        return (
            "sleep-driven autonomic load — недосып/фрагментация вероятно тянут HRV вниз "
            "(механизм: снижение slow-wave sleep → меньше nocturnal HRV rebound)."
        )
    return "mixed autonomic state — частичная нагрузка без классического «двойного» паттерна HRV↓+RHR↑."


def _interpret_correlation(r: Optional[float], n: int, context: str) -> Optional[str]:
    if r is None or n < 5:
        return None
    strength = "слабая"
    if abs(r) >= 0.5:
        strength = "умеренная"
    elif abs(r) >= 0.35:
        strength = "заметная"
    direction = "положительная" if r > 0 else "отрицательная"
    note = (
        f"{context}: {direction} связь r≈{r:.2f} (n={n}, {strength}). "
    )
    if n < 20:
        note += "Мало пар — трактуйте осторожно. "
    if r > 0.25:
        note += (
            "В физиологии: больше/лучше сна → выше SDNN, т.к. REM и deep sleep усиливают "
            "vagal activity и снижают nocturnal sympathetic bursts."
        )
    elif r < -0.15:
        note += (
            "Неожиданная отрицательная связь — часто шум (болезнь, алкоголь, поздние тренировки, "
            "stress без изменения длительности сна). Смотрите на стадии и efficiency."
        )
    else:
        note += (
            "При вашем профиле активности на HRV сильнее влияют тренировочная нагрузка и острые "
            "стрессоры, чем ±30–40 мин сна — но хронический <6 ч всё равно «съедает» HRV."
        )
    return note


def analyze_sleep_hrv(
    nights_sorted: Sequence[Tuple[date, object]],
    hrv_daily: Sequence[Tuple[date, float]],
    *,
    hrv_baseline: Optional[float] = None,
    sleep_target: Optional[float] = None,
) -> SleepHrvAnalysis:
    hrv_map = dict(hrv_daily)
    narrative: List[str] = []

    def pairs_for_lag(lag: int) -> Tuple[List[float], List[float]]:
        xs, ys = [], []
        for d, night in nights_sorted:
            if night.asleep_h <= 0:
                continue
            target = d + timedelta(days=lag)
            h = hrv_map.get(target)
            if h is not None:
                xs.append(night.asleep_h)
                ys.append(h)
        return xs, ys

    r0, r1, r2 = None, None, None
    best_lag = 0
    best_r = -999.0
    for lag in (0, 1, 2):
        xs, ys = pairs_for_lag(lag)
        r = _pearson(xs, ys) if xs else None
        if lag == 0:
            r0 = r
        elif lag == 1:
            r1 = r
        else:
            r2 = r
        if r is not None and abs(r) > abs(best_r):
            best_r = abs(r)
            best_lag = lag

    xs0, ys0 = pairs_for_lag(0)
    n = len(xs0)
    slope = _linear_slope(xs0, ys0)

    # Стадии и efficiency (lag+1 — HRV «на следующий день» ближе к физиологии)
    lag_phys = 1 if (r1 is not None and (r0 is None or abs(r1) >= abs(r0))) else 0
    deep_x, deep_y = _metric_pairs(nights_sorted, hrv_map, lag_phys, _deep_h)
    rem_x, rem_y = _metric_pairs(nights_sorted, hrv_map, lag_phys, _rem_h)
    eff_x, eff_y = _metric_pairs(nights_sorted, hrv_map, lag_phys, _sleep_efficiency)
    deep_r = _pearson(deep_x, deep_y) if len(deep_x) >= 5 else None
    rem_r = _pearson(rem_x, rem_y) if len(rem_x) >= 5 else None
    eff_r = _pearson(eff_x, eff_y) if len(eff_x) >= 5 else None

    short_hrv, ok_hrv = [], []
    sleep_hrv_pairs: List[Tuple[float, float]] = []
    for d, night in nights_sorted:
        if night.asleep_h <= 0:
            continue
        h = hrv_map.get(d + timedelta(days=lag_phys)) or hrv_map.get(d)
        if h is None:
            continue
        sleep_hrv_pairs.append((night.asleep_h, h))
        if night.asleep_h < 6.0:
            short_hrv.append(h)
        elif night.asleep_h >= 7.0:
            ok_hrv.append(h)

    effect_pct = None
    if short_hrv and ok_hrv:
        m_short, m_ok = statistics.mean(short_hrv), statistics.mean(ok_hrv)
        if m_ok > 0:
            effect_pct = (m_ok - m_short) / m_ok * 100.0
            if effect_pct > 5:
                narrative.append(
                    f"Контраст <6 ч vs ≥7 ч: HRV ~{m_short:.0f} мс vs ~{m_ok:.0f} мс "
                    f"(недосып −{effect_pct:.0f}% SDNN). Согласуется с литературой: sleep restriction снижает vagal tone."
                )
            elif effect_pct < -5:
                narrative.append(
                    f"Парадокс в ваших данных: ночи <6 ч → HRV ~{m_short:.0f} мс vs ≥7 ч → ~{m_ok:.0f} мс "
                    f"(короткий сон ассоциирован с более высоким SDNN на {abs(effect_pct):.0f}%). "
                    "Это НЕ значит, что недосып полезен. Частые объяснения: (1) HRV Apple измеряется не только утром; "
                    "(2) в «короткие» ночи вы могли меньше тренироваться накануне; (3) длинный сон после тяжёлой недели "
                    "может совпадать с восстановлением после overreaching, когда HRV ещё подавлен; "
                    "(4) алкоголь/болезнь сокращают сон, но кратко меняют HRV. Смотрите lag+1 и deep sleep."
                )
            else:
                narrative.append(
                    f"Разница HRV между <6 ч (~{m_short:.0f} мс) и ≥7 ч (~{m_ok:.0f} мс) минимальна — "
                    "длительность сна не главный драйвер вашего HRV; сильнее влияют нагрузка и острые стрессоры."
                )

    hrv_q1, hrv_q4 = _quartile_means(sleep_hrv_pairs)
    quartile_effect = None
    if hrv_q1 is not None and hrv_q4 is not None and hrv_q4 > 0:
        quartile_effect = (hrv_q4 - hrv_q1) / hrv_q4 * 100.0
        if quartile_effect > 5:
            narrative.append(
                f"Квартили сна: 25% коротких ночей → HRV ~{hrv_q1:.0f} мс vs 25% длинных → ~{hrv_q4:.0f} мс "
                f"(+{quartile_effect:.0f}% при большем сне)."
            )
        elif quartile_effect < -5:
            narrative.append(
                f"Квартили: короткие ночи → HRV ~{hrv_q1:.0f} мс vs длинные → ~{hrv_q4:.0f} мс "
                f"(инверсия {abs(quartile_effect):.0f}% — см. парадокс выше)."
            )

    for r_val, note in (
        (r0, _interpret_correlation(r0, n, "Сон (ч) → HRV в день пробуждения")),
        (r1, _interpret_correlation(r1, len(pairs_for_lag(1)[0]), "Сон → HRV на следующий день (lag+1)")),
        (deep_r, _interpret_correlation(deep_r, len(deep_x), "Deep sleep (ч) → HRV")),
        (rem_r, _interpret_correlation(rem_r, len(rem_x), "REM (ч) → HRV")),
        (eff_r, _interpret_correlation(eff_r, len(eff_x), "Sleep efficiency (%) → HRV")),
    ):
        if note:
            narrative.append(note)

    if slope is not None and slope > 0:
        narrative.append(
            f"Линейная модель: +1 ч сна ≈ +{slope:.1f} мс SDNN (ассоциация, не RCT). "
            "Для молодых активных людей типичный «выигрыш» от 7→8 ч часто 5–15 мс, если база уже нормальная."
        )

    if best_lag == 1 and r1 is not None and (r0 is None or abs(r1) > abs(r0) + 0.05):
        narrative.append(
            f"Сильнее всего связь с HRV на следующий день (lag+1, r≈{r1:.2f}) — "
            "соответствует модели: сон восстанавливает autonomic balance с задержкой 12–24 ч."
        )

    target = sleep_target or 7.0
    debt = _accumulated_sleep_debt(nights_sorted, target)
    if debt and debt > 3:
        narrative.append(
            f"Накопленный sleep debt за ~14 ночей: ~{debt:.1f} ч ниже цели {target:.1f} ч/ночь. "
            "Хронический debt = allostatic load (McEwen): даже «нормальный» HRV может маскировать усталость."
        )

    recovery_thr = _recovery_sleep_threshold(nights_sorted, hrv_map, hrv_baseline, lag=lag_phys)
    if recovery_thr is not None:
        narrative.append(
            f"Персональный порог восстановления HRV: при сне ≥{recovery_thr:.1f} ч ваш SDNN (lag+{lag_phys}) "
            f"в среднем достигает базовой медианы (~{hrv_baseline:.0f} мс)."
        )

    streak = _consecutive_low_hrv(hrv_daily, hrv_baseline)
    autonomic = _autonomic_pattern_label(None, None, None)

    return SleepHrvAnalysis(
        same_day_r=r0,
        next_day_r=r1,
        lag2_r=r2,
        best_lag_days=best_lag,
        n_pairs=n,
        slope_ms_per_hour=slope,
        short_sleep_threshold_h=6.0,
        hrv_short_sleep_mean=statistics.mean(short_hrv) if short_hrv else None,
        hrv_adequate_sleep_mean=statistics.mean(ok_hrv) if ok_hrv else None,
        effect_pct=effect_pct,
        deep_sleep_r=deep_r,
        rem_sleep_r=rem_r,
        sleep_efficiency_r=eff_r,
        hrv_sleep_q1_mean=hrv_q1,
        hrv_sleep_q4_mean=hrv_q4,
        quartile_effect_pct=quartile_effect,
        recovery_sleep_threshold_h=recovery_thr,
        accumulated_sleep_debt_h=debt,
        consecutive_low_hrv_days=streak,
        autonomic_pattern=autonomic,
        narrative=narrative,
    )


def compute_stress_assessment(
    *,
    nights_sorted: Sequence[Tuple[date, object]],
    hrv_daily: Sequence[Tuple[date, float]],
    rhr_daily: Sequence[Tuple[date, float]],
    spo2_night_daily: Sequence[Tuple[date, float]],
    workout_minutes_by_day: Dict[date, float],
    baseline_days: int = 28,
) -> StressAssessment:
    hrv_map = dict(hrv_daily)
    rhr_map = dict(rhr_daily)
    spo2_n_map = dict(spo2_night_daily)
    night_map = {d: n for d, n in nights_sorted}

    all_dates = sorted(set(hrv_map) | set(rhr_map) | set(night_map))
    if not all_dates:
        return StressAssessment(
            daily_stress=[],
            daily_recovery=[],
            rolling7_stress=[],
            domain_scores=[],
            overall_stress_0_100=0,
            overall_label="нет данных",
            overall_recovery=0,
            pattern_acute="",
            pattern_chronic="",
            sleep_hrv=SleepHrvAnalysis(
                None, None, None, 0, 0, None, 6.0, None, None, None,
                None, None, None, None, None, None, None, None, 0, "",
            ),
            clinical_narrative=["Недостаточно данных для оценки нагрузки."],
            red_flags=[],
            limitations=_default_limitations(),
            methodology=_methodology_text(),
            acute_chronic_ratio=None,
        )

    # Персональные базовые уровни (первая часть периода, без последних 7 дней если возможно)
    split = max(7, len(all_dates) - 7)
    baseline_dates = all_dates[: max(split, min(baseline_days, len(all_dates)))]
    bl_hrv = [hrv_map[d] for d in baseline_dates if d in hrv_map]
    bl_rhr = [rhr_map[d] for d in baseline_dates if d in rhr_map]
    bl_sleep = [night_map[d].asleep_h for d in baseline_dates if d in night_map and night_map[d].asleep_h > 0]
    bl_awake = [night_map[d].awake_h * 60 for d in baseline_dates if d in night_map]

    hrv_med, hrv_sig = _median_std(bl_hrv)
    rhr_med, rhr_sig = _median_std(bl_rhr)
    sleep_med, sleep_sig = _median_std(bl_sleep)
    awake_med, awake_sig = _median_std(bl_awake)

    sleep_target = max(7.0, sleep_med or 7.0)

    daily_stress: List[Tuple[date, float]] = []
    domain_latest: List[DomainScore] = []

    for d in all_dates:
        components: List[Tuple[float, float]] = []  # weight, stress

        if d in hrv_map and hrv_med is not None:
            z = _z_low_is_stress(hrv_map[d], hrv_med, hrv_sig or 5.0)
            s = _stress_from_z(z)
            components.append((0.32, s))

        if d in rhr_map and rhr_med is not None:
            z = _z_low_is_stress(rhr_map[d], rhr_med, rhr_sig or 3.0, invert=True)
            s = _stress_from_z(z)
            components.append((0.22, s))

        if d in night_map and night_map[d].asleep_h > 0:
            sleep_h = night_map[d].asleep_h
            z_sleep = _z_low_is_stress(sleep_h, sleep_target, sleep_sig or 0.75)
            components.append((0.26, _stress_from_z(z_sleep)))
            awake_m = night_map[d].awake_h * 60
            if awake_med is not None:
                z_aw = _z_low_is_stress(awake_m, awake_med, awake_sig or 10.0, invert=True)
                components.append((0.08, _stress_from_z(z_aw)))

        # Нагрузка vs восстановление: вчера много тренировок + сегодня низкий HRV
        yd = d - timedelta(days=1)
        load_y = workout_minutes_by_day.get(yd, 0)
        if load_y >= 60 and d in hrv_map and hrv_med is not None and hrv_map[d] < hrv_med * 0.9:
            components.append((0.07, min(100.0, 40.0 + load_y / 3.0)))

        if d in spo2_n_map and spo2_n_map[d] < 95:
            components.append((0.05, _stress_from_z((95 - spo2_n_map[d]) / 1.5)))

        if components:
            w_sum = sum(w for w, _ in components)
            stress = sum(w * s for w, s in components) / w_sum
        else:
            stress = 50.0
        daily_stress.append((d, stress))

    # rolling 7d
    rolling7: List[Tuple[date, float]] = []
    for i, (d, _) in enumerate(daily_stress):
        window = [s for _, s in daily_stress[max(0, i - 6) : i + 1]]
        rolling7.append((d, statistics.mean(window)))

    latest_d = daily_stress[-1][0]
    latest_stress = daily_stress[-1][1]

    # Domain scores for latest day
    if latest_d in hrv_map and hrv_med is not None:
        z = _z_low_is_stress(hrv_map[latest_d], hrv_med, hrv_sig or 5.0)
        interp = "SDNN на уровне или выше вашей базы — автonomic balance ближе к восстановлению."
        if z > 0.5:
            interp = (
                "SDNN ниже вашей персональной базы. В клинических и спортивных исследованиях "
                "стойкое снижение HRV связано с психологическим стрессом, недосыпом, болезнью и перегрузкой."
            )
        domain_latest.append(
            DomainScore(
                "hrv", "HRV (SDNN)", 0.32, _stress_from_z(z),
                f"{hrv_map[latest_d]:.0f} мс", f"ваша база ~{hrv_med:.0f} мс", z,
                interp, "hrv",
            )
        )

    if latest_d in rhr_map and rhr_med is not None:
        z = _z_low_is_stress(rhr_map[latest_d], rhr_med, rhr_sig or 3.0, invert=True)
        interp = "Пульс покоя в пределах вашей обычной линии."
        if z > 0.5:
            interp = (
                "RHR выше обычного для вас. Стойкое повышение может сопровождать стресс, "
                "обезвоживание, болезнь, недосып или перетренированность (AHA, sports medicine)."
            )
        domain_latest.append(
            DomainScore(
                "rhr", "Пульс покоя", 0.22, _stress_from_z(z),
                f"{rhr_map[latest_d]:.0f} уд/мин", f"база ~{rhr_med:.0f}", z,
                interp, "rhr",
            )
        )

    if latest_d in night_map and night_map[latest_d].asleep_h > 0:
        sh = night_map[latest_d].asleep_h
        z = _z_low_is_stress(sh, sleep_target, sleep_sig or 0.75)
        domain_latest.append(
            DomainScore(
                "sleep", "Сон", 0.26, _stress_from_z(z),
                f"{sh:.1f} ч", f"цель ≥{sleep_target:.1f} ч (CDC + ваш профиль)", z,
                "Недосып — один из самых надёжных факторов снижения HRV на следующий день." if z > 0.3 else "Сон в пределах цели.",
                "sleep",
            )
        )

    sleep_hrv = analyze_sleep_hrv(
        nights_sorted, hrv_daily, hrv_baseline=hrv_med, sleep_target=sleep_target
    )

    # Autonomic pattern по последнему дню
    hrv_s = next((d.stress_0_100 for d in domain_latest if d.key == "hrv"), None)
    rhr_s = next((d.stress_0_100 for d in domain_latest if d.key == "rhr"), None)
    sleep_s = next((d.stress_0_100 for d in domain_latest if d.key == "sleep"), None)
    autonomic = _autonomic_pattern_label(hrv_s, rhr_s, sleep_s)
    streak = _consecutive_low_hrv(hrv_daily, hrv_med)
    sleep_hrv = SleepHrvAnalysis(
        same_day_r=sleep_hrv.same_day_r,
        next_day_r=sleep_hrv.next_day_r,
        lag2_r=sleep_hrv.lag2_r,
        best_lag_days=sleep_hrv.best_lag_days,
        n_pairs=sleep_hrv.n_pairs,
        slope_ms_per_hour=sleep_hrv.slope_ms_per_hour,
        short_sleep_threshold_h=sleep_hrv.short_sleep_threshold_h,
        hrv_short_sleep_mean=sleep_hrv.hrv_short_sleep_mean,
        hrv_adequate_sleep_mean=sleep_hrv.hrv_adequate_sleep_mean,
        effect_pct=sleep_hrv.effect_pct,
        deep_sleep_r=sleep_hrv.deep_sleep_r,
        rem_sleep_r=sleep_hrv.rem_sleep_r,
        sleep_efficiency_r=sleep_hrv.sleep_efficiency_r,
        hrv_sleep_q1_mean=sleep_hrv.hrv_sleep_q1_mean,
        hrv_sleep_q4_mean=sleep_hrv.hrv_sleep_q4_mean,
        quartile_effect_pct=sleep_hrv.quartile_effect_pct,
        recovery_sleep_threshold_h=sleep_hrv.recovery_sleep_threshold_h,
        accumulated_sleep_debt_h=sleep_hrv.accumulated_sleep_debt_h,
        consecutive_low_hrv_days=streak,
        autonomic_pattern=autonomic,
        narrative=sleep_hrv.narrative,
    )

    # Acute:chronic ratio (как training load ratio)
    ac_ratio = None
    if len(rolling7) >= 28:
        acute_roll = statistics.mean([s for _, s in rolling7[-7:]])
        chronic_roll = statistics.mean([s for _, s in rolling7[-28:]])
        if chronic_roll > 0:
            ac_ratio = acute_roll / chronic_roll
    last7 = [s for _, s in daily_stress[-7:]]
    prev7 = [s for _, s in daily_stress[-14:-7]] if len(daily_stress) >= 14 else []
    acute = ""
    if last7 and prev7:
        d7 = statistics.mean(last7) - statistics.mean(prev7)
        if d7 >= 12:
            acute = f"За последнюю неделю индекс нагрузки вырос на ~{d7:.0f} пунктов vs предыдущая неделя — острый стресс/перегрузка."
        elif d7 <= -12:
            acute = f"За неделю индекс снизился на ~{abs(d7):.0f} пунктов — восстановление улучшается."
        else:
            acute = "Острая динамика (7 vs 7 дней): без резких сдвигов."

    chronic = ""
    if len(rolling7) >= 14:
        recent = statistics.mean([s for _, s in rolling7[-7:]])
        earlier = statistics.mean([s for _, s in rolling7[-14:-7]])
        if recent >= 55 and recent > earlier + 5:
            chronic = "Хронически повышенная нагрузка (средний 7-дневный индекс ≥55) — риск burnout/перетренированности; нужен план восстановления."
        elif recent < 35:
            chronic = "Длительно низкий индекс нагрузки — хорошее восстановление или недостаток данных/нагрузки."
        else:
            chronic = "Хронический фон: умеренный, типичный для активного образа жизни."

    if ac_ratio is not None:
        if ac_ratio >= 1.25:
            chronic = (chronic or "") + f" A:C ratio {ac_ratio:.2f} — острая нагрузка заметно выше хронической (≥1.25)."
        elif ac_ratio <= 0.85:
            chronic = (chronic or "") + f" A:C ratio {ac_ratio:.2f} — фаза восстановления (острая ниже хронической)."

    narrative = _build_clinical_narrative(
        latest_stress, domain_latest, sleep_hrv, last7, hrv_med, rhr_med, ac_ratio
    )
    red_flags = _red_flags(domain_latest, last7, sleep_hrv, spo2_n_map, latest_d, ac_ratio)

    return StressAssessment(
        daily_stress=daily_stress,
        daily_recovery=[(d, 100 - s) for d, s in daily_stress],
        rolling7_stress=rolling7,
        domain_scores=domain_latest,
        overall_stress_0_100=latest_stress,
        overall_label=_label_stress(latest_stress),
        overall_recovery=100 - latest_stress,
        pattern_acute=acute,
        pattern_chronic=chronic,
        sleep_hrv=sleep_hrv,
        clinical_narrative=narrative,
        red_flags=red_flags,
        limitations=_default_limitations(),
        methodology=_methodology_text(),
        acute_chronic_ratio=ac_ratio,
    )


def _default_limitations() -> List[str]:
    return [
        "Apple Watch SDNN ≠ медицинская HRV (не RMSSD, не 24-ч Holter).",
        "Нет кортизола, давления, симптомов, лекарств — модель неполная.",
        "Корреляция сон–HRV не доказывает причинность.",
        "Индекс калиброван относительно ваших же данных, не популяционных норм.",
        "При тревожных симптомах — очный врач, не этот отчёт.",
    ]


def _methodology_text() -> List[str]:
    return [
        "1. Персональная база: медиана HRV, RHR, сна за первые ~28 дней окна (без последней недели).",
        "2. Для каждого дня: z-отклонение от базы → доменный stress 0–100 (HRV 32%, RHR 22%, сон 26%, фрагментация 8%, нагрузка 7%, SpO₂ ночью 5%).",
        "3. Индекс нагрузки = взвешенное среднее доменов. Recovery = 100 − нагрузка.",
        "4. Сон→HRV: Pearson r (lag 0–2), deep/REM/efficiency, квартили сна, sleep debt, порог восстановления HRV.",
        "5. A:C ratio = 7д rolling / 28д rolling (аналог training load ratio).",
        "6. Ориентиры: Task Force HRV (1996), McEwen allostatic load, overtraining (HRV↓ + RHR↑).",
    ]


def _build_clinical_narrative(
    latest_stress: float,
    domains: List[DomainScore],
    sleep_hrv: SleepHrvAnalysis,
    last7: List[float],
    hrv_med: Optional[float],
    rhr_med: Optional[float],
    ac_ratio: Optional[float] = None,
) -> List[str]:
    lines: List[str] = []
    lines.append(
        f"Сводная оценка на последнюю дату: индекс нагрузки {latest_stress:.0f}/100 — {_label_stress(latest_stress)}."
    )
    if last7:
        lines.append(f"Средний индекс за 7 дней: {statistics.mean(last7):.0f}/100.")

    if sleep_hrv.autonomic_pattern:
        lines.append(f"Autonomic pattern: {sleep_hrv.autonomic_pattern}")

    if sleep_hrv.consecutive_low_hrv_days >= 3 and hrv_med is not None:
        lines.append(
            f"HRV ниже ~85% вашей базы ({hrv_med:.0f} мс) уже {sleep_hrv.consecutive_low_hrv_days} дней подряд — "
            "в спортивной медицине это red flag перегрузки; нужен deload и аудит сна."
        )

    if ac_ratio is not None:
        if ac_ratio >= 1.25:
            lines.append(
                f"Acute:Chronic stress ratio ≈{ac_ratio:.2f} (7д/28д rolling) — острая нагрузка превышает хронический фон; "
                "риск overreaching, если не снижать интенсивность."
            )
        elif ac_ratio <= 0.85:
            lines.append(
                f"A:C ratio ≈{ac_ratio:.2f} — организм в фазе восстановления относительно недавнего фона."
            )

    hrv_d = next((d for d in domains if d.key == "hrv"), None)
    rhr_d = next((d for d in domains if d.key == "rhr"), None)
    sleep_d = next((d for d in domains if d.key == "sleep"), None)

    if hrv_d and rhr_d:
        if hrv_d.stress_0_100 > 50 and rhr_d.stress_0_100 > 50:
            lines.append(
                "Паттерн «низкий HRV + высокий RHR» относительно вашей базы — классический признак симpathetic dominance "
                "(стресс, недосып, болезнь или избыточная нагрузка). Так смотрят спортивные врачи при overreaching."
            )
        elif hrv_d.stress_0_100 < 30 and rhr_d.stress_0_100 < 30:
            lines.append("HRV и RHR в комфортной зоне относительно базы — autonomic recovery благоприятный.")

    if sleep_d and sleep_d.stress_0_100 > 45:
        if sleep_hrv.effect_pct is not None and sleep_hrv.effect_pct > 10:
            lines.append(
                "Сон — главный modifiable фактор для вашего HRV. Приоритет: стабильный режим, 7+ ч."
            )
        else:
            lines.append(
                f"Сон сейчас короткий ({sleep_d.your_value}), но связь сон→HRV у вас не линейная — "
                "фокус на качестве (deep/REM, меньше awake), режиме и sleep debt, а не только на часах."
            )

    if sleep_hrv.deep_sleep_r is not None and sleep_hrv.deep_sleep_r > 0.3:
        lines.append(
            f"Deep sleep коррелирует с HRV (r≈{sleep_hrv.deep_sleep_r:.2f}) — slow-wave sleep критичен для "
            "nocturnal cardiac vagal modulation; при хроническом недосыпе deep sleep падает первым."
        )

    lines.extend(sleep_hrv.narrative)
    return lines


def _red_flags(
    domains: List[DomainScore],
    last7: List[float],
    sleep_hrv: SleepHrvAnalysis,
    spo2_n: Dict[date, float],
    latest_d: date,
    ac_ratio: Optional[float] = None,
) -> List[str]:
    flags: List[str] = []
    if last7 and statistics.mean(last7) >= 65:
        flags.append("Индекс нагрузки ≥65 в среднем за неделю — рассмотрите дни полного отдыха и сокращение интенсивности.")

    hrv_d = next((d for d in domains if d.key == "hrv"), None)
    rhr_d = next((d for d in domains if d.key == "rhr"), None)
    if hrv_d and rhr_d and hrv_d.stress_0_100 > 60 and rhr_d.stress_0_100 > 60:
        flags.append("Сочетание низкого HRV и высокого RHR >3–5 дней подряд — обратитесь к врачу при усталости, боли в груди, одышке.")

    if latest_d in spo2_n and spo2_n[latest_d] <= 92:
        flags.append("SpO₂ ≤92% ночью — медицинская срочность; не откладывайте визит.")

    if sleep_hrv.effect_pct and sleep_hrv.effect_pct > 20:
        flags.append(
            f"Недосып (<6 ч) связан с падением HRV ~{sleep_hrv.effect_pct:.0f}% — хронический недосып = хронический стресс для организма."
        )
    if sleep_hrv.consecutive_low_hrv_days >= 5:
        flags.append(
            f"HRV подавлен {sleep_hrv.consecutive_low_hrv_days} дней подряд — рассмотрите полный rest day, "
            "снижение кофеина/алкоголя, проверку сна и при симптомах — врач."
        )

    if ac_ratio and ac_ratio >= 1.35:
        flags.append(
            f"A:C stress ratio {ac_ratio:.2f} — острая нагрузка существенно выше хронической; "
            "высокий риск overreaching без deload."
        )

    if sleep_hrv.accumulated_sleep_debt_h and sleep_hrv.accumulated_sleep_debt_h > 10:
        flags.append(
            f"Sleep debt ~{sleep_hrv.accumulated_sleep_debt_h:.0f} ч за 2 недели — приоритет №1 для HRV, не «ещё одна тренировка»."
        )

    return flags
