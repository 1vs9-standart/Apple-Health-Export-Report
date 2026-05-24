"""
Rich HTML dashboard: Plotly charts + modern layout.
Requires: pip install -r requirements.txt
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Tuple

import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Shared types imported at runtime from health_insights to avoid circular imports at module level


PALETTE = {
    "bg": "#0b1220",
    "surface": "#151d2e",
    "card": "#1a2332",
    "border": "#2a3548",
    "text": "#e8edf5",
    "muted": "#8b9cb3",
    "sleep": "#2dd4bf",
    "hrv": "#a78bfa",
    "rhr": "#fb7185",
    "activity": "#fbbf24",
    "spo2": "#38bdf8",
    "ok": "#4ade80",
    "warn": "#fbbf24",
    "alert": "#f87171",
}

PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, system-ui, sans-serif", color=PALETTE["text"], size=12),
    margin=dict(l=48, r=24, t=48, b=40),
    hovermode="x unified",
    hoverlabel=dict(
        bgcolor=PALETTE["card"],
        bordercolor=PALETTE["border"],
        font=dict(color=PALETTE["text"], size=13, family="Inter, system-ui, sans-serif"),
    ),
    legend=dict(
        bgcolor="rgba(26,35,50,0.92)",
        bordercolor=PALETTE["border"],
        borderwidth=1,
        font=dict(color=PALETTE["text"], size=11),
    ),
    xaxis=dict(
        showgrid=True,
        gridcolor="rgba(255,255,255,0.08)",
        zeroline=False,
        tickfont=dict(color=PALETTE["muted"], size=11),
        title_font=dict(color=PALETTE["text"]),
        linecolor=PALETTE["border"],
    ),
    yaxis=dict(
        showgrid=True,
        gridcolor="rgba(255,255,255,0.08)",
        zeroline=False,
        tickfont=dict(color=PALETTE["muted"], size=11),
        title_font=dict(color=PALETTE["text"]),
        linecolor=PALETTE["border"],
    ),
)


def _apply_plotly_theme(fig: go.Figure, title: Optional[str] = None, **extra_layout) -> go.Figure:
    layout = dict(PLOTLY_LAYOUT)
    if title:
        layout["title"] = dict(text=title, font=dict(size=16, color=PALETTE["text"]))
    layout.update(extra_layout)
    fig.update_layout(**layout)
    fig.update_xaxes(
        tickfont=dict(color=PALETTE["muted"], size=11),
        title_font=dict(color=PALETTE["text"]),
        linecolor=PALETTE["border"],
    )
    fig.update_yaxes(
        tickfont=dict(color=PALETTE["muted"], size=11),
        title_font=dict(color=PALETTE["text"]),
        linecolor=PALETTE["border"],
    )
    return fig


@dataclass
class DashboardInput:
    lookback_days: int
    sources_used: List[str]
    source: str
    cda_only: bool
    birth_date: Optional[date]
    user_age: Optional[int]
    sex_label: str
    avg_asleep: Optional[float]
    med_hrv: Optional[float]
    low_hrv_q: Optional[float]
    med_rhr: Optional[float]
    med_spo2: Optional[float]
    latest_bmi: Optional[float]
    avg_weekly_min: Optional[float]
    total_workout_km: float
    nights_count: int
    workouts_count: int
    routes_count: int
    ecg_count: int
    nights_sorted: Sequence[Tuple[date, Any]]
    hrv_daily: Sequence[Tuple[date, float]]
    rhr_daily: Sequence[Tuple[date, float]]
    spo2_daily: Sequence[Tuple[date, float]]
    spo2_night_daily: Sequence[Tuple[date, float]]
    weekly_minutes: Sequence[Tuple[str, float]]
    steps_daily: Sequence[Tuple[date, float]]
    distance_daily: Sequence[Tuple[date, float]]
    flights_daily: Sequence[Tuple[date, float]]
    vo2_daily: Sequence[Tuple[date, float]]
    hr_recovery_daily: Sequence[Tuple[date, float]]
    body_mass_daily: Sequence[Tuple[date, float]]
    body_fat_daily: Sequence[Tuple[date, float]]
    lean_mass_daily: Sequence[Tuple[date, float]]
    asymmetry_daily: Sequence[Tuple[date, float]]
    steadiness_daily: Sequence[Tuple[date, float]]
    mindful_daily: Sequence[Tuple[date, float]]
    latest_vo2: Optional[float]
    avg_steps: Optional[float]
    insights: List[str]
    sleep_hrv_r: Optional[float]
    workout_hrv_r: Optional[float]
    hrv_outliers: Sequence[Tuple[date, float, str]]
    sleep_outliers: Sequence[Tuple[date, float, str]]
    weekday_weekend_sleep: Dict[str, float]
    gpx_paths: Sequence[Tuple[str, Any]]
    parse_gpx_latlon_fn: Any
    clinical_checks: Sequence[Any]
    clinical_refs: Dict[str, Any]
    ecg_records: Sequence[Any]
    ecg_summary: List[Tuple[str, int]]
    workouts: Sequence[Any]
    workout_label_fn: Any
    orphan_routes: Sequence[Tuple[str, float, float, float]]
    render_clinical_table_fn: Any
    esc_fn: Any
    stress_assessment: Any = None
    rmssd_daily: Sequence[Tuple[date, float]] = ()
    med_rmssd: Optional[float] = None
    state_of_mind: Sequence[Any] = ()
    scored_assessments: Sequence[Any] = ()


def _stress_recovery_chart(daily_recovery: Sequence[Tuple[date, float]], rolling_stress: Sequence[Tuple[date, float]]) -> Optional[go.Figure]:
    if not daily_recovery:
        return None
    xd, yd = _dates_vals(daily_recovery)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=xd, y=yd, name="Recovery (день)", line=dict(color=PALETTE["ok"], width=1.5), opacity=0.55,
        hovertemplate="%{x}<br>Recovery: %{y:.0f}/100<extra></extra>",
    ))
    if rolling_stress:
        xr, ys = _dates_vals(rolling_stress)
        rec_roll = [100.0 - s for _, s in zip(xr, ys)]
        fig.add_trace(go.Scatter(
            x=xr, y=rec_roll, name="Recovery 7-дн (из rolling stress)", line=dict(color=PALETTE["sleep"], width=3),
            hovertemplate="%{x}<br>Recovery: %{y:.0f}/100<extra></extra>",
        ))
    fig.add_hline(y=55, line=dict(dash="dash", color=PALETTE["muted"]), annotation_text="умеренный порог",
                  annotation_font=dict(color=PALETTE["text"], size=10))
    _apply_plotly_theme(fig, "Recovery score (100 − нагрузка)")
    fig.update_yaxes(title="recovery", range=[0, 100])
    return fig


def _stress_stress_chart(daily: Sequence[Tuple[date, float]], rolling: Sequence[Tuple[date, float]]) -> Optional[go.Figure]:
    if not daily:
        return None
    xd, yd = _dates_vals(daily)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xd, y=yd, name="Нагрузка (день)", line=dict(color=PALETTE["alert"], width=1.5), opacity=0.5))
    if rolling:
        xr, yr = _dates_vals(rolling)
        fig.add_trace(go.Scatter(x=xr, y=yr, name="7-дн среднее", line=dict(color=PALETTE["warn"], width=3)))
    fig.add_hline(y=45, line=dict(dash="dash", color=PALETTE["muted"]), annotation_text="умеренный порог",
                  annotation_font=dict(color=PALETTE["text"], size=10))
    fig.add_hline(y=65, line=dict(dash="dash", color=PALETTE["alert"]), annotation_text="высокий порог",
                  annotation_font=dict(color=PALETTE["text"], size=10))
    _apply_plotly_theme(fig, "Индекс нагрузки / стресса (0–100, персональная модель)")
    fig.update_yaxes(title="нагрузка", range=[0, 100])
    return fig


def _domain_bar_chart(domains: Sequence[Any]) -> Optional[go.Figure]:
    if not domains:
        return None
    names = [d.name_ru for d in domains]
    vals = [d.stress_0_100 for d in domains]
    colors = [PALETTE["ok"] if v < 35 else PALETTE["warn"] if v < 55 else PALETTE["alert"] for v in vals]
    fig = go.Figure(go.Bar(
        y=names, x=vals, orientation="h", marker_color=colors,
        text=[f"{v:.0f}" for v in vals], textposition="outside",
        textfont=dict(color=PALETTE["text"]),
        hovertemplate="%{y}: %{x:.0f}/100<extra></extra>",
    ))
    _apply_plotly_theme(fig, "Домены нагрузки (последний день)", xaxis_range=[0, 100])
    fig.update_xaxes(title="stress 0–100")
    return fig


def _render_mental_section(data: DashboardInput, add_chart: Any) -> str:
    from apple_health.mental_health import (
        RISK_RU,
        VALENCE_RU,
        assessment_display_name,
        mental_health_empty_notice,
        summarize_assessments,
        summarize_state_of_mind,
    )

    som = list(data.state_of_mind)
    assessments = list(data.scored_assessments)

    if som:
        ordered = sorted(som, key=lambda e: e.recorded)
        xs = [e.recorded.isoformat() for e in ordered if e.valence is not None]
        ys = [e.valence for e in ordered if e.valence is not None]
        if len(xs) >= 2:
            add_chart(_line_chart("State of Mind — valence", xs, ys, "#818cf8", "−1…+1", fill=False))

    som_rows = ""
    for e in reversed(sorted(som, key=lambda x: x.recorded)[-20:]):
        vc = VALENCE_RU.get(e.valence_class, e.valence_class or "—")
        val = f"{e.valence:+.2f}" if e.valence is not None else "—"
        lbl = ", ".join(e.labels) or "—"
        som_rows += (
            f"<tr><td>{html.escape(str(e.recorded))}</td><td>{html.escape(e.kind)}</td>"
            f"<td>{val}</td><td>{html.escape(vc)}</td><td>{html.escape(lbl)}</td></tr>"
        )

    assess_rows = ""
    for e in reversed(sorted(assessments, key=lambda x: x.recorded)[-15:]):
        name = assessment_display_name(e.assessment_type)
        risk = RISK_RU.get(e.risk, e.risk or "—")
        score = f"{e.score:.0f}" if e.score is not None else "—"
        n_ans = len(e.answers)
        assess_rows += (
            f"<tr><td>{html.escape(str(e.recorded))}</td><td>{html.escape(name)}</td>"
            f"<td>{score}</td><td>{html.escape(risk)}</td><td>{n_ans or '—'}</td></tr>"
        )

    if not som and not assessments:
        return f"""
<section id="mental" class="section">
  <h2>Самочувствие и опросники</h2>
  <p class="sub">State of Mind (настроение) и Scored Assessment (PHQ-9, GAD-7 и др.)</p>
  <div class="notice warn">{html.escape(mental_health_empty_notice())}</div>
</section>"""

    summary = summarize_state_of_mind(som) + summarize_assessments(assessments)
    summary_html = "<ul class='insights'>" + "".join(f"<li>{html.escape(x)}</li>" for x in summary) + "</ul>"

    som_table = ""
    if som:
        som_table = f"""
  <h3>State of Mind ({len(som)} записей)</h3>
  <table class="data-table"><thead><tr><th>Дата</th><th>Тип</th><th>Valence</th><th>Класс</th><th>Метки</th></tr></thead>
  <tbody>{som_rows}</tbody></table>"""

    assess_table = ""
    if assessments:
        assess_table = f"""
  <h3>Опросники ({len(assessments)} результатов)</h3>
  <table class="data-table"><thead><tr><th>Дата</th><th>Тест</th><th>Score</th><th>Риск</th><th>Ответов</th></tr></thead>
  <tbody>{assess_rows}</tbody></table>"""

    return f"""
<section id="mental" class="section">
  <h2>Самочувствие и опросники</h2>
  <p class="sub">State of Mind (iOS 18+) и Scored Assessment (PHQ-9/GAD-7). Не замена психиатру.</p>
  {summary_html}
  {som_table}
  {assess_table}
</section>"""


def _render_stress_section(stress: Any, add_chart: Any, nights_sorted: Sequence, hrv_daily: Sequence) -> str:
    if stress is None or not stress.daily_stress:
        return '<section id="stress" class="section"><h2>Нагрузка и стресс</h2><p class="muted">Недостаточно данных HRV/сна.</p></section>'

    from apple_health.stress_assessment import EVIDENCE

    add_chart(_stress_stress_chart(stress.daily_stress, stress.rolling7_stress))
    add_chart(_stress_recovery_chart(stress.daily_recovery, stress.rolling7_stress))
    add_chart(_domain_bar_chart(stress.domain_scores))

    # scatter сон vs HRV с линией тренда
    hrv_map = dict(hrv_daily)
    sx, sy = [], []
    for d, n in nights_sorted:
        if n.asleep_h > 0 and d in hrv_map:
            sx.append(n.asleep_h)
            sy.append(hrv_map[d])
    if len(sx) >= 5:
        sh = stress.sleep_hrv
        title = f"Сон → HRV (r≈{sh.same_day_r:.2f}, n={sh.n_pairs})" if sh.same_day_r is not None else "Сон → HRV"
        fig = _scatter_chart(title, sx, sy, "часы сна", "SDNN мс", PALETTE["hrv"])
        if sh.slope_ms_per_hour is not None and sx:
            import statistics as _stats
            mx, my = _stats.mean(sx), _stats.mean(sy)
            intercept = my - sh.slope_ms_per_hour * mx
            x0, x1 = min(sx), max(sx)
            fig.add_trace(
                go.Scatter(
                    x=[x0, x1],
                    y=[intercept + sh.slope_ms_per_hour * x0, intercept + sh.slope_ms_per_hour * x1],
                    mode="lines",
                    name="тренд",
                    line=dict(dash="dash", color=PALETTE["muted"]),
                )
            )
        add_chart(fig)

    rec = stress.overall_recovery
    st = stress.overall_stress_0_100
    gauge_color = PALETTE["ok"] if st < 45 else PALETTE["warn"] if st < 65 else PALETTE["alert"]

    domain_rows = ""
    for d in stress.domain_scores:
        ev = EVIDENCE.get(d.evidence_key)
        src = f'<a href="{html.escape(ev.url)}">{html.escape(ev.label)}</a>' if ev else ""
        bar_w = min(100, d.stress_0_100)
        domain_rows += f"""
        <tr>
          <td>{html.escape(d.name_ru)} <span class="muted">({d.weight*100:.0f}%)</span></td>
          <td>{html.escape(d.your_value)}</td>
          <td>{html.escape(d.personal_baseline)}</td>
          <td><div class="bar-track"><div class="bar-fill" style="width:{bar_w}%;background:{gauge_color if bar_w>50 else PALETTE['ok']}"></div></div> {d.stress_0_100:.0f}</td>
          <td>{html.escape(d.interpretation_ru)}</td>
          <td>{src}</td>
        </tr>"""

    flags = "".join(f'<li class="flag">{html.escape(f)}</li>' for f in stress.red_flags)
    flags_block = f'<ul class="flags">{flags}</ul>' if flags else '<p class="muted">Критических флагов нет.</p>'

    narrative = "".join(f"<li>{html.escape(x)}</li>" for x in stress.clinical_narrative if x)
    method = "".join(f"<li>{html.escape(x)}</li>" for x in stress.methodology)
    limits = "".join(f"<li>{html.escape(x)}</li>" for x in stress.limitations)

    sh = stress.sleep_hrv
    sleep_stats = ""
    if sh.hrv_short_sleep_mean and sh.hrv_adequate_sleep_mean:
        sleep_stats = (
            f"<p><strong>Сон &lt;6 ч:</strong> HRV ~{sh.hrv_short_sleep_mean:.0f} мс · "
            f"<strong>≥7 ч:</strong> ~{sh.hrv_adequate_sleep_mean:.0f} мс"
            + (f" (эффект ~{sh.effect_pct:.0f}%)" if sh.effect_pct else "")
            + "</p>"
        )
    corr_bits = []
    if sh.same_day_r is not None:
        corr_bits.append(f"r(день)={sh.same_day_r:.2f}")
    if sh.next_day_r is not None:
        corr_bits.append(f"r(+1д)={sh.next_day_r:.2f}")
    if sh.deep_sleep_r is not None:
        corr_bits.append(f"deep={sh.deep_sleep_r:.2f}")
    if sh.rem_sleep_r is not None:
        corr_bits.append(f"REM={sh.rem_sleep_r:.2f}")
    if corr_bits:
        sleep_stats += f"<p class='muted'>Корреляции сон→HRV: {', '.join(corr_bits)} · n={sh.n_pairs}</p>"
    if sh.hrv_sleep_q1_mean and sh.hrv_sleep_q4_mean:
        sleep_stats += (
            f"<p>Квартили: короткий сон → HRV ~{sh.hrv_sleep_q1_mean:.0f} мс · "
            f"длинный → ~{sh.hrv_sleep_q4_mean:.0f} мс</p>"
        )
    if sh.recovery_sleep_threshold_h is not None:
        sleep_stats += f"<p>Порог HRV-recovery: ≥{sh.recovery_sleep_threshold_h:.1f} ч сна</p>"
    if sh.accumulated_sleep_debt_h is not None and sh.accumulated_sleep_debt_h > 0:
        sleep_stats += f"<p>Sleep debt (14 ночей): ~{sh.accumulated_sleep_debt_h:.1f} ч</p>"
    if stress.acute_chronic_ratio is not None:
        sleep_stats += f"<p>A:C stress ratio: {stress.acute_chronic_ratio:.2f}</p>"
    if sh.autonomic_pattern:
        sleep_stats += f"<p><strong>{html.escape(sh.autonomic_pattern)}</strong></p>"

    return f"""
<section id="stress" class="section stress-section">
  <h2>Клиническая оценка нагрузки и восстановления</h2>
  <p class="sub">Многофакторная модель (HRV, RHR, сон, нагрузка) относительно <em>вашей</em> базы. Не диагноз.</p>

  <div class="stress-hero">
    <div class="stress-gauge" style="--gc:{gauge_color}">
      <div class="stress-gauge-label">Индекс нагрузки</div>
      <div class="stress-gauge-value">{st:.0f}</div>
      <div class="stress-gauge-sub">Recovery {rec:.0f}/100 · {html.escape(stress.overall_label)}</div>
    </div>
    <div class="stress-patterns">
      <p><strong>Острая динамика:</strong> {html.escape(stress.pattern_acute or "—")}</p>
      <p><strong>Хронический фон:</strong> {html.escape(stress.pattern_chronic or "—")}</p>
      {sleep_stats}
    </div>
  </div>

  {flags_block}

  <h3>Заключение (автоматическое, для обсуждения с врачом)</h3>
  <ul class="insights clinical-text">{narrative}</ul>

  <h3>Домены модели</h3>
  <table class="data-table domain-table">
    <thead><tr><th>Домен</th><th>Значение</th><th>База</th><th>Stress</th><th>Интерпретация</th><th>Источник</th></tr></thead>
    <tbody>{domain_rows}</tbody>
  </table>

  <details class="method-box">
    <summary>Методология и ограничения</summary>
    <h4>Метод</h4><ul>{method}</ul>
    <h4>Ограничения</h4><ul>{limits}</ul>
  </details>
</section>"""


def _fig_div(fig: go.Figure, include_js: bool = True) -> str:
    return fig.to_html(
        full_html=False,
        include_plotlyjs="cdn" if include_js else False,
        config={"displayModeBar": True, "responsive": True, "scrollZoom": True},
    )


def _dates_vals(series: Sequence[Tuple[date, float]]) -> Tuple[List[str], List[float]]:
    return [d.isoformat() for d, _ in series], [v for _, v in series]


def _line_chart(
    title: str,
    x: List[str],
    y: List[float],
    color: str,
    y_title: str,
    h_lines: Optional[List[Tuple[float, str, str]]] = None,
    fill: bool = True,
) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x,
            y=y,
            mode="lines+markers",
            name=title,
            line=dict(color=color, width=2.5),
            marker=dict(size=4),
            fill="tozeroy" if fill else None,
            fillcolor=f"rgba({int(color[1:3], 16)},{int(color[3:5], 16)},{int(color[5:7], 16)},0.15)" if fill and color.startswith("#") else None,
            hovertemplate="%{x}<br>%{y:.1f}<extra></extra>",
        )
    )
    if h_lines:
        for val, label, dash in h_lines:
            fig.add_hline(
                y=val,
                line=dict(color=PALETTE["muted"], dash=dash, width=1.5),
                annotation_text=label,
                annotation_position="top left",
                annotation_font=dict(size=10, color=PALETTE["text"]),
            )
    _apply_plotly_theme(fig, title)
    fig.update_yaxes(title=y_title)
    return fig


def _bar_chart(title: str, x: List[str], y: List[float], color: str, goal: Optional[float] = None) -> go.Figure:
    colors = [color if (goal is None or v >= goal) else PALETTE["warn"] for v in y]
    fig = go.Figure(go.Bar(
        x=x, y=y, marker_color=colors,
        text=[f"{v:.0f}" for v in y], textposition="outside",
        textfont=dict(color=PALETTE["text"]),
        hovertemplate="%{x}<br>%{y:.0f}<extra></extra>",
    ))
    if goal is not None:
        fig.add_hline(
            y=goal,
            line=dict(color=PALETTE["ok"], dash="dash", width=2),
            annotation_text=f"WHO: {goal:.0f} мин",
            annotation_font=dict(color=PALETTE["text"], size=10),
        )
    _apply_plotly_theme(fig, title)
    fig.update_yaxes(title="минут")
    return fig


def _activity_dual_chart(
    steps: Sequence[Tuple[date, float]],
    distance: Sequence[Tuple[date, float]],
    flights: Sequence[Tuple[date, float]],
) -> Optional[go.Figure]:
    if not steps and not distance:
        return None
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    if steps:
        xs, ys = _dates_vals(steps)
        fig.add_trace(
            go.Bar(x=xs, y=ys, name="Шаги", marker_color=PALETTE["activity"], opacity=0.85,
                   hovertemplate="Шаги: %{y:,.0f}<extra></extra>"),
            secondary_y=False,
        )
    if distance:
        xd, yd = _dates_vals(distance)
        fig.add_trace(
            go.Scatter(x=xd, y=yd, name="Дистанция км", line=dict(color=PALETTE["sleep"], width=2),
                       hovertemplate="%{x}<br>%{y:.1f} км<extra></extra>"),
            secondary_y=True,
        )
    if flights:
        xf, yf = _dates_vals(flights)
        fig.add_trace(
            go.Scatter(x=xf, y=yf, name="Этажи", mode="lines", line=dict(color=PALETTE["spo2"], width=1.5, dash="dot")),
            secondary_y=False,
        )
    _apply_plotly_theme(fig, "Активность: шаги, дистанция, этажи", barmode="overlay")
    fig.update_yaxes(title_text="шаги / этажи", secondary_y=False)
    fig.update_yaxes(title_text="км", secondary_y=True)
    return fig


def _scatter_chart(title: str, x: List[float], y: List[float], x_title: str, y_title: str, color: str) -> go.Figure:
    fig = go.Figure(
        go.Scatter(
            x=x, y=y, mode="markers", marker=dict(size=9, color=color, opacity=0.75),
            hovertemplate=f"{x_title}: %{{x:.1f}}<br>{y_title}: %{{y:.0f}}<extra></extra>",
        )
    )
    _apply_plotly_theme(fig, title)
    fig.update_xaxes(title=x_title)
    fig.update_yaxes(title=y_title)
    return fig


def _build_routes_map(gpx_paths: Sequence[Tuple[str, Any]], latlon_fn: Any) -> str:
    try:
        import folium
    except ImportError:
        return '<p class="muted">Установите folium: pip install folium</p>'
    routes: List[Tuple[str, List[Tuple[float, float]]]] = []
    for label, path in list(gpx_paths)[-25:]:
        coords = latlon_fn(path)
        if len(coords) >= 2:
            routes.append((label, coords))
    if not routes:
        return '<p class="muted">Нет GPX-маршрутов в выбранном периоде.</p>'
    mid = routes[0][1][len(routes[0][1]) // 2]
    m = folium.Map(location=[mid[0], mid[1]], zoom_start=13, tiles="CartoDB dark_matter")
    colors = ["#2dd4bf", "#818cf8", "#fb7185", "#fbbf24", "#38bdf8", "#a78bfa"]
    all_pts: List[Tuple[float, float]] = []
    for i, (label, coords) in enumerate(routes):
        folium.PolyLine(
            coords, color=colors[i % len(colors)], weight=3, opacity=0.85, tooltip=label
        ).add_to(m)
        folium.CircleMarker(coords[0], radius=3, color=colors[i % len(colors)], fill=True, popup=f"Старт {label}").add_to(m)
        all_pts.extend(coords)
    if all_pts:
        m.fit_bounds(
            [
                [min(c[0] for c in all_pts), min(c[1] for c in all_pts)],
                [max(c[0] for c in all_pts), max(c[1] for c in all_pts)],
            ]
        )
    return f'<div class="map-wrap">{m._repr_html_()}</div>'


def _pie_chart(title: str, labels: List[str], values: List[int]) -> go.Figure:
    fig = go.Figure(
        go.Pie(
            labels=labels,
            values=values,
            hole=0.45,
            marker=dict(colors=[PALETTE["ok"], PALETTE["warn"], PALETTE["alert"], PALETTE["spo2"], PALETTE["muted"]]),
            textinfo="label+percent",
            textfont=dict(color=PALETTE["text"], size=11),
            hovertemplate="%{label}: %{value}<br>%{percent}<extra></extra>",
        )
    )
    _apply_plotly_theme(fig, title, showlegend=False)
    return fig


def _sleep_stages_chart(nights_sorted: Sequence[Tuple[date, Any]]) -> Optional[go.Figure]:
    if not nights_sorted:
        return None
    dates: List[str] = []
    core, rem, deep, awake = [], [], [], []
    for d, n in nights_sorted:
        sh = n.stages_h
        core_v = sh.get("HKCategoryValueSleepAnalysisAsleepCore", 0)
        rem_v = sh.get("HKCategoryValueSleepAnalysisAsleepREM", 0)
        deep_v = sh.get("HKCategoryValueSleepAnalysisAsleepDeep", 0)
        uns_v = sh.get("HKCategoryValueSleepAnalysisAsleepUnspecified", 0)
        if core_v + rem_v + deep_v + uns_v + n.awake_h <= 0:
            continue
        dates.append(d.isoformat())
        core.append(core_v + uns_v * 0.5)
        rem.append(rem_v)
        deep.append(deep_v)
        awake.append(n.awake_h)
    if not dates:
        return None
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Core", x=dates, y=core, marker_color="#0d9488", hovertemplate="Core: %{y:.1f} ч<extra></extra>"))
    fig.add_trace(go.Bar(name="REM", x=dates, y=rem, marker_color="#6366f1", hovertemplate="REM: %{y:.1f} ч<extra></extra>"))
    fig.add_trace(go.Bar(name="Deep", x=dates, y=deep, marker_color="#1e3a8a", hovertemplate="Deep: %{y:.1f} ч<extra></extra>"))
    fig.add_trace(go.Bar(name="Awake", x=dates, y=awake, marker_color="#f59e0b", hovertemplate="Awake: %{y:.1f} ч<extra></extra>"))
    _apply_plotly_theme(fig, "Сон по стадиям (ч)", barmode="stack")
    return fig


def _kpi(label: str, value: str, hint: str, tone: str = "neutral") -> str:
    tones = {
        "neutral": ("#6366f1", "rgba(99,102,241,0.12)"),
        "ok": (PALETTE["ok"], "rgba(74,222,128,0.12)"),
        "warn": (PALETTE["warn"], "rgba(251,191,36,0.12)"),
        "alert": (PALETTE["alert"], "rgba(248,113,113,0.12)"),
        "sleep": (PALETTE["sleep"], "rgba(45,212,191,0.12)"),
        "hrv": (PALETTE["hrv"], "rgba(167,139,250,0.12)"),
        "activity": (PALETTE["activity"], "rgba(251,191,36,0.12)"),
    }
    accent, bg = tones.get(tone, tones["neutral"])
    return f"""
    <div class="kpi" style="--accent:{accent};--kpi-bg:{bg}">
      <div class="kpi-label">{html.escape(label)}</div>
      <div class="kpi-value">{html.escape(value)}</div>
      <div class="kpi-hint">{html.escape(hint)}</div>
    </div>"""


def render_rich_report(data: DashboardInput) -> str:
    esc = data.esc_fn
    charts: List[str] = []
    first_js = True

    def add_chart(fig: Optional[go.Figure]) -> None:
        nonlocal first_js
        if fig is None:
            return
        charts.append(f'<div class="chart-box">{_fig_div(fig, include_js=first_js)}</div>')
        first_js = False

    # --- charts
    sleep_dates = [d.isoformat() for d, n in data.nights_sorted]
    sleep_hours = [n.asleep_h for _, n in data.nights_sorted]
    if sleep_dates:
        add_chart(
            _line_chart(
                "Продолжительность сна",
                sleep_dates,
                sleep_hours,
                PALETTE["sleep"],
                "часы",
                h_lines=[(7.0, "CDC ≥ 7 ч", "dash")],
            )
        )
        awake_min = [n.awake_h * 60 for _, n in data.nights_sorted]
        add_chart(
            _line_chart(
                "Бодрствование ночью",
                sleep_dates,
                awake_min,
                PALETTE["activity"],
                "минуты",
                fill=False,
            )
        )
        add_chart(_sleep_stages_chart(data.nights_sorted))

    if data.hrv_daily:
        xs, ys = _dates_vals(data.hrv_daily)
        fig = _line_chart("HRV (SDNN) — ваш тренд", xs, ys, PALETTE["hrv"], "мс", fill=True)
        if data.med_hrv is not None:
            fig.add_hline(y=data.med_hrv, line=dict(color=PALETTE["muted"], dash="dot"), annotation_text="медиана")
        if data.low_hrv_q is not None:
            fig.add_hline(y=data.low_hrv_q, line=dict(color=PALETTE["warn"], dash="dash"), annotation_text="Q1")
        add_chart(fig)

    if data.rmssd_daily:
        xs, ys = _dates_vals(data.rmssd_daily)
        fig = _line_chart("HRV (RMSSD) — из beat-to-beat", xs, ys, "#34d399", "мс", fill=True)
        if data.med_rmssd is not None:
            fig.add_hline(y=data.med_rmssd, line=dict(color=PALETTE["muted"], dash="dot"),
                          annotation_text="медиана", annotation_font=dict(color=PALETTE["text"], size=10))
        add_chart(fig)

    if data.rhr_daily:
        xs, ys = _dates_vals(data.rhr_daily)
        add_chart(
            _line_chart(
                "Пульс в покое",
                xs,
                ys,
                PALETTE["rhr"],
                "уд/мин",
                h_lines=[(60, "AHA 60", "dot"), (100, "AHA 100", "dot")],
                fill=False,
            )
        )

    if data.spo2_daily:
        xs, ys = _dates_vals(data.spo2_daily)
        add_chart(
            _line_chart(
                "SpO₂ (днём)",
                xs,
                ys,
                PALETTE["spo2"],
                "%",
                h_lines=[(95, "норма ≥95%", "dash"), (92, "≤92% — врач", "dash")],
                fill=False,
            )
        )

    if data.spo2_night_daily:
        xs, ys = _dates_vals(data.spo2_night_daily)
        add_chart(
            _line_chart(
                "SpO₂ во время сна",
                xs,
                ys,
                "#6366f1",
                "%",
                h_lines=[(95, "≥95%", "dash")],
                fill=False,
            )
        )

    add_chart(_activity_dual_chart(data.steps_daily, data.distance_daily, data.flights_daily))

    if data.vo2_daily:
        xs, ys = _dates_vals(data.vo2_daily)
        add_chart(_line_chart("VO₂ Max", xs, ys, "#22c55e", "мл/кг/мин", fill=False))

    if data.hr_recovery_daily:
        xs, ys = _dates_vals(data.hr_recovery_daily)
        add_chart(
            _line_chart(
                "Восстановление пульса (1 мин)",
                xs,
                ys,
                PALETTE["rhr"],
                "уд/мин падения",
                h_lines=[(15, "≥15 хорошо", "dash"), (25, "≥25 отлично", "dash")],
                fill=False,
            )
        )

    if data.body_mass_daily or data.body_fat_daily:
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        if data.body_mass_daily:
            xm, ym = _dates_vals(data.body_mass_daily)
            fig.add_trace(go.Scatter(x=xm, y=ym, name="Вес кг", line=dict(color="#e2e8f0")), secondary_y=False)
        if data.body_fat_daily:
            xf, yf = _dates_vals(data.body_fat_daily)
            fig.add_trace(go.Scatter(x=xf, y=yf, name="Жир %", line=dict(color="#f472b6")), secondary_y=True)
        if data.lean_mass_daily:
            xl, yl = _dates_vals(data.lean_mass_daily)
            fig.add_trace(go.Scatter(x=xl, y=yl, name="Мышцы кг", line=dict(color="#38bdf8", dash="dot")), secondary_y=False)
        _apply_plotly_theme(fig, "Состав тела")
        fig.update_yaxes(title_text="кг", secondary_y=False)
        fig.update_yaxes(title_text="% жира", secondary_y=True)
        add_chart(fig)

    if data.asymmetry_daily:
        xs, ys = _dates_vals(data.asymmetry_daily)
        add_chart(_line_chart("Асимметрия ходьбы", xs, ys, PALETTE["warn"], "%", fill=False))

    if data.steadiness_daily:
        xs, ys = _dates_vals(data.steadiness_daily)
        add_chart(_line_chart("Walking Steadiness", xs, ys, PALETTE["ok"], "%", fill=False))

    if data.mindful_daily:
        xs, ys = _dates_vals(data.mindful_daily)
        add_chart(_bar_chart("Mindfulness (мин/день)", xs, ys, "#818cf8"))

    # scatter «сон vs HRV» только в секции «Стресс»

    if data.weekly_minutes:
        wx = [w for w, _ in data.weekly_minutes]
        wy = [m for _, m in data.weekly_minutes]
        add_chart(_bar_chart("Активность по неделям", wx, wy, PALETTE["activity"], goal=150.0))

    if data.ecg_summary:
        labels = [k for k, _ in data.ecg_summary]
        values = [v for _, v in data.ecg_summary]
        add_chart(_pie_chart("ЭКГ — классификации Apple", labels, values))

    # KPIs
    sleep_kpi = f"{data.avg_asleep:.1f} ч" if data.avg_asleep is not None else "—"
    sleep_tone = "ok" if data.avg_asleep and data.avg_asleep >= 7 else "warn" if data.avg_asleep else "neutral"
    hrv_kpi = f"{data.med_hrv:.0f} мс" if data.med_hrv is not None else "—"
    rhr_kpi = f"{data.med_rhr:.0f}" if data.med_rhr is not None else "—"
    act_kpi = f"{data.avg_weekly_min:.0f} мин/нед" if data.avg_weekly_min is not None else "—"
    act_tone = "ok" if data.avg_weekly_min and data.avg_weekly_min >= 150 else "warn" if data.avg_weekly_min else "neutral"

    steps_kpi = f"{data.avg_steps:,.0f}" if data.avg_steps is not None else "—"
    vo2_kpi = f"{data.latest_vo2:.1f}" if data.latest_vo2 is not None else "—"
    stress_kpi = "—"
    stress_tone = "neutral"
    if data.stress_assessment and data.stress_assessment.daily_stress:
        st = data.stress_assessment.overall_stress_0_100
        stress_kpi = f"{st:.0f}"
        stress_tone = "ok" if st < 45 else "warn" if st < 65 else "alert"

    kpis = "".join(
        [
            _kpi("Нагрузка / стресс", stress_kpi, "персональный индекс 0–100", stress_tone),
            _kpi("Сон (среднее)", sleep_kpi, f"{data.nights_count} ночей", sleep_tone),
            _kpi("Шаги/день", steps_kpi, "среднее за период", "activity"),
            _kpi("VO₂ Max", vo2_kpi, "мл/кг/мин · ACSM", "ok" if data.latest_vo2 else "neutral"),
            _kpi("HRV медиана", hrv_kpi, "SDNN, тренд для себя", "hrv"),
            _kpi("Пульс покоя", rhr_kpi, "уд/мин · AHA 60–100", "neutral"),
            _kpi("Тренировки", str(data.workouts_count), f"{data.total_workout_km:.1f} км · GPS: {data.routes_count}", "activity"),
        ]
    )

    map_html = _build_routes_map(data.gpx_paths, data.parse_gpx_latlon_fn)

    insights_html = ""
    if data.insights:
        stress_lines = set()
        if data.stress_assessment and data.stress_assessment.clinical_narrative:
            stress_lines = {x.strip() for x in data.stress_assessment.clinical_narrative if x.strip()}
        insights_html = "<ul class='insights'>" + "".join(
            f"<li>{html.escape(x)}</li>"
            for x in data.insights
            if x and x.strip() and x.strip() not in stress_lines
        ) + "</ul>"

    stress_html = _render_stress_section(
        data.stress_assessment, add_chart, data.nights_sorted, data.hrv_daily
    )
    mental_html = _render_mental_section(data, add_chart)

    charts_html = "\n".join(charts) if charts else '<p class="muted">Недостаточно данных для графиков.</p>'
    ww = data.weekday_weekend_sleep
    ww_html = ""
    if ww.get("weekday") or ww.get("weekend"):
        ww_html = (
            f"<p class='sub'>Сон: будни <strong>{ww.get('weekday', 0):.1f} ч</strong> · "
            f"выходные <strong>{ww.get('weekend', 0):.1f} ч</strong></p>"
        )

    outlier_html = ""
    if data.hrv_outliers or data.sleep_outliers:
        parts = []
        for d, v, note in data.sleep_outliers[-5:]:
            parts.append(f"<li>{d}: {v:.1f} ч — {html.escape(note)}</li>")
        for d, v, note in data.hrv_outliers[-5:]:
            parts.append(f"<li>{d}: HRV {v:.0f} мс — {html.escape(note)}</li>")
        outlier_html = "<ul class='insights'>" + "".join(parts) + "</ul>"

    profile = []
    if data.birth_date:
        profile.append(f"🎂 {data.birth_date.isoformat()}")
    if data.user_age is not None:
        profile.append(f"{data.user_age} лет")
    if data.sex_label:
        profile.append(data.sex_label)
    profile_str = " · ".join(html.escape(p) for p in profile) if profile else "—"
    sources_str = html.escape(", ".join(data.sources_used) or "—")

    notice = ""
    if data.cda_only:
        notice = '<div class="notice warn">Режим CDA: неполные данные. Используйте <code>--source both</code> для полного отчёта.</div>'
    elif data.source == "both":
        notice = '<div class="notice info">Данные HealthKit + CDA объединены. Тренировки и GPS — из export.xml.</div>'

    clinical_html = data.render_clinical_table_fn(list(data.clinical_checks), data.clinical_refs)

    # ECG table
    ecg_rows = ""
    for r in reversed(list(data.ecg_records)[-15:]):
        dt = r.recorded.strftime("%Y-%m-%d %H:%M") if r.recorded else "—"
        cls = "badge-ok" if r.classification == "Sinus Rhythm" else (
            "badge-alert" if r.classification == "Atrial Fibrillation" else "badge-warn"
        )
        ecg_rows += (
            f"<tr><td>{esc(dt)}</td><td><span class='{cls}'>{esc(r.classification)}</span></td>"
            f"<td>{esc(r.device)}</td><td><code>{esc(r.path)}</code></td></tr>"
        )
    ecg_block = (
        f'<table class="data-table"><thead><tr><th>Дата</th><th>Результат</th><th>Устройство</th><th>Файл</th></tr></thead>'
        f"<tbody>{ecg_rows or '<tr><td colspan=4 class=muted>Нет записей</td></tr>'}</tbody></table>"
    )

    afib_n = sum(1 for r in data.ecg_records if r.classification == "Atrial Fibrillation")
    afib_alert = ""
    if afib_n:
        afib_alert = f'<div class="notice alert"><strong>Atrial Fibrillation: {afib_n}</strong> — обратитесь к кардиологу.</div>'

    # Workouts table
    wrows = ""
    for w in reversed(list(data.workouts)[-12:]):
        dist = w.distance_km or w.route_distance_km
        dist_s = f"{dist:.2f}" if dist else "—"
        hr_s = f"{w.hr_avg:.0f}" if w.hr_avg else "—"
        wrows += (
            f"<tr><td>{esc(w.start.strftime('%d.%m %H:%M'))}</td>"
            f"<td>{esc(data.workout_label_fn(w.activity_type))}</td>"
            f"<td>{w.duration_min:.0f}</td>"
            f"<td>{dist_s}</td>"
            f"<td>{hr_s}</td></tr>"
        )
    workout_block = (
        f'<table class="data-table"><thead><tr><th>Дата</th><th>Тип</th><th>мин</th><th>км</th><th>ЧСС</th></tr></thead>'
        f"<tbody>{wrows or '<tr><td colspan=5 class=muted>Нет тренировок</td></tr>'}</tbody></table>"
    )

    sleep_rows = ""
    for d, n in reversed(list(data.nights_sorted)[-14:]):
        sleep_rows += f"<tr><td>{esc(d)}</td><td>{n.asleep_h:.2f}</td><td>{n.awake_h*60:.0f}</td><td>{n.inbed_h:.2f}</td></tr>"
    sleep_table = (
        f'<table class="data-table"><thead><tr><th>Ночь</th><th>Сон ч</th><th>Awake мин</th><th>В кровати</th></tr></thead>'
        f"<tbody>{sleep_rows or '<tr><td colspan=4 class=muted>Нет данных</td></tr>'}</tbody></table>"
    )

    charts_html = "\n".join(charts) if charts else '<p class="muted">Недостаточно данных для графиков.</p>'

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Apple Health — дашборд</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet"/>
<style>
:root {{
  --bg: {PALETTE["bg"]};
  --surface: {PALETTE["surface"]};
  --card: {PALETTE["card"]};
  --border: {PALETTE["border"]};
  --text: {PALETTE["text"]};
  --muted: {PALETTE["muted"]};
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; font-family: Inter, system-ui, sans-serif;
  background: linear-gradient(160deg, #0b1220 0%, #111827 40%, #0f172a 100%);
  color: var(--text); min-height: 100vh;
}}
.wrap {{ max-width: 1200px; margin: 0 auto; padding: 24px 20px 64px; }}
.hero {{
  background: linear-gradient(135deg, rgba(99,102,241,0.25), rgba(45,212,191,0.15));
  border: 1px solid var(--border); border-radius: 20px; padding: 28px 32px; margin-bottom: 24px;
}}
.hero h1 {{ margin: 0 0 8px; font-size: 1.75rem; font-weight: 700; letter-spacing: -0.02em; }}
.hero-meta {{ color: var(--muted); font-size: 0.9rem; line-height: 1.6; }}
.nav {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0 24px; }}
.nav a {{
  color: var(--text); text-decoration: none; font-size: 0.85rem; padding: 8px 14px;
  background: var(--card); border: 1px solid var(--border); border-radius: 999px;
}}
.nav a:hover {{ border-color: #6366f1; }}
.kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 14px; margin-bottom: 28px; }}
.kpi {{
  background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 16px 18px;
  border-left: 3px solid var(--accent);
}}
.kpi-label {{ font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); }}
.kpi-value {{ font-size: 1.65rem; font-weight: 700; margin: 6px 0 4px; color: var(--accent); }}
.kpi-hint {{ font-size: 0.78rem; color: var(--muted); }}
.section {{
  background: var(--card); border: 1px solid var(--border); border-radius: 18px;
  padding: 22px 24px; margin-bottom: 20px;
}}
.section h2 {{ margin: 0 0 6px; font-size: 1.15rem; font-weight: 600; }}
.section .sub {{ color: var(--muted); font-size: 0.88rem; margin-bottom: 16px; }}
.chart-box {{ margin: 12px 0 20px; min-height: 320px; }}
  /* Plotly: контраст tooltip/осей на тёмной теме */
  .js-plotly-plot .hoverlayer .hovertext,
  .js-plotly-plot .hoverlayer text {{
    fill: #e8edf5 !important;
    color: #e8edf5 !important;
  }}
  .js-plotly-plot .hoverlayer .bg {{
    fill: #1a2332 !important;
    fill-opacity: 0.97 !important;
    stroke: #2a3548 !important;
    stroke-width: 1px !important;
  }}
  .js-plotly-plot .legend text {{ fill: #e8edf5 !important; }}
  .js-plotly-plot .infolayer text {{ fill: #e8edf5 !important; }}
  .js-plotly-plot .gtitle {{ fill: #e8edf5 !important; }}
  .js-plotly-plot .xtick text, .js-plotly-plot .ytick text {{ fill: #8b9cb3 !important; }}
  .js-plotly-plot .xaxislayer-above text, .js-plotly-plot .yaxislayer-above text {{ fill: #8b9cb3 !important; }}
.chart-grid {{ display: grid; grid-template-columns: 1fr; gap: 8px; }}
@media (min-width: 900px) {{ .chart-grid.two {{ grid-template-columns: 1fr 1fr; }} }}
.data-table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
.data-table th, .data-table td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border); }}
.data-table th {{ color: var(--muted); font-weight: 500; font-size: 0.75rem; text-transform: uppercase; }}
.data-table tr:hover td {{ background: rgba(255,255,255,0.02); }}
table.clinical {{ font-size: 0.82rem; }}
table.clinical th, table.clinical td {{ border-color: var(--border); color: var(--text); }}
table.clinical thead {{ background: rgba(255,255,255,0.04); }}
.notice {{ padding: 12px 16px; border-radius: 12px; margin-bottom: 16px; font-size: 0.9rem; }}
.notice.warn {{ background: rgba(251,191,36,0.12); border: 1px solid rgba(251,191,36,0.35); }}
.notice.info {{ background: rgba(56,189,248,0.1); border: 1px solid rgba(56,189,248,0.3); }}
.notice.alert {{ background: rgba(248,113,113,0.12); border: 1px solid rgba(248,113,113,0.4); }}
.muted {{ color: var(--muted); }}
code {{ background: rgba(255,255,255,0.06); padding: 2px 6px; border-radius: 4px; font-size: 0.85em; }}
.badge-ok, .badge-warn, .badge-alert, .badge-info {{
  padding: 3px 10px; border-radius: 999px; font-size: 0.75rem; font-weight: 500;
}}
.badge-ok {{ background: rgba(74,222,128,0.15); color: #4ade80; }}
.badge-warn {{ background: rgba(251,191,36,0.15); color: #fbbf24; }}
.badge-alert {{ background: rgba(248,113,113,0.15); color: #f87171; }}
.badge-info {{ background: rgba(56,189,248,0.15); color: #38bdf8; }}
  .footer {{ color: var(--muted); font-size: 0.8rem; margin-top: 32px; line-height: 1.6; }}
  .map-wrap {{ border-radius: 12px; overflow: hidden; border: 1px solid var(--border); margin-top: 12px; }}
  .map-wrap iframe, .map-wrap .folium-map {{ width: 100% !important; min-height: 420px; }}
  ul.insights {{ margin: 0; padding-left: 1.2rem; line-height: 1.7; color: var(--text); }}
  ul.insights li {{ margin-bottom: 6px; }}
  .stress-section {{ border-color: rgba(99,102,241,0.35); }}
  .stress-hero {{ display: grid; grid-template-columns: 1fr 1.5fr; gap: 20px; margin-bottom: 20px; }}
  @media (max-width: 700px) {{ .stress-hero {{ grid-template-columns: 1fr; }} }}
  .stress-gauge {{
    background: rgba(0,0,0,0.25); border-radius: 16px; padding: 24px; text-align: center;
    border: 1px solid var(--border); border-top: 4px solid var(--gc);
  }}
  .stress-gauge-value {{ font-size: 3.2rem; font-weight: 800; color: var(--gc); line-height: 1; }}
  .stress-gauge-label {{ font-size: 0.75rem; text-transform: uppercase; color: var(--muted); letter-spacing: 0.08em; }}
  .stress-gauge-sub {{ font-size: 0.88rem; color: var(--muted); margin-top: 8px; }}
  .stress-patterns p {{ margin: 0 0 10px; font-size: 0.9rem; line-height: 1.55; }}
  .bar-track {{ background: rgba(255,255,255,0.06); height: 8px; border-radius: 4px; width: 80px; display: inline-block; vertical-align: middle; margin-right: 6px; }}
  .bar-fill {{ height: 100%; border-radius: 4px; }}
  .domain-table td {{ font-size: 0.82rem; }}
  .clinical-text li {{ margin-bottom: 8px; }}
  ul.flags {{ list-style: none; padding: 0; margin: 0 0 16px; }}
  ul.flags li.flag {{ background: rgba(248,113,113,0.12); border: 1px solid rgba(248,113,113,0.35); padding: 10px 14px; border-radius: 10px; margin-bottom: 8px; }}
  .method-box {{ margin-top: 16px; font-size: 0.85rem; color: var(--muted); }}
  .method-box summary {{ cursor: pointer; color: var(--text); font-weight: 500; }}
  .kpi[style*="--accent:#f87171"] {{ }}
</style>
</head>
<body>
<div class="wrap">
  <header class="hero">
    <h1>🫀 Apple Health Dashboard</h1>
    <div class="hero-meta">
      Период: <strong>{data.lookback_days} дней</strong> · {profile_str}<br/>
      Источники: {sources_str} · ECG · GPX
    </div>
  </header>

  <nav class="nav">
    <a href="#stress">Стресс</a>
    <a href="#mental">Самочувствие</a>
    <a href="#overview">Обзор</a>
    <a href="#insights">Инсайты</a>
    <a href="#charts">Графики</a>
    <a href="#map">Карта</a>
    <a href="#clinical">Ориентиры</a>
    <a href="#sleep">Сон</a>
    <a href="#workouts">Тренировки</a>
    <a href="#ecg">ЭКГ</a>
  </nav>

  {notice}

  <section id="overview" class="section">
    <h2>Ключевые показатели</h2>
    <p class="sub">Сводка за выбранный период. Ориентиры — CDC, WHO, AHA; не замена врачу.</p>
    <div class="kpi-grid">{kpis}</div>
  </section>

  {stress_html}

  {mental_html}

  <section id="insights" class="section">
    <h2>Умная аналитика</h2>
    <p class="sub">Корреляции и выводы по вашим данным (не диагноз).</p>
    {ww_html}
    {insights_html if insights_html else '<p class="muted">Недостаточно данных для выводов.</p>'}
    <h3>Необычные дни</h3>
    {outlier_html if outlier_html else '<p class="muted">Выбросов не найдено.</p>'}
  </section>

  <section id="charts" class="section">
    <h2>Интерактивные графики</h2>
    <p class="sub">Plotly: наведите курсор, масштабируйте, перетаскивайте. Для графиков нужен интернет (CDN plotly.js).</p>
    <div class="chart-grid">{charts_html}</div>
  </section>

  <section id="map" class="section">
    <h2>Карта GPX-маршрутов</h2>
    <p class="sub">Последние тренировки с GPS из workout-routes/ (Folium + OpenStreetMap).</p>
    {map_html}
  </section>

  <section id="clinical" class="section">
    <h2>Клинические ориентиры</h2>
    <p class="sub">Публичные рекомендации с ссылками на источники.</p>
    {clinical_html}
  </section>

  <section id="sleep" class="section">
    <h2>Сон — детали</h2>
    {sleep_table}
  </section>

  <section id="workouts" class="section">
    <h2>Тренировки</h2>
    {workout_block}
  </section>

  <section id="ecg" class="section">
    <h2>Электрокардиограммы</h2>
    <p class="sub">Классификация алгоритма Apple, не заключение врача.</p>
    {afib_alert}
    {ecg_block}
  </section>

  <footer class="footer">
    Автоматический отчёт из экспорта HealthKit. ЭКГ Apple Watch ≠ медицинская ЭКГ.
    При симптомах (боль в груди, одышка, обмороки) — обращайтесь к врачу.
  </footer>
</div>
</body>
</html>"""
