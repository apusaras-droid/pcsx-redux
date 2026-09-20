# ONE解析用のPCSX-Redux環境

2026-09-20: PCSX-Redux `25477.20260919.11.x64`（changeset
`a409befe8215caeb1bdb92e5cd654f1254657b26`）と未改造SCPH-5500日本版で、
Disc 1 / SLPS-01972の最初の文章表示まで確認。
CPUはInterpreter、描画はSoftware、メモリーカード未挿入、fastboot無効。

公式BIOSのMD5は `8dd7d5296a650fac7319bce665a6a53c`。
このビルドは日本語を含むディスクパスで文字コード変換エラーになったため、
ローカルの英数字パスにディスクをコピーして使用している。

## 起動

作業フォルダーで、前のPCSX-Reduxを閉じてから実行する。

```powershell
# 観測なし
./tools/one-analysis/start.ps1 -Baseline
# BIOS入口の観測あり
./tools/one-analysis/start.ps1
```

必要なローカルファイル:

- `.tools/redux/pcsx-redux.exe` と公式配布の依存ファイル
- `.tools/redux/scph5500.bin`
- `.tools/redux-analysis/disc1/disc.cue` と `disc.bin`
- `.tools/redux/pcsx.json`（今回用意した設定）

これらのバイナリー・ディスク・ダンプ・ログはGit管理外。
初回導入用インストーラーではなく、このワークスペース用の起動スクリプト。
旧ログは起動前に `.tools/redux-analysis/archive/` へ退避する。

## 操作と取得

`observe.lua` はBIOS A0/B0/C0入口で関数番号、PC、RA、a0〜a3をCSVに記録する。
関数ごとに最初の128件、全体20000件が上限。完全な実行トレースではない。
戻り値・ファイル名・CD DMAの追跡はまだ実装していない。
関数別カウンターは総記録上限に達するまで更新する。
出力は `.tools/redux/bios-calls.csv`。

```powershell
# 一時停止してRAM・VRAM・ゲーム画面・観測状態を取得し、元の実行状態へ戻す
python tools/one-analysis/capture.py .tools/redux-analysis/new-checkpoint

# パッド入力してから取得（observe.lua起動時のみ）
python tools/one-analysis/capture.py .tools/redux-analysis/after-input --button START
```

出力先は未作成のディレクトリーを指定する。既存チェックポイントには上書きしない。
各ダンプのサイズ・SHA256、取得時刻、観測時のレジスター情報はmanifest.jsonに保存する。
パッド操作はエミュレーターのLua APIを使い、Windowsへのキー入力は行わない。

今回確認した操作順:

1. システムデータロード画面でDOWNを2回→「ロードしません」をCIRCLEで決定。
2. オープニングでSTARTを押してタイトルへ進む。
3. タイトルでSTART、メニューのSTART項目でもSTART。
4. 最初の文章「とても幸せだった…」が表示される。

## 検証済み成果物

- `.tools/redux-analysis/baseline-checkpoint/`: 観測なしのロード選択画面。
- `.tools/redux-analysis/observed-load-menu/`: 観測ありの同画面。
  この2件ではscreen.pngとvram.binのSHA256が一致した。
  RAMは取得タイミングが異なるので一致を要求していない。
- `.tools/redux-analysis/intro-checkpoint/`: 最初の文章表示のRAM 2 MiB、VRAM 1 MiB、
  画面、manifest、BIOS呼び出しCSV、エミュレーターログ。
- `.tools/redux-analysis/SLPS_019.72`: REST APIから取得した実行ファイル423936バイト。
- `.tools/redux-analysis/SYSTEM.CNF`: 起動設定。
- 名前付きセーブステート `one-first-text`。

再開例（同じゲームと公式BIOSで起動済みのPCSX-Reduxに対して）:

```powershell
Invoke-RestMethod 'http://127.0.0.1:18080/api/v1/state/load?name=one-first-text'
Invoke-RestMethod -Method Post 'http://127.0.0.1:18080/api/v1/execution-flow?function=resume'
```

ゲームの正常動作・計測の成立を確認した範囲はここまで。
全編の互換性、観測負荷による時間差、シナリオ命令の意味はまだ検証していない。
次はCDの読み込みとRAM上のデータを対応付け、文章描画・シナリオ解釈の関数を特定する。
