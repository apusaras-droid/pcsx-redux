# OpenBIOSとPC連携

このフォークで追加したのは、起動・EXEロード・エラーのレベル付きログです。
プログラム転送、GDB、PCファイルアクセスは、まずPCSX-Redux既存機能を利用できます。

| 目的 | 既存機能 | 対応する場所 |
| --- | --- | --- |
| 実行ファイルをロード | `-loadexe game.ps-exe` | PCSX-Redux側 |
| ブレーク・ステップ実行・レジスタ確認 | `-debugger -gdb` とGDBクライアント | PCSX-Redux側 |
| PCファイルの読み書き | `-pcdrv -pcdrvbase <directory>` とPCdrv API | エミュレーター側とPS1プログラム側 |
| 起動・ロード・エラーログ | `LOG_LEVEL=3`、`-stdout -logfile openbios.log` | このフォークとエミュレーター側 |

PCdrv APIは `../common/kernel/pcdrv.h` の `PCinit`、`PCopen`、`PCread` などです。
PS1プログラムがこのAPIを呼び、エミュレーターがBREAK命令を処理します。
通常のBIOS `open("pcdrv:...")` がこの変更だけで使えるようになるわけではありません。

Sony開発機については、DTL-H2000由来のコンソールドライバーが
`tty/tty.c` にあり、上流READMEには `INSTALL_TTY_CONSOLE=true` が記載されています。
これは市販PS1の汎用シリアルドライバーとは別のものです。
また、DTL-H2000のPCファイルサーバー用BREAKや開発ボードのメモリ転送・
デバッグ通信は下記資料に記述されています。

市販実機向けの転送・デバッグ・ファイルサービスを追加する場合は、
対象本体と通信ハードウェアを決め、実機側モニターとPC側ツールを実装する必要があります。
今回のログバックエンドはPCSX-Reduxのデバッグポートを使用します。

## 資料

- [PCSX-Redux CLI](https://pcsx-redux.consoledev.net/cli_flags/)
- [PCSX-Redux GDB](https://pcsx-redux.consoledev.net/Debugging/gdb-server/)
- [PSX-SPX BIOS PC File Server](https://psx-spx.consoledev.net/kernelbios/)
- [PSX-SPX Dev-Board Protocol](https://psx-spx.consoledev.net/psxdevboardprotocol/)

## 検証

`tests/test_logging.py` はホストCコンパイラーでレベル0〜4の出力と、
無効化されたログ引数に副作用がないことを検証します。

```sh
python tests/test_logging.py
```

ROMの実行確認にはPCSX-Reduxで通常起動、ゲーム起動、EXE不存在、
短いEXEヘッダーなどを試し、ログと起動動作を確認してください。

初回実装ではGCC 14.2.0（mipsel-none-elf）で `LOG_LEVEL=0` のRelease、
`LOG_LEVEL=3` と `LOG_LEVEL=4` のSmallDebugをビルドしました。
いずれも512 KiBのROMを生成でき、ホストテストも通過しています。
エミュレーター上のゲーム起動と実機での動作は未検証です。
