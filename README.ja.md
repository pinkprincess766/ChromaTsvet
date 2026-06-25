[English version](README.md)

# ChromaTsvet

**ChromaTsvet** は、CSV/TXT のスペクトルデータやクロマトグラムを読み込み、処理、可視化、簡易同定するためのデスクトップアプリケーションです。

Python/PyQt による UI と Rust/PyO3 による信号処理コアを組み合わせています。v0.1.0 は最初の公開ソースリリースであり、実験、デモ、今後の科学ツール開発の土台として使うことを目的としています。検証済みの研究機器ではありません。

## 主な機能

- CSV/TXT から数値信号を読み込み
- median / Savitzky-Golay フィルタと baseline correction
- sample rate に基づく FFT 周波数軸
- area normalization
- ピーク検出、FWHM 幅、Gaussian area、SNR
- ピークのグラフ表示とテーブル表示
- SQLite 参照ライブラリとの簡易比較
- ピーク CSV エクスポート
- PDF レポート出力
- light / dark theme

## ソースからの起動

必要なもの:

- Python 3.9+
- Rust toolchain / Cargo
- PyO3 ビルドに必要な OS 側のビルドツール

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

python python_analyzer/main.py
```

Windows では仮想環境を次のように有効化します。

```bat
.venv\Scripts\activate
```

アプリはデモデータなしで起動します。**Open file** から CSV または TXT ファイルを読み込んでください。

## テスト

```bash
QT_QPA_PLATFORM=offscreen python -m unittest discover -v
cd rust_module
cargo test
```

## 構成

```text
python_analyzer/
  main.py                    起動用 bootstrap
  gui/                       MainWindow、dialogs、theme、log view
  analysis/                  analysis settings と pipeline wrapper
  readers/                   CSV/TXT parser
  viz/                       spectrum plot と peak markers
  core/identification.py     SQLite reference matching

rust_module/src/
  lib.rs                     PyO3 analysis pipeline
  signal/                    filters、FFT、normalization、peak detection
  types.rs                   Python から見える Peak 型
```

## ライセンス

[MIT License](LICENSE)
