# 三管の音量を調整する試聴プレイヤー

main `95cfb1fa3545588e750e59b2d4ff7418fb6cb98a` の192秒試作を、三管の音量を個別に調整して比較できるようにする。R/M/A/E/P/UのうちPの編集・保存・再生成を進める独立段階。譜面、初度の採用解釈、音高、テンポ、元stem、物理モデルを変更しない。伝統的な二返・入口・出口・止手、厳格読解、聴感の検証には算入しない。

各管0〜150%を再生前に指定し、再生中は固定する。0%は明示した消音で、三管すべて0%なら再生・保存を止める。笙だけ／旋律だけの聞こえ方も比較できる。音量は作者の試聴制御であり、測定した演奏音量ではない。本人が毎回聴くことを開発の条件にしない。

## PCMと保存

三管の承認済み192秒PCM16 stemだけを入力にする。PR9/mainで検証したMac/LinuxのSHA256を固定し、自己申告manifestの差し替えでは任意の録音を取り込めない。出典実装17ファイルのhash、元WAV形式・hash・末尾0、候補の未検証状態を確認する。新規録音、第三者録音の解析、外部送信、新しい依存はない。

左右係数は既存合奏と同じ笙70/70、龍笛85/50、篳篥50/85（各100分率）。各管の音量%を掛け、PCM整数の加重和を10000で割る。最も近い整数へ丸め、ちょうど半分は0から遠い側に丸める。PythonとJavaScriptでこの規則を共通化し、WAVも同じ44byteヘッダーで書く。

音量範囲の安全性は実PCMの各管絶対peakから左右別に三角不等式で検査する。全管150%でもこの上限がfull scale未満でなければプレイヤーを有効化しない。局所的な位相相殺に頼らず、許可したすべての設定でクリッピングを防ぐ。波形をclampして問題を隠さない。

元合奏は物理計算後のfloatから直接PCM化されている。一方、本段の合奏は保存済みPCM stemから再構成するため、基準100%でも元合奏と最大2 LSBの量子化差を許容する。元合奏を置換せず、新しい調整版として保存する。同じ環境・stem・設定なら再生成WAVはbyte一致。ブラウザの整数PCM/WAV出力とPythonも実192秒でbyte照合する。Mac/Linux stem自体に最大1 LSB差があるため、環境をまたぐ無条件のbyte一致を保証しない。

「音量設定を保存」は3値と候補状態のJSONを保存する。「この音量のWAVを保存」は同じ整数計算による192秒全体を保存する。ブラウザの終了要求による早期96秒停止は、そのWAVには反映しない。演奏結果ログには実際に再生した音量と停止frameを残す。

既存PassOperationを使い、終了要求は全0.25秒の減衰を確保できる96/192秒候補境界へ進む。新しい出口・止手を作らない。`verified_exit=false / tomede=false / traditional_nihen_verified=false / BLOCKED_PUBLIC_EVIDENCE / UNEVALUATED`を保持する。

## 再生成と利用

初回に既存の自前生成stemを作る。既存の同一成果を保存済みなら、最初のコマンドを繰り返す必要はない。

```sh
python -m features.gagaku.product.three_pipe_pass --output-dir output/three-pipe-pass-v1
python -m features.gagaku.product.three_pipe_balance --source-dir output/three-pipe-pass-v1 --output-dir output/three-pipe-balance-v1
python -m http.server 8767 --bind 127.0.0.1 --directory output
```

`http://127.0.0.1:8767/three-pipe-balance-v1/balance-player.html`を開く。保存したJSONをCLIへ指定すると同じ音量で再生成できる。

```sh
python -m features.gagaku.product.three_pipe_balance --source-dir output/three-pipe-pass-v1 --settings balance-settings.json --output-dir output/balance-restored
python -m unittest features.gagaku.product.test_three_pipe_balance -v
node features/gagaku/product/test_balance_player.cjs output/three-pipe-balance-v1
```

成果は調整版合奏WAV、変更のない三管stem、設定JSON、元演奏commit/入力hashとPCM検査、プレイヤー。元演奏のevent/発音spanは元生成フォルダに保持する。ライセンスを追加せず、試作音源を正式releaseや製品DONEとして扱わない。
