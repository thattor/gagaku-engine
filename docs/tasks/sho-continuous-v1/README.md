# SHO_CONTINUOUS_V1 — 採用解釈付き連続笙preview

2026-10-02本人の継続指示に基づく次段階。PR3の台帳から、本体sho.L1.P1〜L4.P8を一度だけ連続生成する。台帳整備で停止せず、聴ける候補を渡す。初度/二返・反復・止手・他管・全曲完成へ読み替えない。PRODUCT_GOAL/SHO_READING_V1/PR2/PR3の既存判定を変更しない。

## 採用と分岐

- 各1.5秒×32主拍点＝48秒。重ね字は各0.75秒の二合竹で、34名目checkpoint。文献の名目等分を秒にした自前tempo。
- PR3の6訂正（重ね字2/引4）を継承。旧25未再照合のうちL1.P2だけ、1932 c14左p17の左端譜列・第二点と1894 c30右p21の曲名後第一譜列・第二点を実画像で追加照合。旧「行」の字形を「引」と読む候補とし、直前十の持続を採用。字形確認と歴史的再発音規則の確定は別。出典画像hash/位置はsho-continuous-v1.jsonに保存する。PR3の固定版を書き換えない。
- 残る旧24セルは原fixtureの記号・管集合を未再照合の候補として使う。今回全管の元譜独立再照合・伝統調律検証をしたとはしない。
- 工L2.P3（15〜16.5秒）は、1932の下と1894の乙を2つの明示版として同条件で生成。共有5管の集合はlegacy由来で未再照合。どちらも正解版と選定しない。版差の由来は未確定。候補版ごとにchecksumを分ける。

## 奏法と物理経路

各境界の共通管は発音spanを保ち、合竹全体の切断/一律crossfadeはしない。一→乞は32.15秒に凢解除、32.25秒に一解除/乞追加、32.35秒に八追加。十→下は39.65秒に八解除、39.75秒に十解除/千・美追加。操作順は清水の現代奏法、絶対時刻・100msの前後差は自前制御。

他の境界は集合差を同時に操作する仮設計。伝統的な管別順序を推論してverifiedにしない。引5例と同合竹の継続では管を再発音しない。吸吹反転、息圧変動、実際の指孔移動音は未再現。各管は追加時刻の後.15秒でattackし、解除時刻の前.25秒でfadeして、解除時刻には0になる。清水資料の指孔操作時刻自体を測定してenvelopeを得たものではなく、自前の音量設計である。末尾のreleaseは抜粋の音量処理で、止手・合法的出口ではない。

既存Hikichi系連成reed/slit/delayの自前計算から作る定常bankを使用。PR2と同じpressure800Pa/Q35/pipe .241m/loss .98/Gaussian幅1sample/ramp .05秒のPoC仮定。自前出力foldとpitch resampling、A430平均律・同一pipe gain .035/RMS・音量gateによる制御。指孔変化を物理モデルへ動的に連成した実器モデルではない。多管の相互作用/放射音は未検証。録音サンプル・未許諾録音分析・新録音/新測定なし。

工以外のcheckpoint/control定義は同じだが、保持管のspan開始位置・位相が分岐で変わるため、工の後にもPCMの差が続き得る。比較は同条件の2連続候補であり、相違が15〜16.5秒だけに限定されるとは称さない。

## 完了条件と検査

今回のみの状態はCONTINUOUS_CANDIDATE_GENERATED。WAV2版、明示した採用/仮定とsource付きcheckpoint/control/span、再生成/hash、数値/PCM/被覆/重複/拒否検査、独立レビュー、exactHEAD CI、Library納品を揃える。本人の80点評価は未実施として独立実装を止めない。完全検証event0/必要総数不明、厳格読解BLOCKEDを維持する。

```sh
python -m features.gagaku.product.sho_continuous --output-dir output/sho-continuous-v1
python -m unittest features.gagaku.product.test_sho_continuous -v
```

34checkpointは名目合竹数、pipe span件数は自前実装の発音区間数で、伝統演奏event完成の分母ではない。checkpointの連続48秒被覆、各名目中点の管集合、共通管の保持、操作順、duplicate/NaN/出典欠落/verified昇格拒否を検査。WAVはmono48kHz PCM16、2304000frames。float/PCM full-scale0、独立bank再計算からPCM hash一致、内部100ms windowの意図しない無音0を確認。peak .6/|DC| .005/sample差 .2/内部windowRMS 1e-5は作者の数値sanity条件で、音楽品質PASSではない。

イベント束には全checkpointの原譜位置、候補読解・追加字形照合・現代奏法・版差の採用根拠を残す。CI artifactにWAV/player/events/inspectionを保存。PR4は未merge PR3のbranchをbaseにする。merge/release/外部サイト公開なし。音色受入、曲全体・三管・長尺実曲運用・ユーザーUは引き続き未完了。
