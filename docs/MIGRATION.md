# 新repoで作業するための基準移植

## 位置付け

所有者から「新repoで使用できるようにプロンプトと準備を変更」と指示があり、その後に今回の対象が「笙の重ね字2箇所と手移りだけ」と明示された。このため旧計画の実曲E2E成立待ちではなく、既存実装の非挙動変更コピーを先に行う。移行タイミングの変更であり、未検証イベントの合格認定ではない。

作業の入口は本repoのIssue #1と `docs/tasks/SHO_READING_V1.md`。旧PR #60 / Issue #59は履歴と由来。今回のコード変更・PR・結果は新repoに記録する。旧repoの開発中branch・過去PR・データは削除・変更していない。

## 起点と対象

- 出典: `thattor/1pjinja` PR #60、commit `96223889106fa98c85a52d2f08ba8d04f186fb9d`。
- `features/gagaku/` の47個のテキスト/コードと、汎用の `app/json_documents.py` のみを限定コピーする。業務app本体を依存先にしない。
- Git全履歴、その他の業務コード、DB、認証、ログ、個人情報、秘密情報、第三者録音・音声素材・PDF・画像のバイナリは移していない。
- 既存コードのパス・内容を保ち、移行元との全48ファイルのbyte一致を確認した。各hashは `docs/migration/source-manifest.json`。初期化ファイル、test依存定義、CI、引継ぎ文書はこのrepo用の追加。
- 旧 `features/gagaku/product/PRODUCT_GOAL_V1.md` は原本hashを維持する。`docs/PRODUCT_GOAL_V1.md` は公開用整理版でhashは別。どちらも全体ゴールであり、今回の範囲を拡張しない。
- 従来の文書内の #50/#52/#53/#54/#55/#59/#60/#61 は旧repoの番号。

## 新repoだけで開始する

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s features/gagaku -t . -v
.venv/bin/python -m unittest features.gagaku.tests.test_evaluate features.gagaku.references.test_corpus -v
```

音源生成は標準ライブラリを使用する。jsonschemaは既存の権利コーパス回帰検査の依存。`app/json_documents.py` はその検査で使う汎用JSON検証だけで、旧repoのDB等には依存しない。

原譜取得先、画像hash、調査箇所と候補は `features/gagaku/product/score-sources.json` / `score-reading.md` にある。旧repoの閲覧権限がなくても、保存済みのコードと出典情報から作業できる。原譜サイトへの実アクセス可否は実行環境で別に確認する。

## 検証状態

今回実行した準備検査は `docs/migration/preparation-checks.json` に記録する。基準移植の回帰CIは `Baseline regression`。これは笙の未読箇所を解決した検査ではない。今回のCodexタスクでは、既存検査に加え笙event対応・手移り・stem生成とartifact保存のCIを追加する。

旧 `score-evidence.json` の音声hash/試験/ブラウザ記録は過去の証拠であり、新repoでその音声の再生成や聴感検証を実施済みとはしない。新repoでの基準音声hash再比較も未実施で、移行の全検証完了や製品完了とは報告しない。

未読2箇所、手移り未検証、製品全体R/M/A/E/P/Uの未達は維持する。今回の準備で読解を解決していない。公開repoだがライセンスは未設定。新しい利用許諾や既存資産の再ライセンスは付与していない。
