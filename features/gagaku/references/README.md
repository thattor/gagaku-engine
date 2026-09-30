# 雅楽 参照コーパス メタデータ v0.1

Issue #55。三管（笙・篳篥・龍笛）の system identification / real-vs-real baseline / 音響・知覚的妥当性検証のための参照資料を、権利境界付きで管理する。**このディレクトリには録音データ・論文本文・図表そのものは一切含まない。**含むのは出典・権利区分・許可状態を記すメタデータのみ。

## 正本と責任

- 契約: `corpus.schema.json`（JSON Schema Draft 2020-12）。
- 初期データ: `data/reference-corpus.v0.1.json`。
- 読取り検証: `validation.py` の `load_corpus()` / `validate_corpus()`。
- 回帰試験: `test_corpus.py`（`.venv/bin/python -m unittest features.gagaku.references.test_corpus`）。

この機能は参照資料の**出典・権利・許可状態**だけを管理する。物理音源モデル自体の実装、実際のパラメータ抽出、音声ファイルの保存先はここに含めない。

## 権利区分

`rights_category` は次の3値のいずれか。

| 値 | 意味 |
| --- | --- |
| `public_domain_production_usable` | 出典がパブリックドメイン、または権利者が明示的に製品利用を許諾している |
| `analysis_only` | 引用・内部分析目的の参照は可能だが、製品向け音声・派生物の生成には使えない |
| `unclear_or_prohibited` | 権利が未確認。確認が取れるまで分析・製品利用いずれも既定で不許可 |

`analysis_permission` / `production_permission` は `granted` / `not_granted` / `unknown` のいずれか。スキーマは `rights_category` が `public_domain_production_usable` でない限り `production_permission: granted` を拒否する（既定拒否）。`raw_audio_included` は全レコードで `false` に固定され、音声データそのものをこの契約内に埋め込むことをスキーマ上禁止する。

## 現在収録している参照 (v0.1)

- `sho-ichi-hikichi2003`: 笙の名管「一（いち）」を単音で扱った参照。出典は T. Hikichi, N. Osaka, F. Itakura, "Time-domain simulation of sound production of the sho," *Journal of the Acoustical Society of America*, vol. 113, no. 2, pp. 1092-1101, 2003。
- `sho-ensemble-freesound-680565`: [Freesound の神社婚礼の録音](https://freesound.org/people/gaijinbuzz/sounds/680565/)を候補として記録。投稿者は CC0 1.0 と表示しているが、篳篥との合奏であり、人声・足音も入る。管・音高・奏法が不明なので笙「一」B4 の実録音基準には使えない。演奏者や映り込んだ声の第三者権利も未確認のため、分析・製品利用の許可は既定拒否とする。

論文エントリは笙1管の実測値を評価へ渡すためのもの。DOIと「一」管 B4 483.7 Hz は [PubMed PMID 12597202](https://pubmed.ncbi.nlm.nih.gov/12597202/) と[著者公開本文](https://www.researchgate.net/publication/10891514_Time-domain_simulation_of_sound_production_of_the_sho)で2026-09-30に照合した。録音の利用権限は未確認。

## 不足データ・未確認事項（正直に明示）

- **笙「一」の音声本体が存在しない**: 上記論文は測定値と図を掲載するが、再利用可能な生録音・波形データは確認できなかった。このリポジトリにも含めない。Freesound 候補も単管録音ではない。録音を分析に使うには入手元と許諾の確認が必要。
- **real-vs-real baseline が未整備**: 現状、同一の管・同一音高・同一奏法について独立な2件以上の実録音が存在しない。real-vs-real（実録音同士）のばらつきを基準化するには、最低でも別演奏者・別収録環境による2本目の参照が必要。今回のv0.1はこの不足を埋めていない。
- **出典と録音権利は別**: DOI `10.1121/1.1534605` の書誌と論文中の実測値は照合済み。ただし、著者公開本文には著作権表示があり、音声・図表の再配布や製品利用の許可を意味しない。
- **篳篥・龍笛の参照が皆無**: 三管への拡張を見込んだ `instrument` enum（`sho` / `hichiriki` / `ryuteki`）は用意したが、今回は笙のみ。篳篥・龍笛のエントリ追加が次の不足。
- **権利者への確認未着手**: JASA/AIP・著者への許諾確認は行っていない。`analysis_permission: "unknown"`、`production_permission: "not_granted"` は確認前の既定拒否であり、許諾済みという意味ではない。

## 拡張方法

1. `sources` に出典を追加する（`kind` / `citation_text` / `doi` / `doi_verification_status` / `publisher_or_venue` / `retrieved_on` / `primary_source_rechecked` が必須）。
2. `entries` にレコードを追加し、既存の `source_ref` を参照する。`instrument` は `sho` / `hichiriki` / `ryuteki` から選ぶ。
3. `validate_corpus()` で参照整合性・重複ID・既定拒否ルールを確認する。実際の権利確認・DOI照合はこのスキーマ検証の範囲外であり、別途人手で行う。

## 検証契約

- JSONの重複キーを拒否。全 `entry_id`、`sources` のキーはそれぞれ重複不可。
- `entry.source_ref` と `evidence.source_ref`（非null時）は `sources` に存在するIDを参照すること。
- `raw_audio_included` は常に `false`。`true` を設定するとスキーマ違反になる。
- `rights_category` が `public_domain_production_usable` でない場合、`production_permission: "granted"` は拒否される。
- 形式検証だけでは、出典の真正性・DOIの実在・権利者の許諾内容までは保証しない。

スキーマ検証はメタデータの整合性だけを確認する。録音の権利確認と real-vs-real baseline は未完了。
