# gagaku-engine

[日本語](README.md) | [English](README.en.md)

A project in development for performing Hyōjō Gojōraku-kyū with independently generated instrument sounds. The goal is sufficiently convincing timbre and musical progression, rather than complete identification of real instruments. Current audio and notation are previews with unverified elements, not a finished product.

## Development status

This README describes the public `main` implementation. It includes physical sound generators for shō, ryūteki and hichiriki, a 192-second three-pipe candidate built by expanding a 96-second body twice, browser playback, and finish requests at candidate boundaries. The repetition and 250ms fade are author-selected designs; they do not establish verified traditional nihen, musical exits or tomede.

The original strict task to resolve two stacked shō symbols and hand transitions remains `BLOCKED_PUBLIC_EVIDENCE`. Prototypes based on explicit adopted interpretations are recorded separately from full verification of score readings and performance practice. The owner's musical-quality evaluation `U` is `UNEVALUATED`; overall product acceptance, `DONE = R AND M AND A AND E AND P AND U`, is not met.

Keep development-branch results separate from `main`. A correction for the preceding piece's final column appearing in the old ryūteki candidate is in [Draft PR #13](https://github.com/thattor/gagaku-engine/pull/13) and its successors, unmerged as checked on 2026-10-10. Do not treat the 192-second candidate in `main` as the corrected performance.

## Setup

CI uses Python 3.12. Audio generation uses the standard library; regression tests including the rights corpus need the test dependencies in [requirements-dev.txt](requirements-dev.txt).

```sh
git clone https://github.com/thattor/gagaku-engine.git
cd gagaku-engine
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

## Usage

Generate the public `main` 192-second candidate. WAVs, performance events, inspection results and a player are saved in the selected directory. Use a separate output directory to distinguish regenerated files from existing results.

```sh
.venv/bin/python -m features.gagaku.product.three_pipe_pass --output-dir output/three-pipe-pass-v1
.venv/bin/python -m http.server 8000 --bind 127.0.0.1 --directory output/three-pipe-pass-v1
```

After generation, open <http://127.0.0.1:8000/pass-player.html>. Finish requests take effect at the 96- or 192-second candidate boundary. See the [192-second candidate procedure](docs/tasks/three-pipe-pass-v1/README.md) for playback conditions, adopted interpretations and checks.

Regression tests:

```sh
.venv/bin/python -m unittest discover -s features/gagaku -t . -v
.venv/bin/python -m unittest features.gagaku.tests.test_evaluate features.gagaku.references.test_corpus -v
```

## Limitations and references

Pitches, timing, hand transitions and timbre include unverified adopted hypotheses. Passing tests or reproducing audio does not establish historical performance correctness or the owner's listening acceptance. A complete three-pipe performance, verified exits and tomede, and 5/10/20-minute product operation remain incomplete. No new instrument measurements or performer recordings are made, and third-party recordings are not used as production material.

- [Issue #1](https://github.com/thattor/gagaku-engine/issues/1)
- [Original shō reading task: scope, completion and stopping conditions](docs/tasks/SHO_READING_V1.md)
- [Codex / agent entry point](AGENTS.md)
- [Fixed overall product goal](docs/PRODUCT_GOAL_V1.md)
- [Baseline provenance and regression procedure](docs/MIGRATION.md)

The repository includes selectively migrated code, score fixtures, source records and tests. Old repository issue numbers and test results provide provenance; do not treat them as current-version completion evidence. Detailed references are mainly in Japanese.

## License

No license has been set. Code, generated audio and score data require separate treatment. Public availability does not imply unrestricted reuse of the included material. No third-party recordings or audio samples are bundled.
