# 三管自前音源の実装候補

固定ゴールは [PRODUCT_GOAL_V1.md](PRODUCT_GOAL_V1.md)。この実装は実音声を生成し、三管stem・音声接続・反復／終了要求を試験する。診断入力は五常楽急ではなく、製品M/E/Uを合格にしない。

## 再生成・検査・再生

Python 3.12、標準ライブラリのみ（外部音源・API不要）。repo rootから:

```sh
python3.12 -m unittest features.gagaku.product.test_product features.gagaku.test_player features.gagaku.test_sho_one_pipe features.gagaku.test_spherical_load
python3.12 -m features.gagaku.product.audio --diagnostic --long --output-dir output/gagaku-product
python3.12 -m features.gagaku.product.verify output/gagaku-product
python3.12 -m http.server 8765 --bind 127.0.0.1 --directory output/gagaku-product
```

`http://127.0.0.1:8765/player.html` を開く。三管の短尺・別検証区間・5/10/20分のWAVを再生できる。開始ボタンは自作の四区間を初回／反復順で実音声再生し、終了要求で第四区間後の自作終了形へ接続する。実曲は原譜・止手が未検証なので拒否する。即時停止は試聴中断であり、製品の終了遷移ではない。

生成音のrawは `bank/*.raw-f64le.gz`（little endian binary64、Pa、48kHz）で、聴取用の音量とは別。管モデルは一般化したリード／ジェットの設計候補で、実器の同定ではない。笙はPR #56の同一物理生成器を変更せず使用。自己生成の定常振動32周期を位相平均した周期バンクから音高を作るため、呼吸やピッチ揺れ等の実器性は未受入。残響なし。モデル・制御・物理単位・gain・hashはmanifestとbank.jsonに保存。

## 判定の境界

- 48kHz PCM16 WAV、各管stem、raw、イベント、制御、固定seed1000終了要求ログを生成する。
- 長尺は診断入力の実音声接続検査であり、五常楽急の製品Eではない。
- 1000件は状態機械／スケジューラ検査。各要求の1000個の長尺音声を生成・再生したとは報告しない。
- #52の研究閾値・過去FAILは変更しない。数値検査で音色の用途可を判定しない。
- 制作allowlistは独立生成器・自作診断イベントのみ。NDL譜、Stanford図／音声、既存録音はこの候補に入らない。

## 楽曲の未解決点

1932三管譜と1894東儀文礼『雅楽集』の運指・合竹・拍節・手移説明を目視し、別の `score-fixture.json` から三管の冒頭30秒と笙の本体読解192秒を生成する経路を追加した。1932 canvas5–6は凡例ではなく目録/楽器図だった。原譜の具体的な位置、照合結果、未解決記号、初度/二返/止手の残件、数と権利は [score-reading.md](score-reading.md) と `score-review.json` を参照する。

```sh
python3.12 -m features.gagaku.product.score_audio --preview --output-dir output/goshouraku-score
python3.12 -m features.gagaku.product.verify_score output/goshouraku-score
python3.12 -m http.server 8766 --bind 127.0.0.1 --directory output/goshouraku-score
```

`http://127.0.0.1:8766/player.html` で再生する。読解プレビューには音域・装飾・拍内配置の未検証と、笙本体の明示された2箇所の未読がある。完成候補のUや5/10/20分の製品Eには使えない。
