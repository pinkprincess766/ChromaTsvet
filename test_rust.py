import sys
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import spectrometer_rust

print("✅ Rust модуль загружен! Версия:", spectrometer_rust.get_version())

# Лучшие тестовые данные с чёткими пиками
data = [0.1, 0.2, 0.5, 1.0, 3.0, 12.0, 8.0, 4.0, 1.5, 0.6, 0.3, 2.5, 9.0, 6.0, 1.0]

print("\n=== Полный пайплайн Rust ===")
result = spectrometer_rust.process_signal(
    data=data,
    sample_rate=1000.0,
    filter_type="median",
    window_type="hann",
    threshold=0.01     # ← очень чувствительный
)
print(f"Длина спектра: {len(result['spectrum'])}")
print(f"Найдено пиков: {len(result['peaks'])}")

for p in result['peaks']:
    print(f"  Пик → pos: {p.position:.2f} | int: {p.intensity:.2f} | SNR: {p.snr:.2f}")

# Графики
plt.figure(figsize=(12, 8))
plt.subplot(2, 1, 1)
plt.plot(data, label="Исходный сигнал", color='gray', alpha=0.7)
plt.plot(result['spectrum'], label="После FFT", color='blue', linewidth=2)
plt.title("Спектр после обработки")
plt.xlabel("Индекс")
plt.ylabel("Амплитуда")
plt.grid(True)
plt.legend()

plt.subplot(2, 1, 2)
if result['peaks']:
    pos = [p.position for p in result['peaks']]
    ints = [p.intensity for p in result['peaks']]
    plt.stem(pos, ints, linefmt='r-', markerfmt='ro', basefmt=' ')
    plt.title("Найденные пики")
else:
    plt.text(0.5, 0.5, "Пики не найдены", ha='center', va='center', transform=plt.gca().transAxes)
plt.xlabel("Позиция")
plt.ylabel("Интенсивность")
plt.grid(True)

plt.tight_layout()
plt.show()
