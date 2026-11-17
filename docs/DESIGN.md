# 設計メモ / Design Notes

このアプリが「なぜその作りになっているか」をまとめたメモです。
実装の正確な仕様はコードそのもの (`pass_through_gui.py`) とテスト
(`test_pass_through_logic.py`) が常に正です。

## アーキテクチャ

USB キャプチャーボード（DirectShow）の映像・音声を、ffplay を別プロセスとして
起動し、2 台目のモニター（プロジェクター）へ超低遅延・フルスクリーン表示します。
システム構成図は README 冒頭の図を参照してください。

- 映像・音声パイプライン: `ffplay` を `-fflags nobuffer -flags low_delay
  -framedrop -probesize 32k -analyzeduration 0` で起動（「低遅延(最速)」ON 時）
- デバイス列挙: `ffmpeg -list_devices` の出力を解析（マーカー形式・節ヘッダ形式の
  両対応）。同じフレンドリ名のボードが複数あっても `(1) [識別子]` の形で判別
- 表示先モニター列挙: Win32 `EnumDisplayMonitors`（ctypes 経由、追加依存なし）
- ffplay は起動失敗時に exit 0 を返すことがあるため、stderr を一時ファイルに
  取得して即終了・非 0 終了を検知し、エラー内容をダイアログ表示する
- 設定は exe / スクリプトの隣の `pass_through_gui_config.json` に保存

## 多言語化（i18n）

採用方式: **コード内埋め込み翻訳辞書**（`TRANSLATIONS[lang][key]` + `tr()` ヘルパー）。

| 案 | 判定 | 理由 |
|---|---|---|
| A. コード内翻訳辞書 | **採用** | 追加依存ゼロ・onefile exe にそのまま入る・翻訳の寄稿が 1 エントリ追加で済む |
| B. gettext (.po/.mo) | 不採用 | 標準的だがツールチェーンが必要で、単一ファイルの小型アプリには重い |
| C. 外部 JSON 辞書 | 不採用 | 同梱ファイルが増え「exe 1 つで動く」利点が崩れる |

- 既定言語は日本語 (`language: "ja"`)。不正な値・未訳キーは日本語へフォールバック
- 言語切替は UI 全体を再構築して即時反映（値の退避 → 破棄 → 再構築 → 復元）。
  再起動は不要
- デバイス名は翻訳対象外（Windows が返す名称のため）

## ライセンス方針（MIT + 開示）

- **アプリ本体（このリポジトリのソース）: MIT** — 個人・企業を問わず自由に使える
- **同梱 FFmpeg: GPLv3**（BtbN 製 win64 shared、`--enable-gpl --enable-version3`、
  バージョン `N-106550-g072101bd52-20220410`）
  - FFmpeg は別プロセス起動（aggregation）なので、アプリコードは MIT のまま
  - 配布時の GPLv3 の開示義務は [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)
    で履行（ライセンス文・同梱ビルドの識別子・Corresponding Source の参照）
- 全体を GPLv3 にしない理由: FFmpeg の開示義務は変わらないまま、自作コードの
  自由度が減るだけだから

## 配布モデル

- ソース: このリポジトリ
- exe: **GitHub Releases** で配布（onefile で約 50MB あり、git 管理には適さないため）
- 自前ビルド: `FFMPEG_BIN` 環境変数で示した win64 shared ビルドの
  `ffmpeg.exe` / `ffplay.exe` を用意し、`python -m PyInstaller --noconfirm
  --clean pass_through_gui.spec`（README のビルド手順参照）
