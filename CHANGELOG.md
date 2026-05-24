# Changelog

Формат основан на [Keep a Changelog](https://keepachangelog.com/).

## [0.1.0] - 2026-05-24

### Added

- HTML-отчёт по экспорту Apple Health (`export.xml`, CDA, ЭКГ, GPX-маршруты)
- Интерактивный дашборд: сон, HRV, RMSSD, SpO₂, активность, VO₂, стресс/recovery
- Модель нагрузки и восстановления (stress index, sleep→HRV)
- Секции «Стресс» и «Самочувствие» (State of Mind / PHQ-GAD — если есть в экспорте)
- Папки `data/` (вход) и `output/` (отчёт)
- `run.bat` для запуска двойным щелчком в Windows
- MIT License

### Notes

- State of Mind и опросники Apple часто отсутствуют в стандартном `export.xml`
- Графики Plotly требуют интернет при просмотре отчёта (CDN)
- Не является медицинским диагнозом

[0.1.0]: #v010
