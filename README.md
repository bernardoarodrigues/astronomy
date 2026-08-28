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
  were recovered from the guarded 50 MB input; the 18-test suite passes.
- **Radio cadence validation — planned:** the compact 1.45 GB HIP 56242
  ABACAD set is documented but has not been downloaded.
- **Atmospheric positive/negative controls — planned:** begin with published
  spectra, not raw telescope ramps, for WASP-39 b and GJ 486 b.
- **K2-18 b — retrospective replication only:** methane is the strongest
  published atmospheric result; CO2 is less independently mature; DMS/DMDS,
  an ocean, a technosignature, and life are not established.

Each evidence track gets its own manifests, dependencies, results, and claim
gates. Success means a reproducible, calibrated answer—including a null—not a
candidate.

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

The unit suite uses in-memory HTTP responses, temporary files, and a tiny
synthetic turboSETI `.dat` fixture. It imports no scientific package and never
downloads the 50 MB sample:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The suite exercises manifest validation, all size guards, streamed overflow,
checksum failure, atomic success/cache behavior, hit parsing, and known-target
evaluation.

## Benchmark scope

Passing means that, for this fixed public observation and dependency set,
turboSETI returned the three expected hits within the manifest's 25 Hz
frequency and 0.02 Hz/s drift tolerances, with the carrier strongest. The
benchmark deliberately makes no inference about signal origin beyond the
already-known spacecraft transmission and no claim about unlisted hits.

Phase 2 (HIP 56242) and BLC1 are future acceptance gates only. Their data have
not been downloaded or added to this Phase 1 manifest; see
[`docs/FUTURE_GATES.md`](docs/FUTURE_GATES.md).
