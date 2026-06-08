[English version](README.md)

# ChromaTsvet

**ChromaTsvet** は、スペクトルデータやクロマトグラムの読み込み、処理、可視化、同定を行うためのデスクトップアプリケーションです。

Python によるデスクトップ UI と、Rust/PyO3 による信号処理コアを組み合わせることで、高速で信頼性の高い科学データ解析ツールの基盤を目指しています。

プロジェクト名 **ChromaTsvet** は、クロマトグラフィーを発明した植物学者 **ミハイル・セミョーノヴィチ・ツヴェット（Mikhail Semyonovich Tsvet）** に敬意を表したものです。

## Features

- CSV/TXT ファイルからスペクトルデータやクロマトグラムを読み込み
- Rust バックエンドによる数値信号の処理
- 窓関数の適用と FFT ベースのスペクトル計算
- 処理済みスペクトルからのピーク検出
- ローカル SQLite リファレンスライブラリとのスペクトル比較
- 参照物質の追加と復元
- PyQt デスクトップ UI によるスペクトルと検出ピークの可視化
- 解析結果の PDF レポート出力

## Installation

### Windows

1. Python 3.9 以降をインストールします。
2. Python 依存パッケージをインストールします。

   ```bat
   py -m pip install numpy PyQt5 pyqtgraph reportlab Pillow
   ```

3. コンパイル済みの Rust 拡張モジュールがプロジェクトルートにあることを確認します。

   ```text
   spectrometer_rust.pyd
   ```

4. アプリケーションを起動します。

   ```bat
   py python_analyzer\main.py
   ```

### macOS / Linux

1. Python 3.9 以降をインストールします。
2. Python 依存パッケージをインストールします。

   ```bash
   python3 -m pip install numpy PyQt5 pyqtgraph reportlab Pillow
   ```

3. 使用している OS 向けの Rust/PyO3 拡張モジュールをビルドし、プロジェクトルートに配置します。
4. アプリケーションを起動します。

   ```bash
   python3 python_analyzer/main.py
   ```

## Building from Source

Rust による信号処理モジュールは `rust_module/` にあり、PyO3 を通じて Python から利用されます。

Rust モジュールをチェックおよびテストするには、次のコマンドを実行します。

```bash
cd rust_module
cargo test
```

拡張モジュールを手動でビルドする場合は、Rust crate を `cdylib` としてビルドし、生成された Python 向けのプラットフォーム固有拡張モジュールをプロジェクトルートに配置します。

- Windows: `spectrometer_rust.pyd`
- macOS / Linux: プラットフォーム固有の共有拡張モジュール

`maturin` などを使ったパッケージングは今後の改善予定です。現在は、意図的にシンプルなビルドフローを保っています。

## Usage

1. ChromaTsvet を起動します。
2. **Open file** をクリックし、数値信号を含む CSV または TXT ファイルを選択します。
3. アプリケーションがデータを読み込み、信号を処理し、結果のスペクトルを表示します。
4. 検出されたピークがプロット上に表示されます。
5. 候補となる物質の一致結果がテーブルに表示されます。
6. **Add** を使って、ローカルライブラリに参照物質を追加できます。
7. **PDF Report** を使って、現在の解析結果を PDF として出力できます。

最良の結果を得るには、1 行に 1 つの信号値を持つ、整理された数値入力ファイルを使用してください。

## Project Structure

```text
.
├── python_analyzer/
│   ├── main.py                  # PyQt GUI、ファイル読み込み、プロット、PDF 出力
│   └── core/
│       └── identification.py    # SQLite ベースのスペクトル同定
├── rust_module/
│   ├── Cargo.toml
│   └── src/
│       ├── lib.rs               # PyO3 モジュールのエクスポート
│       ├── types.rs             # Python から見える Rust データ型
│       └── signal/
│           ├── filters.rs       # 信号フィルタ
│           ├── fft.rs           # FFT 振幅スペクトル
│           ├── peak_detection.rs
│           └── window.rs        # 窓関数
├── library.db                   # 参照物質データベース
├── spectrometer_rust.pyd        # コンパイル済み Windows 拡張モジュール
├── test_rust.py                 # Rust モジュールの手動スモークテスト
└── README.md
```

## Technologies Used

- **Python** — アプリケーションの制御とデスクトップ UI
- **PyQt5** — ネイティブデスクトップインターフェース
- **pyqtgraph** — インタラクティブなプロット表示
- **NumPy** — 数値配列の取り扱い
- **SQLite** — ローカル参照ライブラリ
- **reportlab** — PDF レポート生成
- **Rust** — 性能が重要な信号処理
- **PyO3** — Rust モジュールを Python から利用するためのバインディング
- **rustfft / ndarray** — Rust 側での FFT と配列処理

## Roadmap

- 科学的により妥当なピークマッチングとスコアリングの改善
- UI 上で解析パラメータをより分かりやすく設定できるようにする
- PDF レポートにプロットや処理メタデータを含める
- 再現性のあるクロスプラットフォームビルドフローの整備
- ファイル読み込み、同定処理、Rust DSP のエッジケースに対する自動テストの拡充
- 参照ライブラリの管理とバリデーションの改善

## License

本プロジェクトは **MIT License** の下で提供されています。

詳細は [LICENSE](LICENSE) ファイルを参照してください。
