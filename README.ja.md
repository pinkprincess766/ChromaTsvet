[English version](README.md) | [Русская версия](README.ru.md)

# ChromaTsvet

**ChromaTsvet** は、CSV/TXT のスペクトルデータやクロマトグラムを読み込み、処理、可視化、簡易同定するためのデスクトップアプリケーションです。

Python/PyQt による UI と Rust/PyO3 による信号処理コアを組み合わせています。v0.2.0 は日常的な作業フローを改善する alpha リリースであり、実験、デモ、今後の科学ツール開発の土台として使うことを目的としています。検証済みの研究機器ではありません。

クローズド alpha テスト向けの手順は [Alpha Testing Guide](docs/testing_guide.md) を参照してください。`examples/alpha/` には、プライベートデータを使わずにインポート、解析、プロット、エクスポートを確認するための合成サンプルがあります。

## 主な機能

- CSV/TXT から数値信号を読み込み
- median / Savitzky-Golay フィルタと baseline correction
- sample rate に基づく FFT 周波数軸
- area normalization
- ピーク検出、FWHM 幅、Gaussian area、SNR
- ピークのグラフ表示とテーブル表示
- 2 つ目の解析済みスペクトルを重ねて表示
- Recent Files、最後に使ったディレクトリ、基本的な keyboard shortcuts
- SQLite 参照ライブラリとの簡易比較と保存済み参照の管理
- ピーク CSV エクスポート
- PDF / HTML / Excel レポート出力
- グラフの PNG / SVG エクスポート
- light / dark theme

## ソースからの起動

必要なもの:

- Python 3.9+
- Rust toolchain / Cargo
- PyO3 ビルドに必要な OS 側のビルドツール

```bash
git clone https://github.com/pinkprincess766/ChromaTsvet.git
cd ChromaTsvet

make setup
make doctor
make run
```

`make setup` は `.venv` を作成し、Python 開発依存関係をインストールし、
Rust/PyO3 拡張を maturin でビルドします。

`make` が使えない環境では Python helper を使えます。

```bash
python scripts/dev.py setup
python scripts/dev.py doctor
python scripts/dev.py run
```

従来の直接起動も引き続き利用できます。

```bash
python python_analyzer/main.py
```

Windows では Python helper を使うのが簡単です。

```bat
py scripts\dev.py setup
py scripts\dev.py doctor
py scripts\dev.py run
```

アプリはデモデータなしで起動します。**Open file** から CSV または TXT ファイルを読み込んでください。

## テスト

```bash
make test
make rust
```

## 構成

```text
python_analyzer/
  main.py                    起動用 bootstrap
  gui/                       MainWindow、dialogs、reference library、theme、log view
  analysis/                  analysis settings と pipeline wrapper
  exporters/                 PDF / HTML / Excel / peak CSV export
  readers/                   CSV/TXT parser
  viz/                       spectrum plot と peak markers
  core/identification.py     SQLite reference matching

rust_module/src/
  lib.rs                     PyO3 analysis pipeline
  signal/                    filters、FFT、normalization、peak detection
  types.rs                   Python から見える Peak 型
```

注意: 日本語 README は英語版とロシア語版より遅れて更新される場合があります。最新の詳細は [English README](README.md) または [Русская версия](README.ru.md) を参照してください。

## ライセンス

[MIT License](LICENSE)
