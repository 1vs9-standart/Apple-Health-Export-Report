#!/usr/bin/env python3
"""
Анализ экспорта Apple Health: export.xml, electrocardiograms/, workout-routes/.

Это НЕ медицинский диагноз. Скрипт сравнивает ваши данные с публичными
клиническими ориентирами (CDC, WHO, AHA и др.) и показывает тренды.

Требует только стандартную библиотеку Python 3.9+.
"""

from __future__ import annotations

import argparse
import html
import math
import re
import statistics
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Клинические ориентиры (публичные рекомендации, не персональный диагноз)
# Источники указаны в поле source — это официальные/общепринятые руководства.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClinicalRef:
    metric: str
    normal_text: str
    source: str
    source_url: str
    # optional numeric checks: (min_ok, max_ok) inclusive; None = open bound
    min_ok: Optional[float] = None
    max_ok: Optional[float] = None
    warn_below: Optional[float] = None
    warn_above: Optional[float] = None
    unit: str = ""


CLINICAL_REFS: Dict[str, ClinicalRef] = {
    "sleep_hours_adult": ClinicalRef(
        metric="Сон (взрослые 18–60 лет)",
        normal_text="≥ 7 часов за сутки",
        source="CDC — How Much Sleep Do I Need?",
        source_url="https://www.cdc.gov/sleep/about/index.html",
        min_ok=7.0,
        warn_below=7.0,
        unit="ч/сут",
    ),
    "resting_hr_adult": ClinicalRef(
        metric="Пульс в покое (взрослые)",
        normal_text="60–100 уд/мин (у тренированных людей часто ниже)",
        source="American Heart Association — All About Heart Rate",
        source_url="https://www.heart.org/en/health-topics/high-blood-pressure/the-facts-about-high-blood-pressure/all-about-heart-rate-pulse",
        min_ok=60.0,
        max_ok=100.0,
        warn_below=60.0,
        warn_above=100.0,
        unit="уд/мин",
    ),
    "spo2_sea_level": ClinicalRef(
        metric="Насыщение крови кислородом (SpO₂)",
        normal_text="≥ 95% на уровне моря; ≤ 92% — повод срочно обратиться к врачу",
        source="WHO — Oxygen therapy for children / клинические пороги гипоксемии",
        source_url="https://www.who.int/publications/i/item/9789241549554",
        min_ok=95.0,
        warn_below=95.0,
        unit="%",
    ),
    "respiratory_rate_adult": ClinicalRef(
        metric="Частота дыхания (в покое, взрослые)",
        normal_text="12–20 вдохов/мин",
        source="Cleveland Clinic / Merck Manual (общепринятый клинический диапазон)",
        source_url="https://my.clevelandclinic.org/health/articles/17488-vital-signs-body-temperature-pulse-rate-respiration-rate-blood-pressure",
        min_ok=12.0,
        max_ok=20.0,
        warn_below=12.0,
        warn_above=20.0,
        unit="вд/мин",
    ),
    "bmi_adult": ClinicalRef(
        metric="ИМТ (взрослые)",
        normal_text="18,5–24,9 — норма; 25–29,9 — избыточный вес; ≥ 30 — ожирение",
        source="WHO — Body mass index (BMI)",
        source_url="https://www.who.int/europe/news-room/fact-sheets/item/a-healthy-lifestyle---who-recommendations",
        min_ok=18.5,
        max_ok=24.9,
        warn_below=18.5,
        warn_above=25.0,
        unit="кг/м²",
    ),
    "weekly_moderate_activity": ClinicalRef(
        metric="Физическая активность (взрослые 18–64)",
        normal_text="150–300 мин умеренной или 75–150 мин интенсивной активности в неделю",
        source="WHO — Physical activity",
        source_url="https://www.who.int/news-room/fact-sheets/detail/physical-activity",
        min_ok=150.0,
        warn_below=150.0,
        unit="мин/нед",
    ),
    "ecg_sinus": ClinicalRef(
        metric="ЭКГ Apple Watch — Sinus Rhythm",
        normal_text="Синусовый ритм — ожидаемый результат при отсутствии аритмии на записи",
        source="Apple — Understanding your results (ECG app)",
        source_url="https://support.apple.com/guide/watch/understand-your-results-apd9479bf18/watchos",
        unit="",
    ),
    "ecg_afib": ClinicalRef(
        metric="ЭКГ Apple Watch — Atrial Fibrillation",
        normal_text="Обнаружена фибрилляция предсердий — нужна консультация врача",
        source="Apple — Understanding your results (ECG app)",
        source_url="https://support.apple.com/guide/watch/understand-your-results-apd9479bf18/watchos",
        unit="",
    ),
    "vo2_max": ClinicalRef(
        metric="VO₂ Max (кардиофитнес)",
        normal_text="Зависит от возраста и пола — см. ACSM / Cooper Institute",
        source="ACSM Guidelines for Exercise Testing and Prescription",
        source_url="https://www.acsm.org/education-resources/trending-topics-resources/physical-activity-guidelines",
        unit="мл/кг/мин",
    ),
    "hr_recovery": ClinicalRef(
        metric="Восстановление пульса (1 мин)",
        normal_text="≥15–25 уд/мин падения — хороший ориентир тренированности",
        source="Exercise physiology (общепринятые пороги)",
        source_url="https://www.heart.org/en/health-topics/high-blood-pressure/the-facts-about-high-blood-pressure/all-about-heart-rate-pulse",
        unit="уд/мин",
    ),
    "daily_steps": ClinicalRef(
        metric="Шаги в день",
        normal_text="~7000–10000 шагов связаны с пользой для здоровья (WHO / исследования)",
        source="WHO — Physical activity",
        source_url="https://www.who.int/news-room/fact-sheets/detail/physical-activity",
        unit="шагов",
    ),
}

WORKOUT_TYPE_LABELS = {
    "HKWorkoutActivityTypeWalking": "Ходьба",
    "HKWorkoutActivityTypeRunning": "Бег",
    "HKWorkoutActivityTypeCycling": "Велосипед",
    "HKWorkoutActivityTypeCooldown": "Заминка",
    "HKWorkoutActivityTypeHighIntensityIntervalTraining": "HIIT",
    "HKWorkoutActivityTypeCrossTraining": "Кросс-тренинг",
}


@dataclass
class RefCheck:
    ref_key: str
    your_value: str
    status: str  # ok | warn | alert | info | na
    note: str


def classify_value(ref: ClinicalRef, value: float) -> RefCheck:
    status = "ok"
    note = f"В пределах ориентира: {ref.normal_text}"
    if ref.warn_below is not None and value < ref.warn_below:
        status = "warn" if (ref.min_ok is None or value >= (ref.min_ok - 5 if ref.min_ok else 0)) else "warn"
        if ref.metric.startswith("SpO") and value <= 92:
            status = "alert"
            note = "≤ 92% — клинически значимая гипоксемия, нужна медицинская помощь"
        else:
            note = f"Ниже ориентира ({ref.normal_text})"
    if ref.max_ok is not None and value > ref.max_ok:
        status = "warn"
        note = f"Выше верхней границы ориентира ({ref.max_text if hasattr(ref, 'max_text') else ref.normal_text})"
    if ref.warn_above is not None and value >= ref.warn_above and ref.max_ok is None:
        status = "warn"
        note = f"Выше порога «норма» ({ref.normal_text})"
    if ref.min_ok is not None and ref.max_ok is not None and ref.min_ok <= value <= ref.max_ok:
        status = "ok"
        note = "В пределах клинического ориентира"
    return RefCheck(ref.ref_key if hasattr(ref, "ref_key") else "", f"{value:.2g} {ref.unit}".strip(), status, note)


def bmi_category(bmi: float) -> Tuple[str, str]:
    if bmi < 18.5:
        return "warn", "Недостаточная масса (WHO: < 18,5)"
    if bmi <= 24.9:
        return "ok", "Норма (WHO: 18,5–24,9)"
    if bmi <= 29.9:
        return "warn", "Избыточный вес (WHO: 25–29,9)"
    return "warn", "Ожирение (WHO: ≥ 30)"


# ---------- Даты Apple: "2025-06-19 18:54:38 +0200"


def parse_cda_dt(s: Optional[str]) -> Optional[datetime]:
    """CDA effectiveTime: 20250610142734+0200"""
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), "%Y%m%d%H%M%S%z")
    except ValueError:
        return None


def detect_export_format(path: Path) -> str:
    try:
        with path.open(encoding="utf-8") as f:
            head = f.read(4096)
    except OSError:
        return "healthkit"
    if "ClinicalDocument" in head:
        return "cda"
    if "HealthData" in head:
        return "healthkit"
    return "healthkit"


def parse_cda_profile(path: Path) -> Tuple[Optional[date], Optional[str]]:
    try:
        with path.open(encoding="utf-8") as f:
            head = f.read(8000)
    except OSError:
        return None, None
    birth: Optional[date] = None
    m = re.search(r'<birthTime value="(\d{8})"', head)
    if m:
        raw = m.group(1)
        birth = date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    sex: Optional[str] = None
    m2 = re.search(r'administrativeGenderCode code="([MF])"', head)
    if m2:
        sex = "HKBiologicalSexMale" if m2.group(1) == "M" else "HKBiologicalSexFemale"
    return birth, sex


def iter_cda_observations(path: Path) -> Iterator[Tuple[str, datetime, datetime, Optional[str]]]:
    """
    Потоковый разбор export_cda.xml.
    Файл Apple иногда содержит несколько корневых блоков — iterparse ломается,
    поэтому собираем каждый <observation>...</observation> отдельно.
    """
    re_type = re.compile(r"<type>(HK[^<]+)</type>")
    re_text_val = re.compile(r"<text>.*?<value>([^<]+)</value>", re.DOTALL)
    re_pq = re.compile(r'<value xsi:type="PQ" value="([^"]+)"')
    re_low = re.compile(r'<low value="([^"]+)"')
    re_high = re.compile(r'<high value="([^"]+)"')
    buf: List[str] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            buf.append(line)
            if "</observation>" not in line:
                continue
            block = "".join(buf)
            buf.clear()
            tm = re_type.search(block)
            if not tm:
                continue
            lm, hm = re_low.search(block), re_high.search(block)
            if not lm or not hm:
                continue
            start, end = parse_cda_dt(lm.group(1)), parse_cda_dt(hm.group(1))
            if start is None or end is None:
                continue
            val_raw: Optional[str] = None
            tvm = re_text_val.search(block)
            if tvm:
                val_raw = tvm.group(1).strip()
            elif re_pq.search(block):
                val_raw = re_pq.search(block).group(1)  # type: ignore[union-attr]
            yield tm.group(1), start, end, val_raw


@dataclass
class ParsedHealthData:
    birth_date: Optional[date] = None
    sex: Optional[str] = None
    hrv_points: List[Tuple[date, float]] = field(default_factory=list)
    rhr_points: List[Tuple[date, float]] = field(default_factory=list)
    spo2_timed: List[Tuple[datetime, float]] = field(default_factory=list)
    rr_points: List[Tuple[date, float]] = field(default_factory=list)
    bmi_points: List[Tuple[date, float]] = field(default_factory=list)
    step_points: List[Tuple[date, float]] = field(default_factory=list)
    distance_points: List[Tuple[date, float]] = field(default_factory=list)
    flights_points: List[Tuple[date, float]] = field(default_factory=list)
    vo2_points: List[Tuple[date, float]] = field(default_factory=list)
    hr_recovery_points: List[Tuple[date, float]] = field(default_factory=list)
    body_mass_points: List[Tuple[date, float]] = field(default_factory=list)
    body_fat_points: List[Tuple[date, float]] = field(default_factory=list)
    lean_mass_points: List[Tuple[date, float]] = field(default_factory=list)
    asymmetry_points: List[Tuple[date, float]] = field(default_factory=list)
    steadiness_points: List[Tuple[date, float]] = field(default_factory=list)
    mindful_minutes: List[Tuple[date, float]] = field(default_factory=list)
    rmssd_points: List[Tuple[date, float]] = field(default_factory=list)
    state_of_mind: List = field(default_factory=list)
    scored_assessments: List = field(default_factory=list)
    sleep_intervals: List[Tuple[datetime, datetime]] = field(default_factory=list)
    nights: Dict[date, SleepNight] = field(default_factory=dict)
    workouts: List[WorkoutSummary] = field(default_factory=list)
    seen_records: set = field(default_factory=set)
    sources_used: List[str] = field(default_factory=list)


def record_dedup_key(hk_type: str, start: datetime, end: datetime, val_raw: Optional[str]) -> Tuple[str, str, str, str]:
    return (hk_type, start.isoformat(), end.isoformat(), val_raw or "")


def ingest_record(
    state: ParsedHealthData,
    hk_type: str,
    start: datetime,
    end: datetime,
    val_raw: Optional[str],
    cutoff: datetime,
    dedup: bool,
    meta: Optional[Dict[str, str]] = None,
    hrv_beats: Optional[List[Tuple[float, datetime]]] = None,
) -> None:
    from apple_health.mental_health import (
        compute_rmssd_ms,
        parse_scored_assessment_from_record,
        parse_state_of_mind_from_record,
    )

    if to_utc(end) < cutoff:
        return
    if dedup:
        key = record_dedup_key(hk_type, start, end, val_raw)
        if key in state.seen_records:
            return
        state.seen_records.add(key)

    meta = meta or {}
    d = start.date()

    som = parse_state_of_mind_from_record(hk_type, d, meta, val_raw)
    if som:
        state.state_of_mind.append(som)

    assessment = parse_scored_assessment_from_record(hk_type, d, meta, val_raw)
    if assessment:
        state.scored_assessments.append(assessment)

    if hk_type == "HKQuantityTypeIdentifierHeartRateVariabilitySDNN" and val_raw:
        try:
            state.hrv_points.append((d, float(val_raw)))
            if hrv_beats:
                rmssd = compute_rmssd_ms(hrv_beats)
                if rmssd is not None:
                    state.rmssd_points.append((d, rmssd))
        except ValueError:
            pass
    elif hk_type == "HKQuantityTypeIdentifierHeartRateVariabilityRMSSD" and val_raw:
        try:
            state.rmssd_points.append((d, float(val_raw)))
        except ValueError:
            pass
    elif hk_type == "HKQuantityTypeIdentifierRestingHeartRate" and val_raw:
        try:
            state.rhr_points.append((start.date(), float(val_raw)))
        except ValueError:
            pass
    elif hk_type == "HKQuantityTypeIdentifierOxygenSaturation" and val_raw:
        try:
            v = float(val_raw)
            if v <= 1.5:
                v *= 100.0
            state.spo2_timed.append((start, v))
        except ValueError:
            pass
    elif hk_type == "HKQuantityTypeIdentifierStepCount" and val_raw:
        try:
            state.step_points.append((start.date(), float(val_raw)))
        except ValueError:
            pass
    elif hk_type == "HKQuantityTypeIdentifierDistanceWalkingRunning" and val_raw:
        try:
            state.distance_points.append((start.date(), float(val_raw)))
        except ValueError:
            pass
    elif hk_type == "HKQuantityTypeIdentifierFlightsClimbed" and val_raw:
        try:
            state.flights_points.append((start.date(), float(val_raw)))
        except ValueError:
            pass
    elif hk_type == "HKQuantityTypeIdentifierVO2Max" and val_raw:
        try:
            state.vo2_points.append((start.date(), float(val_raw)))
        except ValueError:
            pass
    elif hk_type == "HKQuantityTypeIdentifierHeartRateRecoveryOneMinute" and val_raw:
        try:
            state.hr_recovery_points.append((start.date(), float(val_raw)))
        except ValueError:
            pass
    elif hk_type == "HKQuantityTypeIdentifierBodyMass" and val_raw:
        try:
            state.body_mass_points.append((start.date(), float(val_raw)))
        except ValueError:
            pass
    elif hk_type == "HKQuantityTypeIdentifierBodyFatPercentage" and val_raw:
        try:
            v = float(val_raw)
            state.body_fat_points.append((start.date(), v * 100.0 if v <= 1.5 else v))
        except ValueError:
            pass
    elif hk_type == "HKQuantityTypeIdentifierLeanBodyMass" and val_raw:
        try:
            state.lean_mass_points.append((start.date(), float(val_raw)))
        except ValueError:
            pass
    elif hk_type == "HKQuantityTypeIdentifierWalkingAsymmetryPercentage" and val_raw:
        try:
            v = float(val_raw)
            state.asymmetry_points.append((start.date(), v * 100.0 if v <= 1.5 else v))
        except ValueError:
            pass
    elif hk_type == "HKQuantityTypeIdentifierAppleWalkingSteadiness" and val_raw:
        try:
            v = float(val_raw)
            state.steadiness_points.append((start.date(), v * 100.0 if v <= 1.5 else v))
        except ValueError:
            pass
    elif hk_type == "HKCategoryTypeIdentifierMindfulSession":
        dur = (end - start).total_seconds() / 60.0
        if dur > 0:
            state.mindful_minutes.append((start.date(), dur))
    elif hk_type == "HKQuantityTypeIdentifierRespiratoryRate" and val_raw:
        try:
            state.rr_points.append((start.date(), float(val_raw)))
        except ValueError:
            pass
    elif hk_type == "HKQuantityTypeIdentifierBodyMassIndex" and val_raw:
        try:
            state.bmi_points.append((start.date(), float(val_raw)))
        except ValueError:
            pass
    elif hk_type == "HKCategoryTypeIdentifierSleepAnalysis":
        val = val_raw or ""
        dur_h = (end - start).total_seconds() / 3600.0
        if dur_h <= 0:
            return
        key = night_key_from_segment_end(end)
        night = state.nights.setdefault(key, SleepNight(date_key=key))
        if val in ASLEEP_VALUES:
            night.asleep_h += dur_h
            night.stages_h[val] += dur_h
            state.sleep_intervals.append((start, end))
        elif val == "HKCategoryValueSleepAnalysisAwake":
            night.awake_h += dur_h
        elif val == "HKCategoryValueSleepAnalysisInBed":
            night.inbed_h += dur_h


def load_from_healthkit(path: Path, data_dir: Path, cutoff: datetime, state: ParsedHealthData, dedup: bool) -> None:
    for tag, elem in iter_export_events(path):
        if tag == "Me":
            if not state.birth_date:
                state.birth_date = parse_apple_date(elem.get("HKCharacteristicTypeIdentifierDateOfBirth"))
            if not state.sex:
                state.sex = elem.get("HKCharacteristicTypeIdentifierBiologicalSex")
            continue
        if tag == "Workout":
            end = parse_apple_dt(elem.get("endDate"))
            if end is None or to_utc(end) < cutoff:
                continue
            state.workouts.append(parse_workout_element(elem, data_dir))
            continue

        hk_type = elem.get("type") or ""
        start = parse_apple_dt(elem.get("startDate"))
        end = parse_apple_dt(elem.get("endDate"))
        if start is None or end is None:
            continue
        meta: Dict[str, str] = {}
        hrv_beats: List[Tuple[float, datetime]] = []
        for child in elem:
            if child.tag == "MetadataEntry":
                k, v = child.get("key"), child.get("value")
                if k:
                    meta[k] = v or ""
            elif child.tag == "HeartRateVariabilityMetadataList":
                for bpm_el in child:
                    if bpm_el.tag != "InstantaneousBeatsPerMinute":
                        continue
                    t = parse_beat_time(start, bpm_el.get("time"))
                    try:
                        bpm = float(bpm_el.get("bpm") or "0")
                    except ValueError:
                        continue
                    if t and bpm > 0:
                        hrv_beats.append((bpm, t))
        ingest_record(
            state, hk_type, start, end, elem.get("value"), cutoff, dedup,
            meta=meta, hrv_beats=hrv_beats or None,
        )


def load_from_cda(path: Path, cutoff: datetime, state: ParsedHealthData, dedup: bool) -> None:
    birth, sex = parse_cda_profile(path)
    if birth and not state.birth_date:
        state.birth_date = birth
    if sex and not state.sex:
        state.sex = sex
    for hk_type, start, end, val_raw in iter_cda_observations(path):
        ingest_record(state, hk_type, start, end, val_raw, cutoff, dedup)


def load_health_data(
    source: str,
    healthkit_path: Optional[Path],
    cda_path: Optional[Path],
    data_dir: Path,
    cutoff: datetime,
) -> ParsedHealthData:
    state = ParsedHealthData()
    use_hk = source in ("healthkit", "both")
    use_cda = source in ("cda", "both")
    dedup = source == "both"

    if use_hk and healthkit_path and healthkit_path.is_file():
        load_from_healthkit(healthkit_path, data_dir, cutoff, state, dedup)
        state.sources_used.append(f"HealthKit: {healthkit_path.name}")
    if use_cda and cda_path and cda_path.is_file():
        load_from_cda(cda_path, cutoff, state, dedup)
        state.sources_used.append(f"CDA: {cda_path.name}")
    return state


def parse_apple_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S %z")


def parse_beat_time(record_start: datetime, time_str: Optional[str]) -> Optional[datetime]:
    """InstantaneousBeatsPerMinute time — только HH:MM:SS,ms относительно даты записи."""
    if not time_str:
        return None
    normalized = time_str.strip().replace(",", ".")
    for fmt in ("%H:%M:%S.%f", "%H:%M:%S"):
        try:
            t = datetime.strptime(normalized, fmt).time()
            return record_start.replace(
                hour=t.hour, minute=t.minute, second=t.second, microsecond=t.microsecond,
            )
        except ValueError:
            continue
    return None


def parse_apple_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    return date.fromisoformat(s[:10])


def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def age_years(birth: date, on: Optional[date] = None) -> int:
    today = on or date.today()
    y = today.year - birth.year
    if (today.month, today.day) < (birth.month, birth.day):
        y -= 1
    return y


ASLEEP_VALUES = frozenset(
    (
        "HKCategoryValueSleepAnalysisAsleepCore",
        "HKCategoryValueSleepAnalysisAsleepREM",
        "HKCategoryValueSleepAnalysisAsleepDeep",
        "HKCategoryValueSleepAnalysisAsleepUnspecified",
    )
)


@dataclass
class SleepNight:
    date_key: date
    asleep_h: float = 0.0
    awake_h: float = 0.0
    inbed_h: float = 0.0
    stages_h: Dict[str, float] = field(default_factory=lambda: defaultdict(float))


@dataclass
class EcgRecord:
    path: str
    recorded: Optional[datetime]
    classification: str
    device: str = ""
    symptoms: str = ""


@dataclass
class WorkoutSummary:
    activity_type: str
    start: datetime
    end: datetime
    duration_min: float
    distance_km: Optional[float]
    hr_avg: Optional[float]
    hr_max: Optional[float]
    active_kcal: Optional[float]
    route_path: Optional[str]
    route_distance_km: Optional[float] = None
    route_avg_speed_kmh: Optional[float] = None
    route_elev_gain_m: Optional[float] = None


def night_key_from_segment_end(end_local: datetime) -> date:
    return end_local.date()


def iter_export_events(path: Path) -> Iterator[Tuple[str, ET.Element]]:
    for _, elem in ET.iterparse(path, events=("end",)):
        if elem.tag in ("Record", "Workout", "Me"):
            yield elem.tag, elem
            elem.clear()
        # MetadataEntry / InstantaneousBeatsPerMinute не clear() — иначе списки HRV пустые


def parse_ecg_csv(path: Path) -> Optional[EcgRecord]:
    meta: Dict[str, str] = {}
    try:
        with path.open(encoding="utf-8", newline="") as f:
            for _ in range(20):
                line = f.readline()
                if not line.strip():
                    break
                if "," not in line:
                    continue
                key, val = line.split(",", 1)
                meta[key.strip()] = val.strip().strip('"')
    except OSError:
        return None
    rec_dt = parse_apple_dt(meta.get("Recorded Date"))
    return EcgRecord(
        path=path.name,
        recorded=rec_dt,
        classification=meta.get("Classification", "Unknown"),
        device=meta.get("Device", ""),
        symptoms=meta.get("Symptoms", ""),
    )


def load_ecg_folder(folder: Path, cutoff: datetime) -> List[EcgRecord]:
    out: List[EcgRecord] = []
    if not folder.is_dir():
        return out
    for p in sorted(folder.glob("*.csv")):
        rec = parse_ecg_csv(p)
        if rec is None:
            continue
        if rec.recorded and to_utc(rec.recorded) < cutoff:
            continue
        out.append(rec)
    return out


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def parse_gpx_route(path: Path) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    """distance_km, duration_min, avg_speed_kmh, elev_gain_m"""
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return None, None, None, None
    ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
    pts = root.findall(".//gpx:trkpt", ns) or root.findall(".//trkpt")
    if len(pts) < 2:
        return None, None, None, None
    dist = 0.0
    elev_gain = 0.0
    times: List[datetime] = []
    prev_ele: Optional[float] = None
    prev_lat = prev_lon = None
    for pt in pts:
        lat = float(pt.get("lat", "0"))
        lon = float(pt.get("lon", "0"))
        ele_el = pt.find("gpx:ele", ns) or pt.find("ele")
        ele = float(ele_el.text) if ele_el is not None and ele_el.text else None
        time_el = pt.find("gpx:time", ns) or pt.find("time")
        if time_el is not None and time_el.text:
            t = datetime.fromisoformat(time_el.text.replace("Z", "+00:00"))
            times.append(t)
        if prev_lat is not None:
            dist += haversine_km(prev_lat, prev_lon, lat, lon)
        if ele is not None and prev_ele is not None and ele > prev_ele:
            elev_gain += ele - prev_ele
        prev_lat, prev_lon = lat, lon
        if ele is not None:
            prev_ele = ele
    duration_min = None
    avg_speed = None
    if len(times) >= 2:
        duration_min = (times[-1] - times[0]).total_seconds() / 60.0
        if duration_min > 0:
            avg_speed = dist / (duration_min / 60.0)
    return dist, duration_min, avg_speed, elev_gain


def parse_gpx_latlon(path: Path) -> List[Tuple[float, float]]:
    """Список (lat, lon) для карты."""
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return []
    ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
    pts = root.findall(".//gpx:trkpt", ns) or root.findall(".//trkpt")
    return [(float(p.get("lat", "0")), float(p.get("lon", "0"))) for p in pts if p.get("lat") and p.get("lon")]


def gpx_filename_to_path(data_dir: Path, ref_path: str) -> Path:
    name = ref_path.strip("/").replace("workout-routes/", "")
    return data_dir / "workout-routes" / name


def workout_label(activity_type: str) -> str:
    return WORKOUT_TYPE_LABELS.get(activity_type, activity_type.replace("HKWorkoutActivityType", ""))


def quartiles(sorted_vals: Sequence[float]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    xs = list(sorted_vals)
    if len(xs) < 2:
        if not xs:
            return None, None, None
        v = xs[0]
        return v, v, v
    q1, q2, q3 = statistics.quantiles(xs, n=4, method="inclusive")  # type: ignore[arg-type]
    return float(q1), float(q2), float(q3)


def svg_polyline_normalized(
    points: Sequence[Tuple[float, float]],
    width: float = 900,
    height: float = 220,
    padding: float = 28,
    stroke: str = "#2563eb",
    fill: str = "rgba(37,99,235,0.12)",
) -> str:
    if len(points) < 2:
        return f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg"></svg>'
    ys = [p[1] for p in points]
    y_min, y_max = min(ys), max(ys)
    if y_max == y_min:
        y_max = y_min + 1e-9
    x0, x1 = padding, width - padding
    y_b, y_t = height - padding, padding
    n = len(points)
    coords: List[Tuple[float, float]] = []
    for i, (_, y) in enumerate(points):
        tx = x0 + (i / (n - 1)) * (x1 - x0)
        ty = y_t + (1 - (y - y_min) / (y_max - y_min)) * (y_b - y_t)
        coords.append((tx, ty))
    d_path = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    area = f"{d_path} L {coords[-1][0]:.1f},{y_b:.1f} L {coords[0][0]:.1f},{y_b:.1f} Z"
    return f"""<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="chart">
  <rect x="0" y="0" width="{width}" height="{height}" fill="#fafafa" stroke="#e5e7eb"/>
  <path d="{area}" fill="{fill}" stroke="none"/>
  <path d="{d_path}" fill="none" stroke="{stroke}" stroke-width="2"/>
</svg>"""


def status_badge(status: str) -> str:
    cls = {"ok": "badge-ok", "warn": "badge-warn", "alert": "badge-alert", "info": "badge-info", "na": "badge-na"}
    labels = {"ok": "в норме", "warn": "внимание", "alert": "срочно", "info": "инфо", "na": "—"}
    return f'<span class="{cls.get(status, "badge-na")}">{labels.get(status, status)}</span>'


def render_clinical_table(checks: List[RefCheck], refs: Dict[str, ClinicalRef]) -> str:
    rows = []
    for c in checks:
        ref = refs.get(c.ref_key)
        if not ref:
            continue
        src = f'<a href="{html.escape(ref.source_url, quote=True)}" rel="noopener">{html.escape(ref.source)}</a>'
        rows.append(
            "<tr>"
            f"<td>{html.escape(ref.metric)}</td>"
            f"<td>{html.escape(c.your_value)}</td>"
            f"<td>{html.escape(ref.normal_text)}</td>"
            f"<td>{status_badge(c.status)}</td>"
            f"<td>{html.escape(c.note)}</td>"
            f"<td>{src}</td>"
            "</tr>"
        )
    if not rows:
        return "<p class=\"muted\">Недостаточно данных для сравнения с ориентирами.</p>"
    return (
        "<table class=\"clinical\"><thead><tr>"
        "<th>Показатель</th><th>Ваше значение</th><th>Клинический ориентир</th>"
        "<th>Статус</th><th>Комментарий</th><th>Источник</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def parse_workout_element(elem: ET.Element, data_dir: Path) -> WorkoutSummary:
    start = parse_apple_dt(elem.get("startDate"))
    end = parse_apple_dt(elem.get("endDate"))
    dur = float(elem.get("duration") or 0)
    dur_unit = elem.get("durationUnit") or "min"
    duration_min = dur if dur_unit == "min" else dur / 60.0

    distance_km = hr_avg = hr_max = active_kcal = None
    route_path: Optional[str] = None

    for child in elem:
        if child.tag == "WorkoutStatistics":
            stype = child.get("type") or ""
            if stype == "HKQuantityTypeIdentifierDistanceWalkingRunning" and child.get("sum"):
                distance_km = float(child.get("sum"))
            elif stype == "HKQuantityTypeIdentifierHeartRate":
                if child.get("average"):
                    hr_avg = float(child.get("average"))
                if child.get("maximum"):
                    hr_max = float(child.get("maximum"))
            elif stype == "HKQuantityTypeIdentifierActiveEnergyBurned" and child.get("sum"):
                active_kcal = float(child.get("sum"))
        elif child.tag == "WorkoutRoute":
            for sub in child:
                if sub.tag == "FileReference" and sub.get("path"):
                    route_path = sub.get("path")

    route_dist = route_speed = route_elev = None
    if route_path:
        gpx = gpx_filename_to_path(data_dir, route_path)
        if gpx.is_file():
            route_dist, _, route_speed, route_elev = parse_gpx_route(gpx)

    assert start and end
    return WorkoutSummary(
        activity_type=elem.get("workoutActivityType") or "",
        start=start,
        end=end,
        duration_min=duration_min,
        distance_km=distance_km,
        hr_avg=hr_avg,
        hr_max=hr_max,
        active_kcal=active_kcal,
        route_path=route_path,
        route_distance_km=route_dist,
        route_avg_speed_kmh=route_speed,
        route_elev_gain_m=route_elev,
    )


def build_report(
    out_path: Path,
    lookback_days: int,
    data_dir: Path,
    source: str,
    healthkit_path: Optional[Path],
    cda_path: Optional[Path],
) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    parsed = load_health_data(source, healthkit_path, cda_path, data_dir, cutoff)
    birth_date = parsed.birth_date
    sex = parsed.sex
    hrv_points = parsed.hrv_points
    rhr_points = parsed.rhr_points
    spo2_timed = parsed.spo2_timed
    rr_points = parsed.rr_points
    bmi_points = parsed.bmi_points
    nights = parsed.nights
    workouts = parsed.workouts
    sources_used = parsed.sources_used
    cda_only = source == "cda"

    ecg_records = load_ecg_folder(data_dir / "electrocardiograms", cutoff)

    # Orphan GPX (без привязки к workout в окне) — сканируем папку
    orphan_routes: List[Tuple[str, float, float, float]] = []
    routes_dir = data_dir / "workout-routes"
    linked_gpx = {w.route_path for w in workouts if w.route_path}
    if routes_dir.is_dir():
        for gpx in sorted(routes_dir.glob("*.gpx")):
            ref = f"/workout-routes/{gpx.name}"
            if ref in linked_gpx:
                continue
            dist, dur, spd, elev = parse_gpx_route(gpx)
            if dist is not None:
                orphan_routes.append((gpx.name, dist, spd or 0.0, elev or 0.0))

    # ----- Агрегаты
    nights_sorted = sorted(nights.items(), key=lambda kv: kv[0])
    asleep_hours_series = [n.asleep_h for _, n in nights_sorted]
    awake_min_series = [n.awake_h * 60 for _, n in nights_sorted]
    avg_asleep = statistics.mean(asleep_hours_series) if asleep_hours_series else None

    by_day_hrv: Dict[date, List[float]] = defaultdict(list)
    for d, v in hrv_points:
        by_day_hrv[d].append(v)
    hrv_daily = sorted(((d, statistics.mean(vs)) for d, vs in by_day_hrv.items()), key=lambda x: x[0])
    hrv_vals_sorted = sorted(v for _, v in hrv_daily)
    low_thr, med_hrv, _ = quartiles(hrv_vals_sorted) if hrv_vals_sorted else (None, None, None)

    by_day_rmssd: Dict[date, List[float]] = defaultdict(list)
    for d, v in parsed.rmssd_points:
        by_day_rmssd[d].append(v)
    rmssd_daily = sorted(((d, statistics.mean(vs)) for d, vs in by_day_rmssd.items()), key=lambda x: x[0])
    med_rmssd = statistics.median([v for _, v in rmssd_daily]) if rmssd_daily else None

    by_day_rhr: Dict[date, List[float]] = defaultdict(list)
    for d, v in rhr_points:
        by_day_rhr[d].append(v)
    rhr_daily = sorted(((d, statistics.mean(vs)) for d, vs in by_day_rhr.items()), key=lambda x: x[0])
    med_rhr = statistics.median([v for _, v in rhr_daily]) if rhr_daily else None

    from apple_health.analytics import (
        build_insights,
        classify_hr_recovery,
        classify_vo2,
        mean_by_day,
        sleep_hrv_correlation,
        split_spo2_day_night,
        sum_by_day,
        weekday_weekend_sleep,
        workout_hrv_correlation,
        zscore_outlier_days,
    )

    steps_daily = sum_by_day(parsed.step_points)
    distance_daily = sum_by_day(parsed.distance_points)
    flights_daily = sum_by_day(parsed.flights_points)
    vo2_daily = mean_by_day(parsed.vo2_points)
    hr_recovery_daily = mean_by_day(parsed.hr_recovery_points)
    body_mass_daily = mean_by_day(parsed.body_mass_points)
    body_fat_daily = mean_by_day(parsed.body_fat_points)
    lean_mass_daily = mean_by_day(parsed.lean_mass_points)
    asymmetry_daily = mean_by_day(parsed.asymmetry_points)
    steadiness_daily = mean_by_day(parsed.steadiness_points)
    mindful_daily = sum_by_day(parsed.mindful_minutes)
    spo2_day_daily, spo2_night_daily = split_spo2_day_night(spo2_timed, parsed.sleep_intervals)

    latest_spo2 = spo2_timed[-1][1] if spo2_timed else None
    med_spo2 = statistics.median([v for _, v in spo2_timed]) if spo2_timed else None
    med_spo2_night = statistics.median([v for _, v in spo2_night_daily]) if spo2_night_daily else None
    latest_vo2 = vo2_daily[-1][1] if vo2_daily else None
    med_hr_recovery = statistics.median([v for _, v in hr_recovery_daily]) if hr_recovery_daily else None
    avg_steps = statistics.mean([v for _, v in steps_daily]) if steps_daily else None
    avg_distance = statistics.mean([v for _, v in distance_daily]) if distance_daily else None
    mindful_total = sum(v for _, v in mindful_daily)
    asymmetry_med = statistics.median([v for _, v in asymmetry_daily]) if asymmetry_daily else None
    steadiness_med = statistics.median([v for _, v in steadiness_daily]) if steadiness_daily else None

    user_age_for_vo2 = age_years(birth_date) if birth_date else None
    sex_male = (sex or "").endswith("Male")
    vo2_status, vo2_label = (
        classify_vo2(latest_vo2, user_age_for_vo2, sex_male)
        if latest_vo2 is not None and user_age_for_vo2 is not None
        else (None, None)
    )

    sleep_hrv_r = sleep_hrv_correlation(nights_sorted, hrv_daily) if nights_sorted else None
    workout_hrv_r = workout_hrv_correlation(workouts, hrv_daily) if workouts else None
    ww_sleep = weekday_weekend_sleep(nights_sorted)
    hrv_outliers = zscore_outlier_days(hrv_daily, low_is_bad=True)
    sleep_outliers = zscore_outlier_days([(d, n.asleep_h) for d, n in nights_sorted if n.asleep_h > 0], low_is_bad=True)

    insights = build_insights(
        avg_asleep=avg_asleep,
        med_hrv=med_hrv,
        sleep_hrv_r=sleep_hrv_r,
        workout_hrv_r=workout_hrv_r,
        ww=ww_sleep,
        vo2_latest=latest_vo2,
        vo2_label=vo2_label,
        avg_steps=avg_steps,
        avg_distance_km=avg_distance,
        spo2_night_med=med_spo2_night,
        mindful_total_min=mindful_total,
        asymmetry_med=asymmetry_med,
        steadiness_med=steadiness_med,
        hr_recovery_med=med_hr_recovery,
    )

    workout_min_by_day: Dict[date, float] = defaultdict(float)
    for w in workouts:
        workout_min_by_day[w.start.date()] += w.duration_min

    from apple_health.stress_assessment import compute_stress_assessment

    stress_report = compute_stress_assessment(
        nights_sorted=nights_sorted,
        hrv_daily=hrv_daily,
        rhr_daily=rhr_daily,
        spo2_night_daily=spo2_night_daily,
        workout_minutes_by_day=dict(workout_min_by_day),
    )
    from apple_health.mental_health import summarize_assessments, summarize_state_of_mind

    mental_lines = summarize_state_of_mind(parsed.state_of_mind) + summarize_assessments(parsed.scored_assessments)
    if mental_lines:
        insights = mental_lines + insights
    elif not parsed.state_of_mind and not parsed.scored_assessments:
        pass  # notice только в секции «Самочувствие», не дублируем в insights

    insights = [x for x in stress_report.clinical_narrative if x.strip()] + insights

    if rmssd_daily and med_rmssd is not None:
        insights.insert(0, f"RMSSD (beat-to-beat): медиана ~{med_rmssd:.0f} мс за {len(rmssd_daily)} измерений — точнее SDNN для recovery.")

    gpx_paths: List[Tuple[str, Path]] = []
    for w in workouts:
        if w.route_path:
            gp = gpx_filename_to_path(data_dir, w.route_path)
            if gp.is_file():
                gpx_paths.append((w.start.strftime("%Y-%m-%d"), gp))

    latest_rr = statistics.mean(v for _, v in rr_points[-7:]) if rr_points else None
    latest_bmi = bmi_points[-1][1] if bmi_points else None

    # Активность по неделям (ходьба и др.)
    weekly_minutes: Dict[Tuple[int, int], float] = defaultdict(float)
    for w in workouts:
        if w.duration_min <= 0:
            continue
        iso = w.start.isocalendar()
        weekly_minutes[(iso.year, iso.week)] += w.duration_min
    recent_weeks = sorted(weekly_minutes.items())[-8:]
    weekly_chart = sorted((f"{y}-W{w:02d}", m) for (y, w), m in weekly_minutes.items())
    avg_weekly_min = statistics.mean([m for _, m in recent_weeks]) if recent_weeks else None

    spo2_daily = spo2_day_daily

    total_workout_km = sum(w.distance_km or w.route_distance_km or 0 for w in workouts)
    workouts_with_routes = [w for w in workouts if w.route_path]

    # ----- Клинические сравнения
    clinical_checks: List[RefCheck] = []

    if avg_asleep is not None:
        ref = CLINICAL_REFS["sleep_hours_adult"]
        st = "ok" if avg_asleep >= 7 else "warn"
        clinical_checks.append(
            RefCheck(
                "sleep_hours_adult",
                f"{avg_asleep:.2f} {ref.unit}",
                st,
                "Среднее за период по стадиям сна Apple Watch",
            )
        )

    if med_rhr is not None:
        ref = CLINICAL_REFS["resting_hr_adult"]
        st = "ok"
        note = "Медиана за период"
        if med_rhr < 60:
            st = "info"
            note = "Ниже 60 — часто норма для молодых/тренированных; при симптомах — к врачу"
        elif med_rhr > 100:
            st = "warn"
            note = "Выше 100 — ориентир AHA для покоя; при стойком повышении — к врачу"
        clinical_checks.append(
            RefCheck("resting_hr_adult", f"{med_rhr:.0f} {ref.unit}", st, note)
        )

    if med_spo2_night is not None:
        ref = CLINICAL_REFS["spo2_sea_level"]
        st = "ok" if med_spo2_night >= 95 else ("alert" if med_spo2_night <= 92 else "warn")
        clinical_checks.append(
            RefCheck("spo2_sea_level", f"{med_spo2_night:.1f} % (ночь)", st, "Медиана SpO₂ во время сна")
        )

    if latest_vo2 is not None and user_age_for_vo2 is not None and vo2_label:
        st = vo2_status or "info"
        clinical_checks.append(
            RefCheck("vo2_max", f"{latest_vo2:.1f} мл/кг/мин", st, vo2_label)
        )

    if med_hr_recovery is not None:
        hrr_st, hrr_note = classify_hr_recovery(med_hr_recovery)
        clinical_checks.append(
            RefCheck("hr_recovery", f"{med_hr_recovery:.0f} уд/мин", hrr_st, hrr_note)
        )

    if avg_steps is not None:
        clinical_checks.append(
            RefCheck("daily_steps", f"{avg_steps:,.0f} шагов/день", "info", "Среднее за период (ориентир ~7000–10000)")
        )

    if latest_rr is not None:
        ref = CLINICAL_REFS["respiratory_rate_adult"]
        st = "ok" if 12 <= latest_rr <= 20 else "warn"
        clinical_checks.append(
            RefCheck("respiratory_rate_adult", f"{latest_rr:.1f} {ref.unit}", st, "Среднее за последние записи")
        )

    if latest_bmi is not None:
        ref = CLINICAL_REFS["bmi_adult"]
        st, bmi_note = bmi_category(latest_bmi)
        clinical_checks.append(
            RefCheck("bmi_adult", f"{latest_bmi:.1f} {ref.unit}", st, bmi_note)
        )

    if avg_weekly_min is not None:
        ref = CLINICAL_REFS["weekly_moderate_activity"]
        st = "ok" if avg_weekly_min >= 150 else "warn"
        clinical_checks.append(
            RefCheck(
                "weekly_moderate_activity",
                f"{avg_weekly_min:.0f} {ref.unit}",
                st,
                f"Среднее за последние {len(recent_weeks)} нед. (все типы тренировок в export.xml)",
            )
        )

    for rec in ecg_records:
        if rec.classification == "Sinus Rhythm":
            clinical_checks.append(
                RefCheck("ecg_sinus", rec.classification, "ok", f"Запись {rec.path}")
            )
        elif rec.classification == "Atrial Fibrillation":
            clinical_checks.append(
                RefCheck("ecg_afib", rec.classification, "alert", f"Запись {rec.path} — обратитесь к врачу")
            )
        elif rec.classification in ("High Heart Rate", "Low Heart Rate", "Inconclusive", "Poor Recording"):
            clinical_checks.append(
                RefCheck(
                    "ecg_sinus",
                    rec.classification,
                    "warn",
                    f"Запись {rec.path} — не «Sinus Rhythm», уточните у врача при симптомах",
                )
            )

    def esc(x: object) -> str:
        return html.escape(str(x), quote=True)

    def numbered_series_daily(series: Sequence[Tuple[date, float]]) -> Tuple[List[Tuple[float, float]], List[str]]:
        pts: List[Tuple[float, float]] = []
        labels: List[str] = []
        for i, (d, v) in enumerate(series):
            pts.append((float(i), v))
            labels.append(d.isoformat())
        return pts, labels

    hrv_pts, hrv_labels = numbered_series_daily(hrv_daily)
    asleep_pts = [(float(i), h) for i, h in enumerate(asleep_hours_series)]
    awake_pts = [(float(i), m) for i, m in enumerate(awake_min_series)]

    user_age = age_years(birth_date) if birth_date else None
    sex_label = sex.replace("HKBiologicalSex", "") if sex else ""

    try:
        from apple_health.dashboard import DashboardInput, render_rich_report

        ecg_summary = Counter(r.classification for r in ecg_records).most_common()
        doc = render_rich_report(
            DashboardInput(
                lookback_days=lookback_days,
                sources_used=sources_used,
                source=source,
                cda_only=cda_only,
                birth_date=birth_date,
                user_age=user_age,
                sex_label=sex_label,
                avg_asleep=avg_asleep,
                med_hrv=med_hrv,
                low_hrv_q=low_thr,
                med_rhr=med_rhr,
                med_spo2=med_spo2,
                latest_bmi=latest_bmi,
                avg_weekly_min=avg_weekly_min,
                total_workout_km=total_workout_km,
                nights_count=len(nights),
                workouts_count=len(workouts),
                routes_count=len(workouts_with_routes),
                ecg_count=len(ecg_records),
                nights_sorted=nights_sorted,
                hrv_daily=hrv_daily,
                rhr_daily=rhr_daily,
                spo2_daily=spo2_daily,
                spo2_night_daily=spo2_night_daily,
                weekly_minutes=weekly_chart,
                steps_daily=steps_daily,
                distance_daily=distance_daily,
                flights_daily=flights_daily,
                vo2_daily=vo2_daily,
                hr_recovery_daily=hr_recovery_daily,
                body_mass_daily=body_mass_daily,
                body_fat_daily=body_fat_daily,
                lean_mass_daily=lean_mass_daily,
                asymmetry_daily=asymmetry_daily,
                steadiness_daily=steadiness_daily,
                mindful_daily=mindful_daily,
                latest_vo2=latest_vo2,
                avg_steps=avg_steps,
                insights=insights,
                sleep_hrv_r=sleep_hrv_r,
                workout_hrv_r=workout_hrv_r,
                hrv_outliers=hrv_outliers,
                sleep_outliers=sleep_outliers,
                weekday_weekend_sleep=ww_sleep,
                gpx_paths=gpx_paths,
                parse_gpx_latlon_fn=parse_gpx_latlon,
                stress_assessment=stress_report,
                rmssd_daily=rmssd_daily,
                med_rmssd=med_rmssd,
                state_of_mind=parsed.state_of_mind,
                scored_assessments=parsed.scored_assessments,
                clinical_checks=clinical_checks,
                clinical_refs=CLINICAL_REFS,
                ecg_records=ecg_records,
                ecg_summary=ecg_summary,
                workouts=workouts,
                workout_label_fn=workout_label,
                orphan_routes=orphan_routes,
                render_clinical_table_fn=render_clinical_table,
                esc_fn=esc,
            )
        )
        out_path.write_text(doc, encoding="utf-8")
        return
    except ImportError:
        print(
            "Подсказка: pip install -r requirements.txt — для интерактивного дашборда (Plotly).",
            file=sys.stderr,
        )

    sections: List[str] = []

    sections.append("<h2>Обзор за период</h2>")
    profile_bits = []
    if birth_date:
        profile_bits.append(f"дата рождения: {birth_date.isoformat()}")
    if user_age is not None:
        profile_bits.append(f"возраст: {user_age} лет")
    if sex:
        profile_bits.append(f"пол: {esc(sex.replace('HKBiologicalSex', ''))}")
    sources_line = ", ".join(esc(s) for s in sources_used) if sources_used else "—"
    sections.append(
        "<ul>"
        f"<li>Источники XML: {sources_line}; также ECG и GPX-маршруты</li>"
        f"<li>Окно: последние <strong>{lookback_days}</strong> дней</li>"
        + (f"<li>Профиль: {'; '.join(profile_bits)}</li>" if profile_bits else "")
        + f"<li>Ночей с данными сна: <strong>{len(nights)}</strong></li>"
        + f"<li>Тренировок: <strong>{len(workouts)}</strong> (с GPS-маршрутом: {len(workouts_with_routes)})</li>"
        + f"<li>Записей ЭКГ: <strong>{len(ecg_records)}</strong></li>"
        + f"<li>Дистанция тренировок (сумма): <strong>{total_workout_km:.2f} км</strong></li>"
        "</ul>"
    )
    if cda_only:
        sections.append(
            "<p class=\"warn\"><strong>Режим CDA:</strong> в export_cda.xml обычно только часть показателей "
            "(пульс, SpO₂, дыхание, ИМТ). Сон, HRV, пульс в покое и тренировки — из <code>export.xml</code>. "
            "Для полного отчёта используйте <code>--source healthkit</code> или <code>--source both</code>.</p>"
        )
    elif source == "both":
        sections.append(
            "<p class=\"muted\">Режим <code>both</code>: данные из HealthKit и CDA объединены без дубликатов. "
            "Тренировки и GPS — только из export.xml.</p>"
        )

    sections.append("<h2>Сравнение с клиническими ориентирами</h2>")
    sections.append(
        "<p>Ниже — <strong>публичные медицинские ориентиры</strong> (CDC, WHO, AHA, Apple для ЭКГ). "
        "Они не заменяют осмотр врача и могут не учитывать ваши диагнозы, лекарства и образ жизни. "
        "HRV (SDNN) намеренно <em>не</em> сравнивается: единой «нормы» для бытовых часов нет.</p>"
    )
    sections.append(render_clinical_table(clinical_checks, CLINICAL_REFS))

    # ECG section
    sections.append("<h2>Электрокардиограммы (Apple Watch)</h2>")
    sections.append(
        "<p>Классификация даётся алгоритмом Apple, не врачом. "
        f"Ориентир: <a href=\"{esc(CLINICAL_REFS['ecg_sinus'].source_url)}\">{esc(CLINICAL_REFS['ecg_sinus'].source)}</a>.</p>"
    )
    if ecg_records:
        ecg_ctr = Counter(r.classification for r in ecg_records)
        sections.append("<ul>" + "".join(f"<li>{esc(k)}: <strong>{v}</strong></li>" for k, v in ecg_ctr.most_common()) + "</ul>")
        rows = []
        for r in reversed(ecg_records[-20:]):
            dt = r.recorded.strftime("%Y-%m-%d %H:%M") if r.recorded else "—"
            badge = "badge-ok" if r.classification == "Sinus Rhythm" else (
                "badge-alert" if r.classification == "Atrial Fibrillation" else "badge-warn"
            )
            rows.append(
                f"<tr><td>{esc(dt)}</td><td><span class=\"{badge}\">{esc(r.classification)}</span></td>"
                f"<td>{esc(r.device)}</td><td>{esc(r.symptoms or '—')}</td><td><code>{esc(r.path)}</code></td></tr>"
            )
        sections.append(
            "<h3>Последние записи</h3>"
            "<table><thead><tr><th>Дата</th><th>Классификация</th><th>Устройство</th><th>Симптомы</th><th>Файл</th></tr></thead>"
            "<tbody>" + "".join(rows) + "</tbody></table>"
        )
        afib = [r for r in ecg_records if r.classification == "Atrial Fibrillation"]
        if afib:
            sections.append(
                f"<p class=\"alert-box\"><strong>Обнаружено {len(afib)} записей с Atrial Fibrillation.</strong> "
                "По рекомендациям Apple и клинической практике это повод обратиться к кардиологу, "
                "даже если самочувствие нормальное.</p>"
            )
    else:
        sections.append("<p class=\"muted\">Нет записей ЭКГ в выбранном окне (папка electrocardiograms/).</p>")

    # Workouts + routes
    sections.append("<h2>Тренировки и маршруты (GPX)</h2>")
    ref_act = CLINICAL_REFS["weekly_moderate_activity"]
    sections.append(
        f"<p>WHO рекомендует взрослым <strong>{esc(ref_act.normal_text)}</strong> "
        f"(<a href=\"{esc(ref_act.source_url)}\">{esc(ref_act.source)}</a>). "
        "Ходьба из Apple Watch/Pacer учитывается как умеренная активность.</p>"
    )
    if workouts:
        type_ctr = Counter(workout_label(w.activity_type) for w in workouts)
        sections.append("<p>Типы: " + ", ".join(f"{esc(k)} — {v}" for k, v in type_ctr.most_common()) + "</p>")
        if recent_weeks:
            sections.append("<h3>Минуты активности по неделям</h3><ul>")
            for (y, w), mins in recent_weeks:
                mark = " ✓" if mins >= 150 else ""
                sections.append(f"<li>Неделя {y}-W{w:02d}: <strong>{mins:.0f} мин</strong>{mark}</li>")
            sections.append("</ul>")

        rows = []
        for w in reversed(workouts[-15:]):
            dist = w.distance_km or w.route_distance_km
            spd = w.route_avg_speed_kmh
            elev = w.route_elev_gain_m
            route_name = Path(w.route_path).name if w.route_path else "—"
            rows.append(
                "<tr>"
                f"<td>{esc(w.start.strftime('%Y-%m-%d %H:%M'))}</td>"
                f"<td>{esc(workout_label(w.activity_type))}</td>"
                f"<td>{esc(f'{w.duration_min:.0f}')}</td>"
                f"<td>{esc(f'{dist:.2f}' if dist else '—')}</td>"
                f"<td>{esc(f'{w.hr_avg:.0f}' if w.hr_avg else '—')}</td>"
                f"<td>{esc(f'{spd:.1f}' if spd else '—')}</td>"
                f"<td>{esc(f'{elev:.0f}' if elev else '—')}</td>"
                f"<td><code>{esc(route_name)}</code></td>"
                "</tr>"
            )
        sections.append(
            "<h3>Последние тренировки</h3>"
            "<table><thead><tr>"
            "<th>Начало</th><th>Тип</th><th>мин</th><th>км</th><th>ЧСС ср.</th>"
            "<th>км/ч (GPS)</th><th>↑м</th><th>GPX</th>"
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
        )
    else:
        sections.append("<p class=\"warn\">Нет тренировок в выбранном окне.</p>")

    if orphan_routes:
        sections.append(f"<h3>GPX без привязки к тренировке в XML ({len(orphan_routes)} файлов)</h3><ul>")
        for name, dist, spd, elev in orphan_routes[:10]:
            sections.append(f"<li><code>{esc(name)}</code>: {dist:.2f} км, {spd:.1f} км/ч, ↑{elev:.0f} м</li>")
        sections.append("</ul>")

    # Sleep
    sections.append("<h2>Сон</h2>")
    if avg_asleep is not None:
        sleep_ref = CLINICAL_REFS["sleep_hours_adult"]
        cmp = "ниже" if avg_asleep < 7 else "соответствует"
        sections.append(
            f"<p>Среднее ~<strong>{avg_asleep:.2f} ч</strong> — {cmp} ориентиру CDC (≥ 7 ч для взрослых 18–60).</p>"
        )
    if asleep_pts:
        sections.append(svg_polyline_normalized(asleep_pts, stroke="#0f766e", fill="rgba(15,118,110,0.12)"))
    tail = nights_sorted[-14:]
    rows = [
        f"<tr><td>{esc(d)}</td><td>{n.asleep_h:.2f}</td><td>{n.awake_h * 60:.0f}</td><td>{n.inbed_h:.2f}</td></tr>"
        for d, n in reversed(tail)
    ]
    sections.append(
        "<table><thead><tr><th>Дата</th><th>Сон (ч)</th><th>Awake (мин)</th><th>В кровати</th></tr></thead>"
        "<tbody>" + "".join(rows) + "</tbody></table>"
    )
    if awake_pts:
        sections.append("<h3>Бодрствование ночью (мин)</h3>")
        sections.append(svg_polyline_normalized(awake_pts, stroke="#b45309", fill="rgba(180,83,9,0.12)"))

    # HRV
    sections.append("<h2>HRV (SDNN) — только ваш тренд</h2>")
    sections.append("<p>Единой клинической «нормы» SDNN с потребительских часов нет; сравнение только с вашими прошлыми значениями.</p>")
    if med_hrv is not None:
        sections.append(f"<p>Медиана по дням: ~{med_hrv:.1f} мс; нижний квартиль ~{low_thr:.1f} мс.</p>")
    if hrv_pts:
        sections.append(svg_polyline_normalized(hrv_pts, stroke="#7c3aed", fill="rgba(124,58,237,0.12)"))

    # RHR
    sections.append("<h2>Пульс в покое</h2>")
    if med_rhr is not None:
        sections.append(f"<p>Медиана: ~{med_rhr:.0f} уд/мин (ориентир AHA: 60–100).</p>")
    if rhr_daily:
        rhr_pts, _ = numbered_series_daily(rhr_daily)
        sections.append(svg_polyline_normalized(rhr_pts, stroke="#dc2626", fill="rgba(220,38,38,0.10)"))

    disclaimer = (
        "<h2>Ограничение ответственности</h2>"
        "<p>Отчёт автоматический. Клинические ориентиры — обобщённые рекомендации для населения, "
        "не персональное заключение врача. ЭКГ Apple Watch не заменяет медицинскую ЭКГ. "
        "При симптомах (боль в груди, одышка, обмороки, стойкая аритмия) — обращайтесь в медицину.</p>"
    )

    doc = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Отчёт Apple Health</title>
<style>
  body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 24px auto 48px; max-width: 980px; line-height: 1.5; color: #111827; }}
  h1,h2,h3 {{ line-height: 1.25; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 14px; }}
  th, td {{ border: 1px solid #e5e7eb; padding: 8px 10px; text-align: left; vertical-align: top; }}
  thead {{ background: rgba(255,255,255,0.04); }}
  table.clinical {{ font-size: 13px; }}
  code {{ font-size: 0.92em; background: #f3f4f6; padding: 2px 6px; border-radius: 4px; }}
  .muted {{ color: #6b7280; }}
  .warn {{ background: #fffbeb; padding: 10px 12px; border: 1px solid #fcd34d; border-radius: 8px; }}
  .alert-box {{ background: #fef2f2; padding: 12px 14px; border: 1px solid #fca5a5; border-radius: 8px; }}
  svg {{ max-width: 100%; height: auto; display: block; margin: 12px 0; }}
  .badge-ok {{ background: #dcfce7; color: #166534; padding: 2px 8px; border-radius: 999px; font-size: 12px; }}
  .badge-warn {{ background: #fef9c3; color: #854d0e; padding: 2px 8px; border-radius: 999px; font-size: 12px; }}
  .badge-alert {{ background: #fee2e2; color: #991b1b; padding: 2px 8px; border-radius: 999px; font-size: 12px; }}
  .badge-info {{ background: #dbeafe; color: #1e40af; padding: 2px 8px; border-radius: 999px; font-size: 12px; }}
  .badge-na {{ background: #f3f4f6; color: #6b7280; padding: 2px 8px; border-radius: 999px; font-size: 12px; }}
</style>
</head>
<body>
<h1>Отчёт Apple Health: сон, ЭКГ, тренировки, ориентиры</h1>
{"".join(sections)}
{disclaimer}
</body>
</html>
"""
    out_path.write_text(doc, encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    from apple_health.paths import DEFAULT_DATA_DIR, DEFAULT_REPORT_PATH

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    p = argparse.ArgumentParser(description="HTML-отчёт Apple Health + ECG + GPX + клинические ориентиры")
    p.add_argument(
        "--source",
        choices=("healthkit", "cda", "both"),
        default="both",
        help="both = export.xml + export_cda.xml (по умолчанию); healthkit = только export.xml; cda = только export_cda.xml",
    )
    p.add_argument("--xml", type=Path, default=DEFAULT_DATA_DIR / "export.xml", help="HealthKit export.xml")
    p.add_argument(
        "--cda",
        type=Path,
        default=DEFAULT_DATA_DIR / "export_cda.xml",
        help="CDA export_cda.xml (клинический формат Apple)",
    )
    p.add_argument("-o", "--output", type=Path, default=DEFAULT_REPORT_PATH)
    p.add_argument("--days", type=int, default=365)
    p.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Папка с экспортом (export.xml, electrocardiograms/, workout-routes/). По умолчанию: data/",
    )
    args = p.parse_args(list(argv) if argv is not None else None)

    data_dir = args.data_dir
    hk_path = args.xml if args.source in ("healthkit", "both") else None
    cda_path = args.cda if args.source in ("cda", "both") else None

    missing: List[str] = []
    if args.source in ("healthkit", "both") and not args.xml.is_file():
        missing.append(str(args.xml))
    if args.source in ("cda", "both") and not args.cda.is_file():
        missing.append(str(args.cda))
    if missing:
        print("Не найдены файлы:", ", ".join(missing), file=sys.stderr)
        print(f"Положите экспорт Apple Health в папку: {DEFAULT_DATA_DIR.resolve()}", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)

    build_report(
        args.output,
        max(7, args.days),
        data_dir,
        args.source,
        hk_path,
        cda_path,
    )
    print(f"Готово: {args.output.resolve()}")
    print(f"Откройте {args.output.name} в браузере.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
