# 三管本文4巡・384秒候補

統合済みmain `95cfb1fa3545588e750e59b2d4ff7418fb6cb98a` のPR9候補に依存する。未統合PR10には依存しない。既存96秒本文の4巡を自前物理モデルから連続生成し、笙の共有管は境界を越えて保続する。音声ファイルの連結ではない。

初回と後続回の唱歌採用、1932年/1894年の採用解釈、音高、3秒主拍、A430、gain、attack/releaseは既存候補を維持。伝統的二返、入口、真正止手、検証済み出口を新しく成立させる変更ではない。全イベントの演奏 verified はfalse、厳格読解 BLOCKED_PUBLIC_EVIDENCE、聴感 UNEVALUATED。

終了要求は96/192/288/384秒の自前境界を選ぶ。減衰開始0.25秒前までに要求したとき当該境界、それより遅ければ次の境界。末尾は自前人工減衰。5分以上の全本文再生を可能にする運用試作であり、製品Eのverified出口・止手条件やUをPASSにしない。

```sh
python3 -m unittest features.gagaku.product.test_three_pipe_long -v
node features/gagaku/product/test_long_player.cjs
python3 -m features.gagaku.product.three_pipe_long --output-dir output/three-pipe-long-v1
python3 -m http.server 8768 --bind 127.0.0.1 --directory output/three-pipe-long-v1
```

`http://127.0.0.1:8768/long-player.html` でhash確認済み384秒合奏を再生し、終了要求と運用記録保存を使う。PCM48kHz16bit合奏、三管stem、96秒早期出口比較、event/span、固定seed1000件以上の要求、接続/PCM/再生成検査を保存。ブラウザ実再生と状態機械試験は別証拠として扱う。新規実器測定・奏者録音・第三者録音利用・ライセンス変更はない。

ブラウザはAudioContext描画時計の要求に0.10秒の予約余裕を加えて候補を選ぶ。CLI純計画の締切とブラウザ操作の有効締切は区別する。途中出口の末尾PCMフレームをゼロにするgain ramp、全384秒末尾の生成済み発音envelopeを区別し、origin/要求時計/遅延/予約余裕を運用ログへ保存する。
