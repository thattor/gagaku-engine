# gagaku-engine

[日本語](README.md) | [English](README.en.md)

平調・五常楽急を自前生成音源で演奏する開発中のプロジェクトです。実器の完全な同定ではなく、必要十分な音色と音楽的進行を目指します。現在の音声・記譜は未検証を含むプレビューで、完成版ではありません。

## 開発段階

この README は公開 `main` の実装を説明します。笙・龍笛・篳篥の自前物理音源、本体96秒を2回展開する192秒の三管候補、ブラウザ再生、候補境界での終了要求を含みます。反復と250msの減衰は作者の採用設計で、伝統的な二返・出口・止手を検証済みとするものではありません。

当初の「笙の重ね字2箇所と手移りを確定する」厳格読解タスクは `BLOCKED_PUBLIC_EVIDENCE` のままです。その後の採用解釈による試作と、原譜・奏法の完全検証は別に記録しています。本人の音楽品質評価 `U` は `UNEVALUATED` で、製品全体の `DONE = R AND M AND A AND E AND P AND U` は未達です。

開発ブランチの成果は `main` と区別してください。龍笛の旧候補に前曲末尾の列が混入していたことへの修正は、[Draft PR #13](https://github.com/thattor/gagaku-engine/pull/13) とその後続にあり、2026-10-10確認時点で未マージです。`main` の192秒候補を修正済みの演奏として扱わないでください。

## 導入

CIの基準は Python 3.12 です。音源生成は標準ライブラリを使い、権利コーパスを含む回帰検査には [requirements-dev.txt](requirements-dev.txt) のテスト用依存が必要です。

```sh
git clone https://github.com/thattor/gagaku-engine.git
cd gagaku-engine
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

## 使い方

公開 `main` の192秒候補を生成します。WAV、演奏イベント、検査結果、プレイヤーが指定フォルダに保存されます。再生成には既存成果と区別できる出力先を使ってください。

```sh
.venv/bin/python -m features.gagaku.product.three_pipe_pass --output-dir output/three-pipe-pass-v1
.venv/bin/python -m http.server 8000 --bind 127.0.0.1 --directory output/three-pipe-pass-v1
```

生成後に <http://127.0.0.1:8000/pass-player.html> を開きます。終了要求は96秒または192秒の候補境界で適用されます。再生条件・採用解釈・検査の詳細は [192秒候補の手順](docs/tasks/three-pipe-pass-v1/README.md) を参照してください。

回帰検査:

```sh
.venv/bin/python -m unittest discover -s features/gagaku -t . -v
.venv/bin/python -m unittest features.gagaku.tests.test_evaluate features.gagaku.references.test_corpus -v
```

## 制約と資料

音高・時刻・手移り・音色には未検証の採用仮説があります。テスト成功や再生成一致は、歴史的な奏法の正しさや本人の聴感受入を保証しません。完全な三管演奏、検証済みの出口・止手、5/10/20分の製品運用は未達です。新規実器測定・奏者録音は行わず、第三者録音を制作素材にしません。

- [Issue #1](https://github.com/thattor/gagaku-engine/issues/1)
- [当初の笙読解タスクの固定範囲・完了条件・停止条件](docs/tasks/SHO_READING_V1.md)
- [Codex / Agent向け入口](AGENTS.md)
- [製品全体の固定ゴール](docs/PRODUCT_GOAL_V1.md)
- [基準コードの由来と検査手順](docs/MIGRATION.md)

旧開発から限定移植したコード、譜面fixture、出典記録、テストを同梱しています。旧リポジトリの番号や過去の検査結果は由来として参照し、現行版の完了証拠と混同しないでください。詳細資料は主に日本語です。

## ライセンス

未設定です。コードと生成音声・譜面データの扱いは別途整理します。公開済みという理由だけで、収録資料を無制約に再利用できるとは表示しません。第三者の録音・音声素材は同梱していません。
