# SHO_ADOPTION_V1 — 次の最小段階：読解データ整合

2026-10-02「18秒版で止めず継続」の本人依頼に基づく別scope。PR2の採用解釈を機械可読にまとめ、旧転記のverifiedを後続処理が無条件に継承することを防ぐ。SHO_READING_V1の厳格完了はBLOCKEDのまま、U/80点評価も未実施。試聴回答をこの独立実装の前提にしない。

今回の完了条件：32主拍点すべてを一意なIDで出力、訂正6セルと工の版選択待ち1セル・その他25セルの継承境界を区別、出典と旧記号を保持、不正昇格/版混用/前後関係/音高・出典不整合を拒否、PR2の音声制御を保った接続、回帰/独立レビュー/exactHEAD CI成功。完成曲生成・三管完了・製品DONEは今回の完了条件ではない。

`features/gagaku/product/sho-adoption-v1.json` は1932/1894の字形確認に対する現代奏法候補の明示版。6訂正は一/乞・十/下と引4例。重ね字は2 checkpoint/セル（各1/2）、引は直前P5/P7の一/乙を継続する候補（再発音規則の歴史的認証ではない）。pipe MIDI/合竹集合はPR2の既存候補を継承し、検証済み伝統調律へ昇格しない。

工L2.P3は右食指の下/乙の版差のみ画像確認済み。共有管は既存fixture由来・独立再照合未実施で、候補集合全体を新たにverifiedにしない。採用版は未選択、生成用chord_pathはnull。32セル中残り25も旧記号/管集合をlegacy欄に保持するだけで、現在の検証済み管操作として返さない。旧notation/pitch verifiedはlegacy_claimsに隔離する。

`sho_adoption.build_body()` は基準fixtureのbyte hash、ID被覆、6訂正のv1セル/記号/path/先行ID、一次出典、名目分割、MIDI対応、版差候補を検査する。v1内容の変更は別の明示的版とレビューが必要。基準fixtureを変更・置換しない。全演奏event必要総数はnull、完全検証event0、full_body_synthesis_ready=false。32/6/25はデータ整合の件数で、曲完成の分母ではない。

`sho_listening` はこの明示版から合竹とMIDIを読み、訂正側はbuild_bodyの基準/版整合確認を通る。基準比較側の行はfrozen_baseline_comparison、訂正側はcorrected_candidateをevent出典に記録。PR2のpipe/MIDI/start/end全制御値を固定回帰として照合し、音色・時刻をこの変更で調整しない。CIではPR2同じ18秒音の再レンダーhash一致を検査し、新しい全曲試聴候補は生成しない。

```sh
python -m features.gagaku.product.sho_adoption --output-dir output/sho-adoption-v1
python -m unittest features.gagaku.product.test_sho_adoption -v
```

CI artifactは32セルのsho-body-adoption.jsonとsource/input/output hash付きinspection.json。後続はこの台帳から、工の採用版を明示し、残る管操作/初度・二返/他管/止手をそれぞれ限定した版で接続できる。これらの未完了は今回のデータ整合を止める本人判断blockerではない。音色受入は本人試聴待ち、実装は進められる。新規測定・新奏者録音・未許諾録音解析なし。PR2未mergeのため本PRはPR2をbaseにしたDraftの積み上げ。merge承認は取得していない。
