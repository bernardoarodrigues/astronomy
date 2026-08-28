# Reproducible search for signals beyond Earth

This repository develops auditable searches for atmospheric biosignatures and
radio technosignatures. The completed first milestone is a small, reproducible
engineering benchmark that recovers the known Voyager 1 downlink features in a
public Breakthrough Listen observation. It is not an extraterrestrial-signal
claim, a general detection pipeline, or a measurement of Voyager's physical
properties.

The next experiments are deliberately hypothesis-led rather than
headline-led. [`docs/EXPLORATION_PLAN.md`](docs/EXPLORATION_PLAN.md) ranks
K2-18 b and seven complementary systems, identifies public data and realistic
download sizes, and separates what existing observations can test from what
needs new observations. The corresponding machine-readable
[`docs/hypothesis_ledger.json`](docs/hypothesis_ledger.json) freezes the initial
claims, nulls, confounders, gates, and stopping rules.

## Current state

- **Radio positive control — complete:** all three documented Voyager features
  were recovered from the guarded 50 MB input; the full regression suite
  passes.
- **Radio cadence validation — planned:** the compact 1.45 GB HIP 56242
  ABACAD set is documented but has not been downloaded.
- **Atmospheric positive control — complete:** the isolated WASP-39 b harness
  recovers the frozen 4.3 µm feature in the published FIREFLy spectrum with
  leave-one-out, assumed-covariance, scale-invariance, and null-calibration
  checks.
- **Atmospheric ambiguity reproduction — complete:** the separate GJ 486 b
  harness reproduces the archived NIRSpec water-template regressions, exposes
  their sensitivity, ranks the stellar mixtures, and reproduces a separate
  MIRI fixed-model constraint. Its required result is `PASS /
  science_unresolved`; the direct planet-versus-star origin comparison is
  explicitly `not_evaluated`.
- **Synthetic atmospheric engineering preflight — implemented, incomplete:**
  the isolated B3a harness runs 648 deterministic public synthetic cases on
  the pinned Eureka grid without observed transit depths. The frozen v1 run
  passes recovery, coverage, pull, and invariance checks but misses unsafe-
  specific and diagnostic-classification gates, so it correctly reports
  `INCOMPLETE`; its all-gates-pass hypothesis is contradicted.
- **Sealed synthetic scientific gate — pending:** B3b still requires an
  independent truth custodian/scorer and the preregistered 2,000-negative,
  1,000-power, and 2,000-coverage-per-cell release ensembles.
- **K2-18 b visit-level morphology — executed, unresolved:** the isolated
  GO-2372 harness found a positive predeclared 4.3 µm local contrast in C2 but
  not C3 under either paired Eureka/exoTEDRF view, so the frozen repeatability
  criterion was not met. It neither attributes a molecule nor changes
  B3b/readiness or the existing K2-18 molecular hypotheses.
- **K2-18 b held-out o005 — public, blocked before fit:** a later May 2025
  G395H visit is public, pinned, and under 1 GB at Stage 3, but the archived
  extraction skipped flicker-noise cleaning, pixel replacement, and background
  subtraction. No wavelength-dependent fit was run; a detector-level corrected
  reduction and injection gate are required.
- **K2-18 b — retrospective replication only:** methane is the strongest
  published atmospheric result; CO2 is less independently mature; DMS/DMDS,
  an ocean, a technosignature, and life are not established.

Each evidence track gets its own manifests, dependencies, results, and claim
gates. Success means a reproducible, calibrated answer—including a null—not a
candidate.

## Milestone B1 — atmospheric positive control

The separate `atmosphere_benchmark` package and `atmosphere-benchmark` CLI use
a pinned 375 KB Zenodo v1 archive rather than raw JWST detector products. The
benchmark fits a frozen linear baseline and signed 4.3 µm feature to exactly 20
published FIREFLy bins, then runs leave-one-out, ppm-scale invariance, assumed
covariance stress, and 10,000-draw null-calibration checks.

```bash
uv sync
uv run atmosphere-benchmark download
uv run atmosphere-benchmark extract
uv run atmosphere-benchmark verify
uv run atmosphere-benchmark run
```

See [`docs/ATMOSPHERE_BENCHMARK.md`](docs/ATMOSPHERE_BENCHMARK.md) for frozen
inputs, equations, acceptance bands, citations, artifact contract, and strict
claim limitations. This positive control does not alter the Voyager package or
its commands.

## Milestone B2 — GJ 486 b retrospective ambiguity reproduction

The isolated `gj486_benchmark` package and `gj486-benchmark` CLI pin corrected
Zenodo v3 NIRSpec inputs plus a separate GO 1743 MIRI author-data constraint.
The archive downloads total about 289.5 MB. Both default guards remain far
below the immutable 20 GB project ceiling.

```bash
uv sync
uv run gj486-benchmark download
uv run gj486-benchmark extract
uv run gj486-benchmark verify
uv run gj486-benchmark run
```

The three NIRSpec reductions are correlated robustness views and are never
combined as independent evidence. GO 5866 is recorded only as public NIRISS
archive time-series availability, with no B2 interpretation. See
[`docs/GJ486_BENCHMARK.md`](docs/GJ486_BENCHMARK.md) for inputs, calculations,
program provenance, diagnostics, citations, and the strict claim ceiling.

## Milestone B3a — synthetic atmospheric engineering preflight

The isolated `synthetic_atmosphere_benchmark` package and
`synthetic-atmosphere-benchmark` CLI reuse only the three checksum-pinned GJ
486 b NIRSpec source members. They read Eureka wavelengths, widths, and
uncertainties, but deliberately never parse observed transit depths. The
planet proxy is the binned author PICASO water template and the stellar proxy
is the centered PHOENIX M3/M1 contrast.

```bash
uv sync
uv run synthetic-atmosphere-benchmark verify
uv run synthetic-atmosphere-benchmark run
```

The public v1 preflight uses exact signed linear-Gaussian fits, correct and
naive covariance diagnostics, separate challenge/truth/prediction schemas, and
order-independent PCG64DXSM streams. Its current frozen result is
`engineering_preflight_status=INCOMPLETE`, alongside
`science_state=not_applicable_synthetic` and
`real_data_readiness=not_established`. This is useful fail-closed engineering
evidence, not permission to tune the suite, declare B3 complete, or analyze
K2-18 b. See
[`docs/SYNTHETIC_ATMOSPHERE_PREFLIGHT.md`](docs/SYNTHETIC_ATMOSPHERE_PREFLIGHT.md).

## K2-18 b GO-2372 published-spectrum repeatability

The isolated `k218_repeatability` package and `k218-repeatability` CLI pin a
275,602-byte Hu et al. OSF archive and safely extract only the four selected
NRS2 visit/reduction views. A metadata-only inventory selects both GO-2372
G395H visits and marks historical GO-2722 C1 ineligible. The two reductions of
each visit are explicitly correlated views and are never combined or voted as
independent evidence.

```bash
uv sync
uv run k218-repeatability download
uv run k218-repeatability extract
uv run k218-repeatability verify
uv run k218-repeatability run
```

The analysis uses one hashed global R=100 log grid, overlap-aware
inverse-variance rebinning with full covariance propagation, a signed local
4.3 µm morphology contrast, two AR(1) sensitivity models, and full-model
one-bin deletions. `z` is a retrospective standardized contrast, not discovery
significance. See [`docs/K218_REPEATABILITY.md`](docs/K218_REPEATABILITY.md)
for the frozen contract, `SCIENCE_UNRESOLVED` result, and claim boundary.

The later public GO-2372 o005 visit is recorded separately in
[`docs/K218_O005_HELDOUT_PLAN.md`](docs/K218_O005_HELDOUT_PLAN.md). Its
metadata-only preflight is `NOT_RUN / BLOCKED`; it is a future held-out test,
not an extension or reinterpretation of the executed C2/C3 result.

## Phase 1 — Voyager benchmark

Phase 1 uses Berkeley SETI's 50 MB single-coarse-channel HDF5 example rather
than a raw observation measured in many gigabytes. `blimpy` reads and plots the
Breakthrough Listen waterfall, and `turbo_seti` performs the narrowband drift
search.

## Provenance and fixed baseline

The machine-readable manifest is bundled at
[`src/voyager_benchmark/data_manifest.json`](src/voyager_benchmark/data_manifest.json).
It records:

- the immutable sample object in the official turboSETI repository, pinned to
  commit `dbfb5e35edf6a7f384d0da9bc6da14b6bc6e0395`, with Git blob OID
  `42a41e5c2564afc8e73dc7b23cece3e3123f15d6`;
- the original sample URL published by the official
  [blimpy Voyager notebook](https://github.com/UCBerkeleySETI/blimpy/blob/master/examples/voyager.ipynb),
  retained as provenance rather than as the download transport;
- the 50,549,227-byte size returned by the source and documented by that
  notebook;
- SHA-256 `c9a9a54f4140e3754ffb2455fae4eeb2eb70c8207123116ee953e4fce15c36ac`,
  calculated locally from a guarded download on 2026-08-28 (the publisher does
  not provide a signed checksum on the notebook page);
- the published turboSETI arguments `max_drift=4`, `min_drift=0`, and `snr=25`.
  turboSETI interprets nonnegative drift arguments as magnitude bounds and
  searches both signs, so this covers −4 through +4 Hz/s;
- the three expected frequency/drift pairs shown in the official
  [turboSETI Voyager example](https://github.com/UCBerkeleySETI/turbo_seti#example-usage-as-a-python-package).

Downloads use the commit-pinned GitHub HTTPS object. The publisher's original
sample endpoint is HTTP-only: HTTPS currently presents a certificate for a
different hostname, while HTTP is plaintext. It remains in the manifest only
as provenance. The downloader treats the SHA-256 and exact byte count as
mandatory integrity checks. These match both sources as checked on 2026-08-28,
but the digest is still not publisher-signed.

The observation payload's license is recorded as `NOASSERTION`: no dataset
license was asserted by the cited sample pages. This repository's MIT license
applies to the software here and must not be interpreted as licensing the
downloaded HDF5 payload.

## Reproduce the benchmark

[`uv`](https://docs.astral.sh/uv/) is recommended because `uv.lock` pins the
complete dependency graph across supported platforms.

```bash
uv sync
uv run voyager-benchmark download
uv run voyager-benchmark verify
uv run voyager-benchmark run
```

The download command defaults to a 100,000,000-byte guard and can never be
configured above the hard 20,000,000,000-byte project ceiling. Before and
during transfer it checks the manifest size, HTTP `Content-Length` when
present, streamed byte count, exact final size, and SHA-256. It writes through
a temporary file and only moves verified data into place.

`run` verifies the input again, runs turboSETI over ±4 Hz/s, evaluates only the
documented known-signal windows, checks both frequency and drift against fixed
tolerances, requires the carrier to be stronger than both sidebands, and
atomically writes:

- `artifacts/benchmark.json`: fixed parameters, software versions, parsed hits,
  and per-target recovery status;
- `artifacts/voyager_waterfall.png`: a focused blimpy waterfall plot;
- `artifacts/turbo_seti_hits.dat`: the original turboSETI hit table.

The command exits non-zero if any required known target is absent. Output hit
rows and target results are sorted before serialization. No timestamps or
random sampling enter the analysis result.

To use non-default paths:

```bash
uv run voyager-benchmark download --data-dir /path/to/data --max-bytes 100000000
uv run voyager-benchmark run --input /path/to/data/Voyager1.single_coarse.fine_res.h5 --output-dir /path/to/output
```

## Tests (no astronomy download required)

The unit suite uses in-memory HTTP responses, temporary files, generated
spectra, safe-extraction fixtures, and a tiny synthetic turboSETI `.dat`
fixture. It never downloads either benchmark dataset:

```bash
uv run python -m unittest discover -s tests -v
```

The suite exercises manifest validation, all size guards, streamed overflow,
checksum failure, safe extraction, atomic success/cache behavior, spectral
model recovery and negative cases, hit parsing, and known-target evaluation.

## Benchmark scope

Passing means that, for this fixed public observation and dependency set,
turboSETI returned the three expected hits within the manifest's 25 Hz
frequency and 0.02 Hz/s drift tolerances, with the carrier strongest. The
benchmark deliberately makes no inference about signal origin beyond the
already-known spacecraft transmission and no claim about unlisted hits.

Phase 2 (HIP 56242) and BLC1 are future acceptance gates only. Their data have
not been downloaded or added to this Phase 1 manifest; see
[`docs/FUTURE_GATES.md`](docs/FUTURE_GATES.md).
