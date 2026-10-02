# 三管第1行・24秒候補

PR5（`edc50061`）を依存元として、三管の第1行P1〜P8を1主拍点3秒、24秒で一度再生する候補を追加する。PR5の冒頭5点・15秒版は保持する。追加区間はP6〜P8の既存fixtureを採用し、元画像の新しい独立照合は行っていない。

笙はPR4の連続制御を2倍の時間軸で使い、P2の引は十の継続という採用解釈を保持する。P5〜P6の同じ合竹では共通管を鳴らし続ける。第1行に工はなく、1932/1894版の工の選択はこの区間の音を変えない。龍笛・篳篥は既存候補の音高・音域・拍内配置を明示的な発音区間へ展開する。龍笛の延引を含め各既存イベントで再発音し、伝統装飾や息継ぎを確定済みとは扱わない。

出力は笙16、龍笛14、篳篥9の39発音区間と、各管8点・計24主拍点を被覆する48kHz PCM16 WAV4本（各stemはmono、合奏はstereo）。既存の自前物理モデル、A430、RMS利得と左右mix係数を使う。発音0.15秒・終端前0.25秒の減衰は自前制御である。末尾24秒は抜粋用の減衰で、止手・検証済み出口・製品Eの達成ではない。

検査は元入力と設計の一致、管別重複・旋律の隙間、全8主拍点での三管発音、非有限値・clip・無音窓・サンプル差分、PCM形状と最終sampleの0を確認する。別bankから全WAVを再生成してhash一致を要求する。数値検査は音楽的自然さや音色受入の代用ではない。

```sh
python -m unittest features.gagaku.product.test_three_pipe_prefix features.gagaku.product.test_three_pipe_line1 -v
python -m features.gagaku.product.three_pipe_line1 --output-dir output/three-pipe-line1-v1
```

出力の `three-pipe-line1-player.html` を同じフォルダで開くと合奏とstemを試聴できる。events・inspectionに出典、採用解釈、制御値、入力/音声hash、生成commitを保存する。厳格笙読解はBLOCKED_PUBLIC_EVIDENCE、完全検証済み演奏eventは0/必要総数不明、本人の80点目安とUは未評価。第三者録音・新測定・新奏者録音は使わない。製品全体のR/M/A/E/P/Uは完了していない。
