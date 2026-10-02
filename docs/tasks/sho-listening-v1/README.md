# SHO_LISTENING_V1 — 短い比較試聴候補

2026-10-02 本人が、Issue #1コメント5941480847・5941780473の方針に続く短い自前生成を承認した別範囲。SHO_READING_V1はBLOCKED_PUBLIC_EVIDENCEのまま。完全検証演奏eventは0、必要総数は不明。旧fixture、過去FAIL/UNVALIDATED/UNVERIFIED、厳格完了条件、rights/statusを変更しない。

目的は本人が聞こえ方を判断できる最小成果。80/100前後は暫定の主観目安で、未評価・未達成。測定一致80%でも自動PASSでもない。今回の状態はLISTENING_CANDIDATE_GENERATED。全曲・他楽器・正式な終了・古典奏法完全再現ではない。

## 音の並び（両ファイル18秒、非連続抜粋の編集）

| 時間 | 元位置 | 基準 | 修正版 |
|---|---|---|---|
| 0–6秒 | L3.P5→P6 | 一3秒→未読3秒の無音 | 一3秒→一1.5秒→乞1.5秒、共通管保持 |
| 6–12秒 | L4.P2→P3 | 乞3秒→未読3秒の無音 | 乞3秒→十1.5秒→下1.5秒 |
| 12–15秒 | L2.P5→P6 | 一1.5秒→行1.5秒 | 一を3秒持続 |
| 15–18秒 | L4.P5→P6 | 乙1.5秒→行1.5秒 | 乙を3秒持続 |

同一物理bank、同一管gain・調律・envelope。baselineは凍結fixtureの当該読解をこの短い時間配置で再現した比較基準であり、旧192秒WAVそのものの切り出しではない。個別修正の効果を分離する実験ではなく4抜粋全体の比較。抜粋間には編集上の境界がある。

## 一次資料と今回の限定確認

- 1932 NDL1192407 c15右・印刷18と1894 NDL855853 c30右・印刷21を実画像で閲覧。L3.P6は一/乞、L4.P3は十/下。赤線を一の画に含めない。L2.P6/P8とL4.P6/P8の4字は引の字形で、直前P5/P7はそれぞれ一/乙。各版の該当譜列・主拍点で照合（位置と画像hashはsources.json）。
- この字形確認は引の全歴史用法、再発音規則、全管操作時刻を保証しない。現代奏法採用の今回では、Momii Example21の一・乙の継続との既存独立照合を支持資料として持続案を選択。音声はP6の2例のみ、P8の2例も字形を限定確認したが追加音声を作らない。
- 1932 c7右印刷2の工は右食指「下」。1894 c11右の工は乙黒点/下白点を実画像で確認。差の理由は未確定。今回の抜粋に工はなく、どちらも音源に混用しない。
- 採用奏法はChatori Shimizu “Shō: Composer’s Guide” §4の現代手移り。一→乞は凢を先に解除、一解除/乞閉鎖を同時、八は後の気替位置で閉鎖。十→下は八を先に解除、十解除/千閉鎖/美閉鎖を同時。共通管を維持。字形と合竹順は歴史譜、操作列はこの現代資料として区別し、1932の全手順とは称さない。
- Momii (2020) §8注32の二合竹の名目等分を採用。Example21(a)第22小節ichi→kotsu、第27小節jū→geはIssue5941780473の原譜例独立確認を引用し、今回の新しい五線譜独立確認とは数えない。21(b)は9–26小節まで。

## 設計値・未確定事項

3秒/主拍点、重ね字の各1.5秒は試聴用の秒換算。凢解除4.3秒→一/乞交換4.5秒→八追加4.7秒、八解除10.3秒→十/千/美交換10.5秒は自前指定。気替の絶対秒数、吸吹の圧力反転・管内残響・微細な指孔移動は未測定/未再現。乞→十と抜粋間接続は資料で認証した手移りではない。

各管のattack .15秒/release .25秒は音量制御設計。同時操作は同時の制御時刻であり、envelope中には出力の重なりがある。共有管は同一spanで保持し、全合竹の一律crossfadeに置換しない。A430の12平均律近似・各管同一音色/同一gainは既存設計で、伝統調律の測定値ではない。

Hikichi et al. (2003), DOI10.1121/1.1534605の連成reed/slit/delayを計算する既存sho_one_pipeを使用。圧力800Pa、Q35、loss .98、Gaussian幅1sample、pipe .241m、pressure ramp .05秒は既存PoC仮定。自前出力の定常部分をfoldしpitch resamplingする既存経路。外部録音・サンプルは一切入力しない。多管の相互作用・放射伝達・実器一致は未検証。録音利用権確認待ちは維持し、新測定/新録音なし。

## 再生成・検査

```sh
python -m features.gagaku.product.sho_listening --output-dir output/sho-listening-v1
python -m unittest features.gagaku.product.test_sho_listening -v
python -m unittest discover -s features/gagaku -t . -v
python -m unittest features.gagaku.tests.test_evaluate features.gagaku.references.test_corpus -v
```

34管span/版はこのmontageのスケジューラ件数であり完全検証event分母ではない。inspection.jsonに入力/code/WAV hash、finite/peak/rms/full-scale、最大sample差、独立bank再計算でのPCM一致、基準との差RMSを出力。PCM writerはfull-scale/NaNを拒否。追加検査は操作順・同期/共通管保持・引の持続・未知位置保持・不正時刻/重複/verified昇格拒否。独立レビューでassert依存の保証を明示拒否へ修正。

CIは生成WAV・events・inspectionをartifact保存する。exact HEADのCI結果・Library IDはIssue/PRの追記に記録。音量は両版同一gainで、修正版は無音を埋めたため全体RMSが増える。音色受入・本人試聴・80点到達をテストから推論しない。merge/release/外部サイト公開はしない。
