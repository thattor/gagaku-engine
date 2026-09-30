# gagaku-engine

Physical modeling and performance engine for Gagaku.

平調・五常楽急を自前生成音源で演奏する開発中のプロジェクトです。実器の完全な同定ではなく、必要十分な音色と音楽的進行を目指します。現在の音声・記譜は未検証を含むプレビューで、完成版ではありません。

## 今回の作業

**笙の重ね字2箇所と対象区間の手移りを、一次資料・PD資料から確定することだけ。**

- [Issue #1](https://github.com/thattor/gagaku-engine/issues/1)
- [今回の固定範囲・完了条件・停止条件](docs/tasks/SHO_READING_V1.md)
- [Codex / Agent向け入口](AGENTS.md)
- [製品全体の固定ゴール](docs/PRODUCT_GOAL_V1.md)
- [基準コードの由来と検査手順](docs/MIGRATION.md)

旧開発から限定移植したコード、譜面fixture、source evidence、テストを同梱しています。龍笛・篳篥等の既存コードは回帰用に保持していますが、今回それらの開発へ進みません。完了後、または公開資料不足を具体化した場合は停止します。

## ライセンス

未設定です。コードと生成音声・譜面データの扱いは別途整理します。公開済みという理由だけで、収録資料を無制約に再利用できるとは表示しません。第三者の録音・音声素材は同梱していません。
