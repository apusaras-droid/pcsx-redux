# ONE解析用のPCSX-Redux環境

CDの名前・配置・シナリオ対応表の調査は
[設計の手がかり](../../docs/one-disc-design-clues.ja.md)を参照。
文章と命令の混在形式、INITの解読は
[スクリプトの確認結果](../../docs/one-script-evidence.ja.md)を参照。
状態の保存・復元については[内部レコードの調査](../../docs/one-save-state-layout.ja.md)を参照。
シナリオから抽出した操作・参照と保存位置の対応は
[フラグ対応表の調査](../../docs/one-flag-map.ja.md)を参照。
確認済みの流れは[部分フローチャート](../../docs/one-flowcharts.ja.md)で確認できる。
本編のみを対象とした[シナリオ収集範囲の再確認](../../docs/one-scenario-coverage.ja.md)も参照。
[選択肢命令0x11・0x20の確認](../../docs/one-choice-instructions.ja.md)も追加した。

## 統合イベントログ

`start.ps1`の通常起動で`observe.lua`から`trace.lua`も読み込む。
ゲームをロードし、一時停止した後に有効化する。SLPS-01972の6か所の命令語を
照合し、不一致なら開始を拒否する。この版のInterpreter専用。

```powershell
Invoke-RestMethod -Method Post 'http://127.0.0.1:18080/api/v1/lua/one-trace?action=start&pause_choice=1'
Invoke-RestMethod -Method Post 'http://127.0.0.1:18080/api/v1/execution-flow?function=resume'
Invoke-RestMethod 'http://127.0.0.1:18080/api/v1/lua/one-trace-status'
# 停止
Invoke-RestMethod -Method Post 'http://127.0.0.1:18080/api/v1/lua/one-trace?action=stop'
```

`pause_choice=1`は各選択命令0x20へ入った時に停止する。同じ選択肢で再開しても
停止を繰り返さず、決定後に次の選択肢で停止する。省略すれば停止しない。
ログは `.tools/redux/scenario-trace.jsonl`。同一セッションの連番・epoch・CPUサイクルを持つ。
ステートをロードする前にstopし、ロード後にstartすること。新しいepochになり、
巻き戻し前後の状態差分を混ぜない。ログは再起動前にstart.ps1が退避する。

- `command`: 場面名、シナリオ位置、命令。連続する同一位置の待機は省略。
- `input`: one-pad経由の入力。物理パッド入力そのものの記録ではない。
- `choice_text`, `choice_begin`, `choice_result`: 項目のCP932バイト、項目数、結果変数と値。
- `state_change`: フラグ32バイト・数値20バイトの前後差分。観測点間の変化であり、
  一時的な書込みすべてや、厳密な変更元PCを記録するものではない。
- `branch`: 条件結果と予定移動先。次のcommandで実際の移動先を照合できる。
  複合条件のlhs/rhsは最後の比較のみ。
- `snapshot_begin/ready`: 内部レコード構築と完了時の128バイト・チェックサム。
- `restore_begin/return`: ゲーム側復元関数への出入り。
- `card_call/return`: 特定のゲーム側カード転送呼出しと戻り値。
  非同期カード処理の完了やカード上の全書込みを証明しない。
- `bios_io`: A0の00〜04、B0の32〜36のファイルI/O入口と引数。

最大30,000行で自動無効化。Lua例外もtrace_errorを出して無効化する。
ゲーム・BIOSのRAMやROMを書き換えず、観測にはブレークポイントを使う。
戻り位置の一時ブレークポイントは各種1件までなので、再入可能な一般トレーサーではない。

### 実機能の検証結果

エミュレーター内の冒頭2択を同じ直前状態から両方選んだ。

| 操作 | 変数16 | 比較結果 | 実際の次命令 |
| --- | --- | --- | --- |
| 上の項目を決定 | 1 | 成立 | NV30 +0x401 |
| DOWNで下へ移動して決定 | 2 | 不成立 | NV30 +0x465 |

両方で後続の内部レコードの変数16も一致し、チェックサムも一致した。
冒頭進行中8回と、分岐後2回のsnapshot_readyでチェックサム一致、trace_errorなし。
検証ログ: `.tools/redux-analysis/trace-intro.jsonl` と `trace-choices.jsonl`。
選択前のエミュレーター用保存状態: `one-trace-choice`。
カード未挿入のため、カードI/O・ゲーム内ロードの新フックは実動作未検証。

```powershell
python tools/one-analysis/check_trace.py .tools/redux-analysis/trace-choices.jsonl --verify-opening
```

## 選択肢を保存する解析用オートプレイ

`autoplay.py`は一つの選択地点から各項目を試し、それぞれ次の選択地点まで進める。
総当たりの全編攻略ではなく、選択結果の比較と次回解析の開始地点を作る実験。
通常のstart.ps1で起動したInterpreterと、この版のtrace.luaが必要。

```powershell
python tools/one-analysis/autoplay.py .tools/redux-analysis/new-autoplay --seed one-trace-choice --seconds 150
# 保存した次の選択地点を、過去の選択履歴ごと再利用
python tools/one-analysis/autoplay.py .tools/redux-analysis/new-autoplay-next --seed-checkpoint .tools/redux-analysis/autoplay-first/item-1/checkpoint.json --seconds 150
```

出力先は未作成ディレクトリー。`--seconds`は各分岐の進行時間上限（1〜600秒）。
文章送りは既知の待機命令0x16/0x17でのみ行う。Luaが選択命令で止めるため、
通常の文章送りで選択肢を自動決定しない。選択は実験側が明示的に行う。
次の選択肢、時間上限、同一命令での停滞、トレース停止、予期しない一時停止で
進行を止め、正常にAPIへ接続できる場合はその地点を保存する。
エンディングの自動判定や状態の等価性による探索省略はまだ実装していない。

各地点に`checkpoint.json`、`state.sstate`、`ram.bin`、`screen.png`、`trace.jsonl`を保存する。
JSONには親の保存名、選択履歴、場面・位置、変数・フラグ、ハッシュを含む。
`run.json`にはBIOS・実行バイナリー・設定・解析スクリプトのハッシュ等を保存する。
選択肢の文章はログにchoice_textがあれば添付し、ない場合はnull。
RAMのdisplay_rowsには古い文章の末尾が残る場合があり、正確な項目名として扱わない。
画面と生バイトも保存し、表示状態を確認できるようにする。

セーブ名は実行ごとのランダムIDを含み、既存の単一スロットを上書きしない。
エミュレーターが参照する状態は`.tools/redux/SLPS01972/`に残し、出力先にも複製する。
`--seed-checkpoint`ではエミュレーター側の状態ファイルのハッシュを照合する。
別PCへ移す際の自動復元や、異なるエミュレーター版の互換性は保証しない。
メモリーカードを使った原作セーブとは別の仕組み。

ログの30,000行上限は維持する。到達したら停止して保存し、無制限にログを増やさない。
エラー時も入力を解除して一時停止する。開始前の状態もbeforeとして保存する。

### 今回の結果

`.tools/redux-analysis/autoplay-first/`に、開始前・冒頭2択・各項目の先を保存した。
冒頭の各項目を選んだ2経路とも、次の選択命令NV30 +0x633へ到達。
その地点で変数16が1と2に分かれていたため、別の状態として保持した。
root・item-1・item-2を再ロードし、2 MiBのRAMが保存時のSHA256と全て一致。
検証結果は同フォルダーの`restore-validation.json`。

さらに`autoplay-reuse-check/`ではitem-1の保存状態を再利用し、両項目を選択。
1秒の進行上限で停止・保存する動作と、親からの選択履歴の引継ぎを確認した。
NV30 +0x67Dと+0x723に分かれた。長時間の全編動作は未検証。

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
その後のシナリオ解析結果は[根拠付きメモ](../../docs/one-scenario-findings.ja.md)を参照。

## シナリオ資源の検証

標準PythonだけでMODE2/2352のISO一覧と冒頭資源の展開・RAM照合を行う。
`verify_scenario.py`のオフセットは今回のDisc 1専用。別版や別場面のRAMは対象外。
出力にはゲーム由来のデータを含むため、ローカルのGit管理外フォルダーを使う。

```powershell
python tools/one-analysis/disc.py .tools/redux-analysis/disc1/disc.bin .tools/redux-analysis/disc-inventory.json
python tools/one-analysis/verify_scenario.py .tools/redux-analysis/disc1/disc.bin .tools/redux-analysis/intro-checkpoint/ram.bin .tools/redux-analysis/new-scenario-check
python -m unittest discover -s tools/one-analysis -p test_lzss.py
```

RAM一致に失敗した場合も検証JSONを残し、終了コードを非ゼロにする。
ISOリーダーは単一トラックの通常ファイル用で、XA音声やForm2動画のデコーダーではない。

`observe.lua`は狭いRAM領域のRead/Write/Exec監視にも対応する。
アドレスは16進数、幅は10進数、最大4096バイト。最大512イベントで自動解除する。
再設定すると前の監視は解除され、同じCSVに区切り行を追記する。

```powershell
Invoke-RestMethod -Method Post 'http://127.0.0.1:18080/api/v1/lua/one-watch?address=800ea720&width=1024&type=Read'
Invoke-RestMethod 'http://127.0.0.1:18080/api/v1/lua/one-watch-status'
```

出力は `.tools/redux/memory-watch.csv`。実行を止めずにPC・アクセス先・
レジスターを記録するため、各イベント時点の完全なRAMスナップショットではない。
