<p align="right"><a href="README.md">English</a> | <a href="README.ja.md">日本語</a></p>

<p align="center">
  <img src="assets/chromatsvet_readme_logo.png" alt="Логотип ChromaTsvet" width="430">
</p>

<h1 align="center">ChromaTsvet</h1>

<p align="center">
  Десктопное приложение для загрузки, обработки, визуализации и идентификации
  спектральных данных и хроматограмм.
</p>

<p align="center">
  <a href="https://github.com/pinkprincess766/ChromaTsvet/actions/workflows/ci.yml"><img src="https://github.com/pinkprincess766/ChromaTsvet/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/release-v0.2.0-2f855a" alt="Release v0.2.0">
  <img src="https://img.shields.io/badge/Python-3.9%2B-3776ab" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/Rust-PyO3-b7410e" alt="Rust and PyO3">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-4c566a" alt="MIT license"></a>
</p>

![Анализ спектра в ChromaTsvet](docs/screenshots/01-main-spectrum.png)

ChromaTsvet объединяет десктопный интерфейс на PyQt и вычислительное ядро
обработки сигналов на Rust/PyO3. Проект задуман как практичная и проверяемая
основа для научного анализа сигналов, а не как непрозрачный процесс обработки.
Название отсылает к Михаилу Семёновичу Цвету, ботанику и создателю
хроматографии.

## Статус проекта

ChromaTsvet v0.2.0 — alpha-релиз, запускаемый из исходного кода. Основной фокус
версии — удобство повседневной работы: повторная загрузка файлов, более понятное
состояние анализа, настраиваемые численные параметры и расширенный экспорт
отчётов. Приложение уже подходит для локальных экспериментов, демонстраций и
итеративной разработки научных инструментов, но пока не является
сертифицированным лабораторным прибором.

CI запускает Python- и Rust-тесты. Python-тесты теперь используют pytest, а в
проект добавлены детерминированные синтетические спектры для регрессионных
проверок поиска пиков. Идентификация по пикам доступна как прозрачная базовая
реализация; старое косинусное сравнение сохранено как fallback для совместимости.

## Что нового в v0.2

v0.2 делает ежедневную работу со спектральными данными удобнее и менее
повторяющейся.

**Улучшения рабочего процесса:**

- Меню Recent Files для быстрого повторного открытия предыдущих спектров.
- Запоминание последней директории в диалогах Open и Export.
- Улучшенная строка состояния: имя файла, количество точек, количество пиков и состояние анализа.
- Горячие клавиши для частых действий: Open, Analyze, Export PDF и настройки.

**Анализ и GUI:**

- Выбор оконной функции FFT доступен прямо в диалоге настроек анализа.
- Параметры анализа настраиваются через интерфейс: sample rate, threshold, prominence, SNR, smoothing, baseline correction и normalization.

**Данные и экспорт:**

- Более надёжный импорт CSV/TXT: заголовки, UTF-8 BOM, разделители, decimal comma и более понятные сообщения об ошибках.
- Новые форматы отчётов: самодостаточный HTML и Excel workbook.

**Тестирование:**

- Поиск и запуск тестов через pytest.
- Тестовая обвязка синтетических спектров для детерминированных регрессионных тестов.

## Возможности

- Загрузка числовых спектральных или хроматографических данных из CSV и TXT.
- Median- и Savitzky-Golay-фильтрация, опциональное сглаживание спектра и baseline correction.
- Расчёт FFT-спектра с настраиваемым sample rate и частотной осью.
- Нормализация спектра по интегральной площади, когда нужно сравнимое масштабирование интенсивности.
- Поиск пиков с настройками threshold, prominence, distance и SNR; расчёт frequency, intensity, FWHM width в bins/Hz, Gaussian area и SNR.
- Просмотр найденных пиков на графике и в подробной таблице анализа.
- Масштабирование спектра мышью.
- Повторное открытие недавних файлов, переиспользование последней директории и горячие клавиши.
- Сравнение спектров с локальной SQLite-библиотекой эталонов.
- Экспорт найденных пиков с метаданными анализа в CSV и полных результатов анализа в PDF, HTML или Excel.
- Экспорт текущего графика спектра в PNG или SVG.
- Светлая и тёмная темы приложения.

## Скриншоты

<table>
  <tr>
    <td width="50%"><strong>Настройки анализа</strong></td>
    <td width="50%"><strong>Найденные пики</strong></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/02-analysis-settings.png" alt="Диалог настроек анализа"></td>
    <td><img src="docs/screenshots/03-peaks-table.png" alt="Таблица найденных пиков"></td>
  </tr>
  <tr>
    <td colspan="2"><strong>PDF-отчёт анализа</strong></td>
  </tr>
  <tr>
    <td colspan="2" align="center"><img src="docs/screenshots/04-pdf-report.png" alt="Сгенерированный PDF-отчёт анализа" width="620"></td>
  </tr>
</table>

Релизные скриншоты используют детерминированный демонстрационный сигнал с
компонентами на 95 Hz, 240 Hz и 410 Hz. Их можно пересоздать командой
`tools/capture_release_screenshots.py`; PNG-файлы предназначены для README и
GitHub release notes. Для повторной генерации превью PDF нужен либо `pypdfium2`,
либо Poppler `pdftoppm`.

## Быстрый старт

### Требования

- Python 3.9 или новее
- Актуальный Rust toolchain с Cargo
- Системные build tools, необходимые для PyO3

### Сборка и запуск из исходного кода

```bash
git clone https://github.com/pinkprincess766/ChromaTsvet.git
cd ChromaTsvet

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install maturin
python -m pip install -e .

cd rust_module
maturin develop
cd ..

chromatsvet
```

Установленная консольная команда `chromatsvet` — рекомендуемый способ запуска
приложения. Исторический прямой запуск скрипта также поддерживается:

```bash
python python_analyzer/main.py
```

На Windows активируйте виртуальное окружение так:

```bat
.venv\Scripts\activate
```

После этого выполните те же команды `pip`, `maturin develop` и запустите
приложение из активированного окружения. Приложение стартует без демоданных;
используйте **Open file**, чтобы загрузить CSV- или TXT-спектр.

## Входные данные

Самый простой поддерживаемый файл содержит одно значение интенсивности в строке:

```text
intensity
0.12
0.35
1.42
0.48
```

Также поддерживаются двухколоночные файлы без заголовка; в этом случае второй
столбец интерпретируется как интенсивность. Именованные столбцы вроде
`intensity`, `amplitude`, `signal`, `value` или `absorbance` определяются
автоматически. CSV-файлы могут использовать запятую, точку с запятой или tab в
качестве разделителя.

После загрузки файла задайте корректный sample rate в **Analysis Settings**. Он
нужен для преобразования бинов FFT в физические значения частоты.

## Типичный рабочий процесс

1. Откройте CSV- или TXT-файл сигнала.
2. Настройте sample rate, фильтрацию, сглаживание спектра, baseline correction и параметры поиска пиков.
3. Запустите анализ и проверьте отмеченные пики на частотном графике.
4. Просмотрите frequency, intensity, width в bins/Hz, area и SNR в таблице результатов.
5. Экспортируйте список пиков в CSV или сформируйте отчёт анализа в PDF, HTML или Excel.

## Разработка

Для разработки и тестов установите опциональные зависимости:

```bash
python -m pip install -e ".[test]"
```

Запуск Python-тестов из корня проекта:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -v
```

Запуск Rust unit tests:

```bash
cd rust_module
cargo test
```

Запуск детерминированных регрессионных тестов на синтетических спектрах:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/unit/test_synthetic_peak_detection.py -v
```

Перегенерация PNG-скриншотов для v0.2:

```bash
QT_QPA_PLATFORM=offscreen python tools/capture_release_screenshots.py
```

См. [Development Notes](docs/development.md) для текущего процесса сборки через
maturin и процедуры performance profiling. См. [Peak-Based Identification](docs/identification.md)
для текущего сопоставления по пикам и legacy cosine fallback.

## Архитектура

```text
python_analyzer/
  main.py                    Тонкий bootstrap и compatibility facade
  gui/main_window.py         Оркестрация MainWindow, состояние, экспорт
  gui/dialogs.py             Диалоги настроек, анализа и логов
  gui/error_messages.py      Вспомогательные функции для сообщений об ошибках
  gui/recent_files.py        Recent Files и запоминание последней директории
  gui/theme.py               Помощники для Qt palette и stylesheet
  gui/log_view.py            Общее форматирование log view
  analysis/models.py         Dataclasses AnalysisSettings и LoadedSpectrum
  analysis/runner.py         Обёртка pipeline Filter -> Rust
  analysis/windowing.py      Имена, labels и validation для FFT window
  exporters/excel_report.py  Экспорт книги Excel
  exporters/html_report.py   Экспорт самодостаточного HTML-отчёта
  exporters/pdf_report.py    Генерация PDF-отчёта
  exporters/peak_csv.py      Экспорт найденных пиков в CSV
  readers/spectrum_reader.py Парсинг CSV/TXT-спектров
  viz/spectrum_plot.py       График спектра, частотная ось, peak markers
  core/identification.py     SQLite-backed reference matching

rust_module/src/
  lib.rs                     PyO3 analysis pipeline
  types.rs                   Типы результата, видимые из Python
  signal/filters.rs          Фильтры и baseline correction
  signal/fft.rs              FFT и расчёт частотной оси
  signal/normalization.rs    Integral-area normalization
  signal/peak_detection.rs   Метрики и поиск пиков
  signal/window.rs           FFT window functions

tests/
  conftest.py                Общие pytest fixtures
  support/synthetic_spectra.py
                             Синтетические спектры и helpers для peak matching tests
  unit/                      Unit- и focused regression tests
```

Python отвечает за работу с файлами, desktop UI и отчёты. Rust отвечает за
численный pipeline и возвращает обработанный спектр, частотную ось и структуры
пиков через PyO3.

## Область v0.2 и roadmap

Версия 0.2 улучшает повседневную работу вокруг уже существующей основы анализа.
Приложение умеет загружать данные, настраивать анализ через GUI, визуализировать
и экспортировать результаты, сохранять пользовательские настройки, открывать
недавние файлы и создавать PDF, HTML, Excel и CSV со списком пиков.

Следующие приоритеты разработки: более подробная диагностика peak matching,
усиление сценариев работы с библиотекой эталонов, кроссплатформенные готовые сборки и
более широкие синтетические и реальные регрессионные наборы данных. Модель идентификации
описана в [Peak-Based Identification](docs/identification.md).

## Известные ограничения

ChromaTsvet всё ещё является **alpha** научным ПО. Он полезен для экспериментов,
проверки данных, разработки и образовательных задач, но **не является
сертифицированным лабораторным прибором**.

- Идентификация по пикам и сценарии работы с библиотекой эталонов всё ещё развиваются.
- Готовой packaged distribution пока нет; приложение запускается из исходного кода.
- Японская документация ([README.ja.md](README.ja.md)) может временно отставать от английского и русского README.

## Лицензия

ChromaTsvet распространяется под [MIT License](LICENSE).
