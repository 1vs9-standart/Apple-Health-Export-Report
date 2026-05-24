"""
Психическое здоровье и RMSSD из экспорта Apple Health.

State of Mind и PHQ-9/GAD-7 (Scored Assessment) часто ОТСУТСТВУЮТ в стандартном
export.xml — известное ограничение Apple (iOS 18+). Парсер готов, если типы появятся.
RMSSD вычисляется из InstantaneousBeatsPerMinute в HRV-записях Apple Watch.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass
class StateOfMindEntry:
    recorded: date
    kind: str
    valence: Optional[float]
    valence_class: str
    labels: List[str] = field(default_factory=list)
    associations: List[str] = field(default_factory=list)


@dataclass
class ScoredAssessmentEntry:
    recorded: date
    assessment_type: str
    score: Optional[float]
    risk: str
    answers: List[str] = field(default_factory=list)


VALENCE_RU = {
    "VeryUnpleasant": "очень неприятно",
    "Unpleasant": "неприятно",
    "SlightlyUnpleasant": "слегка неприятно",
    "Neutral": "нейтрально",
    "SlightlyPleasant": "слегка приятно",
    "Pleasant": "приятно",
    "VeryPleasant": "очень приятно",
}

RISK_RU = {
    "NoneToMinimal": "минимальный / нет",
    "Minimal": "минимальный",
    "Mild": "лёгкий",
    "Moderate": "умеренный",
    "ModeratelySevere": "умеренно тяжёлый",
    "Severe": "тяжёлый",
    "Low": "низкий",
    "High": "высокий",
}

STRESS_LABELS = {
    "stressed", "anxious", "overwhelmed", "worried", "scared", "hopeless",
    "frustrated", "angry", "lonely", "drained", "annoyed", "discouraged",
}


def compute_rmssd_ms(beats: Sequence[Tuple[float, datetime]]) -> Optional[float]:
    """RMSSD (мс) из списка (bpm, time)."""
    if len(beats) < 2:
        return None
    rr = [60000.0 / bpm for bpm, _ in sorted(beats, key=lambda x: x[1]) if bpm > 0]
    if len(rr) < 2:
        return None
    sq = [(rr[i + 1] - rr[i]) ** 2 for i in range(len(rr) - 1)]
    return math.sqrt(sum(sq) / len(sq))


def _split_csvish(val: str) -> List[str]:
    if not val:
        return []
    return [x.strip() for x in val.replace("|", ",").split(",") if x.strip()]


def parse_state_of_mind_from_record(
    hk_type: str,
    start: date,
    meta: Dict[str, str],
    value: Optional[str],
) -> Optional[StateOfMindEntry]:
    if "StateOfMind" not in hk_type and "stateofmind" not in hk_type.lower():
        return None
    valence: Optional[float] = None
    for key in ("HKStateOfMindValence", "Valence", "valence"):
        if key in meta:
            try:
                valence = float(meta[key])
            except ValueError:
                pass
    if valence is None and value:
        try:
            valence = float(value)
        except ValueError:
            pass
    kind = meta.get("HKStateOfMindKind") or meta.get("Kind") or meta.get("kind") or "Unknown"
    vclass = (
        meta.get("HKStateOfMindValenceClassification")
        or meta.get("ValenceClassification")
        or meta.get("valenceClassification")
        or ""
    )
    labels = _split_csvish(meta.get("HKStateOfMindLabels") or meta.get("Labels") or "")
    assoc = _split_csvish(meta.get("HKStateOfMindAssociations") or meta.get("Associations") or "")
    return StateOfMindEntry(start, kind, valence, vclass, labels, assoc)


def parse_scored_assessment_from_record(
    hk_type: str,
    start: date,
    meta: Dict[str, str],
    value: Optional[str],
) -> Optional[ScoredAssessmentEntry]:
    low = hk_type.lower()
    if not any(x in low for x in ("scoredassessment", "phq", "gad7", "gad-7", "anxiety", "depression")):
        if meta.get("HKAssessmentScore") is None and meta.get("Score") is None and meta.get("Risk") is None:
            return None
    score: Optional[float] = None
    for key in ("HKAssessmentScore", "Score", "score"):
        if key in meta:
            try:
                score = float(meta[key])
            except ValueError:
                pass
    if score is None and value:
        try:
            score = float(value)
        except ValueError:
            pass
    risk = meta.get("HKAssessmentRisk") or meta.get("Risk") or meta.get("risk") or ""
    answers = _split_csvish(meta.get("HKAssessmentAnswers") or meta.get("Answers") or "")
    atype = hk_type.replace("HKScoredAssessmentTypeIdentifier", "").replace("HKQuantityTypeIdentifier", "")
    return ScoredAssessmentEntry(start, atype or hk_type, score, risk, answers)


def assessment_display_name(atype: str) -> str:
    low = atype.lower()
    if "phq" in low:
        return "PHQ-9 (депрессия)"
    if "gad" in low:
        return "GAD-7 (тревога)"
    return atype


def summarize_state_of_mind(entries: Sequence[StateOfMindEntry]) -> List[str]:
    if not entries:
        return []
    lines: List[str] = []
    vals = [e.valence for e in entries if e.valence is not None]
    if vals:
        lines.append(
            f"State of Mind: {len(entries)} записей, средний valence {statistics.mean(vals):+.2f} "
            f"(-1 неприятно … +1 приятно)."
        )
    stress_hits = sum(
        1 for e in entries for lb in e.labels if lb.lower() in STRESS_LABELS or "stress" in lb.lower()
    )
    if stress_hits:
        lines.append(f"Метки стресса/тревоги встречались {stress_hits} раз.")
    recent = sorted(entries, key=lambda e: e.recorded)[-5:]
    for e in recent:
        vc = VALENCE_RU.get(e.valence_class, e.valence_class or "—")
        lbl = ", ".join(e.labels[:3]) or "—"
        lines.append(f"  {e.recorded}: {vc} (valence {e.valence:+.2f}) — {lbl}" if e.valence is not None else f"  {e.recorded}: {vc} — {lbl}")
    return lines


def summarize_assessments(entries: Sequence[ScoredAssessmentEntry]) -> List[str]:
    if not entries:
        return []
    lines: List[str] = []
    for e in sorted(entries, key=lambda x: x.recorded)[-8:]:
        name = assessment_display_name(e.assessment_type)
        risk_ru = RISK_RU.get(e.risk, e.risk or "—")
        score_s = f"{e.score:.0f}" if e.score is not None else "—"
        lines.append(f"{e.recorded} · {name}: score {score_s}, риск — {risk_ru}")
    return lines


def mental_health_empty_notice() -> str:
    return (
        "В вашем export.xml нет State of Mind и Scored Assessment (PHQ-9/GAD-7). "
        "Apple пока часто не включает их в стандартный XML-экспорт (iOS 18+). "
        "Если вы проходили опрос в «Здоровье», данные могут появиться в будущих версиях экспорта."
    )
