# Gagaku physical-source evaluation

Run the standard-library-only evaluator from the repository root:

```sh
python3 -m features.gagaku.evaluate \
  --wav output/sho-ichi.wav \
  --reference features/gagaku/refs/hikichi_2003_ichi.json \
  --output output/sho-ichi-result.json
```

The JSON result records the WAV SHA-256, the complete reference document, paper parameters, evaluator version, Git commit when available, measured fundamental frequency, relative harmonic amplitudes, spectral centroid, and Gate 1 criteria. The CLI also writes a companion `<output-stem>.spectrum.csv` with harmonic frequencies and amplitudes. Spectral summaries use the middle 1-second segment as the stable-state window (or the available shorter duration), preserve the WAV native sample rate to avoid aliasing, and use a Hann-windowed radix-2 FFT for the magnitude-weighted centroid. Exit code `0` means the measurement completed and a result was written; parse `gate_1.status` for the evaluation (`PASS` or `FAIL`). Invalid input or an evaluation error exits non-zero.

A fundamental-frequency criterion can pass within the reference tolerance while overall Gate 1 fails. A single WAV cannot demonstrate pressure-dependent spectral growth or pipe-length-dependent onset threshold, so those criteria are emitted as `UNVERIFIED`, and overall Gate 1 cannot pass while they remain unverified. H2/H4 prominence is measured from the candidate WAV using the unchanged rule that each must be at least half of the strongest H1–H10 amplitude. Each amplitude is the largest Hann-windowed FFT bin within `max(2 Hz, 0.5 Hz × harmonic number)` of the estimated harmonic frequency; the result and CSV record the actual peak bin frequency. This bounded search avoids a false negative when a small fundamental estimate error is multiplied by harmonic number over a 1-second analysis window. It does not alter the WAV or increase individual spectral bins.

Only the candidate WAV and the small JSON reference are needed. The evaluator does not require or redistribute reference recordings or article figures.

## Issue #53: sho ichi pipe

The [reference record](refs/hikichi_2003_ichi.json) traces B4 483.7 Hz,
the original 24.1 cm pipe, and the Table II model parameters to Hikichi,
Osaka and Itakura, *Time-domain simulation of sound production of the sho*,
JASA 113(2), 1092–1101 (2003),
[DOI:10.1121/1.1534605](https://doi.org/10.1121/1.1534605).
No paper audio or figures are stored here.

```sh
python3 -m features.gagaku.experiment --output-dir /tmp/sho-ichi-experiment
```

This creates six 48 kHz PCM16 WAVs at 400, 600 and 800 Pa: internal pipe
pressure `p2` and entrance volume velocity `U_in` for each pressure. Each has
its own evaluation and spectrum. The primary Gate 1 remains based on `p2`.
The `U_in` files are un-radiated source diagnostics, not exterior sound.
The run includes a coarse pipe-length/onset sweep, a 75–450 Pa original-pipe
fine sweep in 25 Pa increments, and `result.json`. A separate `q8/` directory
contains the same run with reed Q=8; Q=35 remains the baseline. Both retain
the 1 Pa steady-state RMS rule on a 1.5 s cold start.
The `result.json` keeps each #52 Gate 1 criterion's PASS/FAIL plus measured
values, model/measurement provenance, and a follow-up experiment for failures.
The renderer integrates the outward-striking reed, nonlinear slit airflow
with inertia, and reflected pipe pressure (paper Eqs. 1–3). No target-frequency
tone is injected. Reflection loss 0.98 and Gaussian width 1 sample are
explicit implementation assumptions; the accessed paper does not specify
their numerical values. The WAV is internal pipe pressure mapped to listening
PCM, without the paper's external radiation transfer. It cannot establish
equality to the author's radiated timbre or substitute for permitted real
reference recordings.

Hikichi et al. Sec. III.D estimates Q=8–10 as appropriate for threshold
behavior while Table II spans Q=8–35. Q=8 here is a sensitivity condition,
not an identified fit. The paper's Sec. IV.C computes radiated sound by
applying a pipe transfer function to `U_in`; this experiment does not implement
that transfer. The same section finds that H2/H4 predominance is not caused
by pipe transfer resonance peaks. Its Sec. V notes that the symmetric reed
model cannot reproduce the measured positive/negative threshold asymmetry.
The fine sweep uses a cold-start step, whereas the paper gradually increased
pressure. The two onset methods are not equivalent.

## Numerical and pressure-protocol diagnosis

```sh
python3 -m features.gagaku.diagnostics --output-dir /tmp/sho-ichi-diagnostics
```

This separate experiment holds the reed parameters fixed while comparing
48/96/192 kHz integration and short/gradual pressure ramps. The Gaussian
reflection width scales with sample rate so its physical duration remains
1/48000 second. Holding its width at one sample would change both the
numerics and the acoustic load, confounding a convergence test.

The renderer accepts `pressure_ramp_seconds` (default 0.05 s). This is a
driving-pressure protocol parameter. The diagnostic onset runs compare
1.5 s and 6 s cold starts and a 3 s gradual ramp. Raw pressure RMS is
recorded in early and late windows; an early window during the long ramp
is not at the final nominal pressure. The existing Gate run retains its
original 50 ms ramp and 1 Pa RMS rule. These experiments diagnose model
and protocol sensitivity; they do not establish exterior microphone
agreement or replace the #52 evaluation.

## Coupled spherical-load experiment (unvalidated)

```sh
python3 -m features.gagaku.radiation_experiment --output-dir /tmp/sho-spherical
python3 -m features.gagaku.radiation_experiment --low-frequency-matched-radius --output-dir /tmp/sho-spherical-matched
```

This independent approximation connects the cylinder to a full pulsating
sphere of radius equal to the pipe radius. The radiating area is four times
the pipe area; that discontinuity is an explicit hypothesis, not a measured
sho geometry or exact reconstruction of the paper's unflanged termination.
The radiation impedance determines the feedback reflection as well as the
external pressure; no independent harmonic gain is introduced. External
distance is 5 cm from the **sphere center**, whereas the paper's microphone
distance is described relative to the pipe exit. These locations are not
silently equated. Propagation uses fractional linear delays with the same
one-way operator squared for the round trip. No fitted wall loss is added.

The module documents the impedance and bilinear filter equations. Tests check
passivity, DC behavior, impulse transfer and observer distance scaling.
The runner saves internal pressure, entrance volume velocity and exterior
pressure at 400/600/800 Pa for Q35 and Q8, plus original-length and pipe-length
onset sweeps. It applies the same four measurement rules and preserves
`physical_model_validation_status=UNVALIDATED` and
`acceptance_status=UNVERIFIED`, independently of their numeric results.
The baseline Gaussian experiment remains the existing Gate condition.
Adopting this approximation as an accepted physical model requires evidence
for the termination geometry and external response; synthesized WAVs alone
cannot establish that. Recording permission in #55 remains unobtained.

The second command compares the effective radius
`a = pipe_radius / (4 * 0.6133)` (1.426708 mm). This follows from matching
the leading radiation resistance and reactance terms in
[Caussé et al. 1984, Sec. II.B, p. 243](https://doi.org/10.1121/1.390402),
the unnumbered formula for `z = kr < 1.5`. It is an asymptotic approximation,
not a fit to sho pitch or harmonics and not the complete Levine–Schwinger
formula. The default radius and this source-derived effective radius are
kept as separate conditions. Tests check the matched low-frequency terms
and the passivity of both digital loads.

Evaluator v0.3 refines the initial autocorrelation estimate with observed
native-rate FFT peaks H1–H6 within 1% of that estimate. It uses logarithmic
parabolic peak interpolation and a magnitude-weighted median of each
partial frequency divided by its harmonic number. The refinement receives
no reference pitch; the preceding autocorrelation still uses the existing
reference-based frequency search range. Both initial and refined estimates
and measured peak candidates are recorded. This corrects observable-dependent
autocorrelation bias that could move H4 outside the unchanged narrow peak
search. The H2/H4 half-strongest rule and its search width remain unchanged.
