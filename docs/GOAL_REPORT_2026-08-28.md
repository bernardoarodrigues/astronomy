# Goal report: evidence-led search beyond Earth

Date: 2026-08-28

## Executive outcome

No evidence of life and no genuinely groundbreaking detection were found. The
strongest defensible result is narrower but useful: under one fixed, signed
4.3-micrometre local-morphology calculation, both correlated reductions of
K2-18 b visit C2 are positive, historical C1 is positive but subthreshold, and
both reductions of C3 fail the sign/threshold criterion. The frozen
C2/C3 repeatability state is therefore `SCIENCE_UNRESOLVED / criterion_not_met`.

This pattern is evidence that the selected published-spectrum morphology is
visit-sensitive under the frozen calculation. It is not evidence that the
planet varied, and it does not identify CO2, DMS/DMDS, any other molecule, an
atmosphere, planetary origin, a biosignature, or life. Hu et al. independently
flag C2-versus-C1/C3 inconsistency, so the repository result quantitatively
sharpens an existing warning rather than establishing a new astrophysical
discovery.

## K2-18 b result

All values below use the same committed global `R=100` grid, overlap-aware
rebinning, full propagated rebin covariance, signed intercept+slope+feature
GLS model, assumed AR(1) sensitivities, and complete one-output-bin deletions.
The Eureka and exoTEDRF columns are correlated views of the same photons, not
independent evidence.

| Visit | Program | Eureka A +/- SE (ppm), z | exoTEDRF A +/- SE (ppm), z | Status |
|---|---|---:|---:|---|
| C1 | GO-2722 | 26.9563 +/- 24.5775, 1.0968 | 31.0411 +/- 27.1365, 1.1439 | Historical context; descriptor not met |
| C2 | GO-2372 | 50.2211 +/- 18.5475, 2.7077 | 55.1672 +/- 22.7551, 2.4244 | Nominal local criterion met in both views |
| C3 | GO-2372 | -33.1768 +/- 18.5032, -1.7930 | -1.5401 +/- 24.6041, -0.0626 | Criterion not met in either view |

C1 is post-publication, not held out, not externally preregistered, and was
used only as descriptive historical context. C2/C3 were the two evidence units
in the separately frozen repeatability benchmark. No C1/C2/C3 values were
pooled, voted, or used for an inferential cross-program comparison.

Deterministic artifact evidence:

- C2/C3 manifest: `1434dde1a6c2169e95b1442671555bb27c0d77873daa53f0da6d6e296dec546f`
- C2/C3 JSON: `b5c8832942a0e1d91ad854d156f6d2460ff4823195ae182bc9c9176fe904c59e`
- C2/C3 PNG: `e9ed232109405f712b82fbe07daa13e961ab2bf0a78a829f1545b8571002992f`
- C1 manifest: `7e586d625c79a027b95802c7b408d1bd3962a42702fc5f9442dc48c8ffac6680`
- C1 JSON: `46c0c1381b07529377411560aedf697c3918f325b35712cee5e3a8cfa9307107`
- C1 PNG: `127286bb5090fc11ecf414e25c6956e02dfa475ef45c7b728358e94f4f5f3056`

## The held-out experiment

The later public GO-2372 o005 G395H observation from 2025-05-26 is the
highest-value next test found. It was not used in the C2/C3 or C1 calculations.
The exact public 971,706,240-byte Stage-3 `x1dints` product was downloaded,
hashed, and inspected only at the metadata/header level. Its SHA-256 is
`79d5957df2bc0a4c3c15e576bff2926c2316868131bd3ae9d6a3df3f94f2648b`.

The fit was initially stopped before opening wavelength-dependent results
because the archived extraction records flicker/1/f-noise cleaning and
flagged-pixel replacement as skipped. Both overlap known NIRSpec/BOTS failure
modes that can create wavelength structure, especially on NRS2. Its background
subtraction is also skipped, but that is expected for standard BOTS without a
background association member and is not itself a pipeline error. The archived
product's formal outcome remains `NOT_RUN / BLOCKED`, not a positive, negative,
or null science result.

All three public NRS2 `uncal` segments then completed a serial
`jwst==3.0.0` / `jwst_1584.pmap` Detector1 and Spec2 path. The output headers
cover integrations 1-2089 continuously and record both cleaning stages,
`fit_profile` pixel replacement, and extraction as complete. This is a useful
engineering advance, but it is not a held-out science result: the configuration
and environment were reconstructed from logs after execution, auxiliary
cleaning cubes were not saved, detector/time-series engineering QC was not run,
and no wavelength-dependent values were opened. Its strict state is
`pipeline_execution=COMPLETE`, overall `PARTIAL`,
`protocol_conformance=NONCONFORMING`, and science `NOT_RUN`.

The remaining decisive work is a contemporaneously frozen reduction/QC and
inference harness with detector-space diagnostics, multiple extraction widths,
a transit/systematics model, joint wavelength covariance, and null/injection
gates completed before unblinding the same 20-bin morphology statistic. The
final planned GO-2372 G395H observation o006 remains unavailable for this run
and is not part of any result here.

Detector-engineering artifact evidence:

- protocol manifest: `0a57f12bffb436879d7a4905f3dc9ce5311561935e0a85fb0d0e4c58f5024a29`
- as-run execution record: `52b2a8931a20a06b701999878751b0f4fa1687aea61fb1c1cb0ff75f93fa0187`
- reconstructed resolved configuration: `eedd9e1ffe86a8a877b3b09b7971895ccdb31d1b0421dbee8f873accdcbd2d68`
- reconstructed environment snapshot: `a746c3e9bca763539dc1cf486113f996571ab9952e9f66295d1f407acf660cde`

## Calibration findings

The atmospheric workflow correctly failed closed before claim-bearing K2-18 b
molecular retrieval:

- WASP-39 b recovered the expected strong published 4.3-micrometre atmospheric
  positive control.
- GJ 486 b reproduced published water-template regressions and their
  sensitivity, but planet-versus-star origin remained unevaluated and the
  science result remained unresolved.
- The 648-case B3a synthetic preflight passed recovery, weak-signal restraint,
  coefficient-bias, coverage, pull, determinism, unit, and order checks, but
  remained `INCOMPLETE`: pooled unsafe over-specific classification was
  20/432 (4.63%) versus a maximum of 2%; the worst family was 17/72 (23.61%);
  omitted-template diagnosis was 36/72 (50%) versus at least 75%; and
  signed-cancellation diagnosis was 31/72 (43.06%) versus at least 70%.
- The sealed B3b scientific gate was not run. Real-data molecular-attribution
  readiness remains unestablished.

The radio track recovered all three known Voyager 1 downlink components as a
positive control. That demonstrates one known-signal pipeline path only; it is
not an unknown-signal search result or a technosignature candidate.

## Reproducibility and repository state

The final full suite passed 116/116 network-free tests. Both real C1 executions
were byte-identical, `uv lock --check` passed, source and wheel builds passed,
the C1 CLI and frozen manifest were present in the wheel, and no downloaded
observation data, run artifacts, or work directories were packaged or
committed. Independent agent reviews found the C1 implementation and the o005
detector package release-clear under their strict claim boundaries.

Goal-run milestones on `main`:

- `77f1954` - synthetic atmosphere preflight
- `b69fbf6` - K2-18 b C2/C3 repeatability benchmark
- `fd797a3` - public o005 held-out preflight
- `6c617bd` - historical C1 context diagnostic
- `551b84b` - o005 detector engineering execution record

Downloaded observations remained outside Git. The o005 Stage-3 inspection used
less than 1 GB; the subsequent staged detector primary, including inputs, CRDS
cache, outputs, and logs, occupied about 11.35 GB of allocated disk. The
existing 20 GB ceiling was retained: 40 GB is justified only when running and
retaining multiple full detector-level o005 reductions or diagnostic cubes,
and storage was not the current scientific blocker. Institutional paper access
was not required for this run.

## Claim ceiling

The result supports only this statement:

> A fixed local 4.3-micrometre morphology criterion was met in both correlated
> published reductions of K2-18 b visit C2, but not in C3; historical C1 was
> positive and subthreshold. The frozen C2/C3 repeatability criterion
> was not met, and molecule, origin, atmosphere, biosignature, and life were not
> evaluated.

Primary provenance: [Hu et al.](https://arxiv.org/abs/2507.12622),
[Schmidt et al.](https://doi.org/10.3847/1538-3881/ae019a),
[published spectra on OSF](https://doi.org/10.17605/OSF.IO/HPU8G), and
[STScI NIRSpec/BOTS known issues](https://jwst-docs.stsci.edu/known-issues/nirspec-known-issues/nirspec-bots-known-issues).
