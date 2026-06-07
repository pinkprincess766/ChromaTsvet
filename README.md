# ChromaTsvet

ChromaTsvet — desktop-приложение для обработки и первичного анализа спектральных данных и хроматограмм.

## Технологии

- Rust + PyO3 — вычислительное ядро для обработки сигнала
- Python + PyQt5 + pyqtgraph — GUI и визуализация
- SQLite — база эталонных веществ
- reportlab — экспорт PDF-отчётов
- NumPy — работа с массивами

## Установка и подготовка

1. Установите Python-зависимости, необходимые для GUI и отчётов: PyQt5, pyqtgraph, NumPy, reportlab, Pillow.
2. Убедитесь, что собранный Rust/PyO3-модуль находится в корне проекта.
   - Windows: `spectrometer_rust.pyd`
   - macOS/Linux: platform-specific extension module после сборки Rust-модуля

## Запуск

На Windows:

```bat
py python_analyzer\main.py
```

На macOS/Linux:

```bash
python3 python_analyzer/main.py
```

## Возможности

- Загрузка CSV/TXT с числовыми данными
- Обработка сигнала и поиск пиков
- Идентификация веществ по базе эталонов
- Добавление и восстановление веществ в базе
- Экспорт отчёта в PDF
