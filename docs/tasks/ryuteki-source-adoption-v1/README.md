# Ryuteki source-column correction v1

The frozen 96-second body candidate places its first ryuteki line on canvas14 of the1932『竜笛譜 初之巻』. Independent visual source review identified that column as the preceding piece's final column: the 五常楽急 title appears at the end of canvas14, and its four body columns begin on canvas15, right printed page18. This separate candidate removes all eight incorrectly adopted first-line cells, shifts the existing24 cells by one line and24 seconds, and adds the omitted eight final-line cells. It preserves the frozen artifacts and validators.

Source: [NDL1194354 canvas15](https://dl.ndl.go.jp/api/iiif/1194354/R0000015/full/full/0/default.jpg), SHA-256 `1c1e63c6f4fe314d93c9e24f6bd51c3c94d45d790638e22a16cb122e280a6f6b`; right printed page18. Every adopted cell has its own approximate full-canvas normalized bbox, source URL/hash, and legacy cell mapping. Four column x ranges, from right to left: L1 .84–.895; L2 .765–.83; L3 .69–.755; L4 .62–.68. Legacy L2→actual L1, legacy L3→actual L2, legacy L4→actual L3; actual L4 has no legacy source cell. New fixture32 cells correspond to32 source locations. The correction establishes the source partition; candidate glyph readings and performance realization remain separate.

| Actual final cell | Chant/sign candidate | Adopted fingers | Author MIDI sequence |
| --- | --- | --- | --- |
| L4.P1 | タア | テ | 76 |
| L4.P2 | ロホ | 六, く | 86,86 |
| L4.P3 | チイイヤ | 五, 上, 五 | 78,79,78 |
| L4.P4 | タア | テ | 76 |
| L4.P5 | ハア | く | 76 retained |
| L4.P6 | タア | テ | 76 |
| L4.P7 | 引様+ア | continuation hypothesis | 76 retained |
| L4.P8 | 引様二記号+二返 | continuation hypothesis | 76 retained |

The final extension-like signs and 二返 remain unverified performance hypotheses; no new repeat, terminal pitch or tomede is invented. Existing finger-to-MIDI choices, A4=430Hz, three seconds per primary cell, equal subdivisions, omission of く finger strikes, and retained-pitch continuation semantics remain author choices. Actual L1.P1's main chant is corrected from the legacy stored トラロ to チラハ. Its initial-only トロホ annotation is retained separately and is not given a newly invented rhythm or execution.

Sho and hichiriki events are copied exactly from the frozen `three_pipe_body.plan()`. The new renderer uses the existing own physical bank, voice interpolation, cosine attack0.15 seconds/release0.25 seconds, gains and stereo coefficients. It uses the existing sounding-span continuation merger, with its own exact-canonical validation; the frozen body validator still rejects this new schedule. There is no new measurement, recording, third-party audio, terminal-envelope experiment, normalization, reverb, UI or license change.

```sh
python3 -m unittest features.gagaku.product.test_ryuteki_source_adoption -v
python3 -m features.gagaku.product.ryuteki_source_adoption --output-dir output/ryuteki-source-adoption-v1
```

Output: four96-second48kHz16-bit PCM WAVs (three mono stems and a stereo ensemble); first24-second and last24-second stereo clips (raw excerpts with no added fades; the first24 seconds cuts a continuous phrase and does not require a zero final frame); `ryuteki-source-before-after-49s.wav` plays the frozen body's last24 seconds, one second of intentional silence, then the corrected last24 seconds. The49-second comparison retains hard excerpt onsets, a checked zero-only24–25 second gap, and the full candidate release at its end. These excerpt cuts are delivery boundaries, not new performance endings. All clip/comparison PCM formats and numeric peaks are inspected; the full96-second candidate, last24-second clip and comparison require a zero final frame. Baseline and corrected audio use the same bank and levels. The report proves sho/hichiriki float and PCM identity to the freshly rendered frozen baseline, changed ryuteki/mix, two independently generated physical-bank metadata matches, independently regenerated float/WAV identity, source locations and exact input hashes, cell/event coverage, nonfinite/full-scale sanity, inherited interior-RMS checks, and final zeros. Numeric checks do not establish musical acceptance. Bank diagnostic WAVs are self-generated model outputs.

CI checks out the exact PR head, runs the narrow tests, regenerates the banks and corrected waveforms, and uploads audio and JSON evidence. Local execution does not claim a CI result. The source commit and exact file hashes bind every report to its actual checkout, including uncommitted source files if run before committing.

`verified_exit=false`, `tomede=false`, `traditional_nihen_verified=false`, `fully_verified_performance_events=0`, `strict_reading_status=BLOCKED_PUBLIC_EVIDENCE`, and `musical_acceptance=UNEVALUATED` remain fixed. Initial ornaments, special-sign execution, actual register/tuning, shared return point, true ending/tomede, other inherited reading limitations, long-duration verified operation and user U remain unresolved. Correcting the wrong-piece adoption does not claim timbre improvement or product completion.
