# K2-18 b historical C1 context diagnostic

This isolated diagnostic applies the already-committed GO-2372 local-contrast
calculation to the historical GO-2722 C1 published spectrum. It is descriptive
context only: C1 is one evidence unit with two correlated reduction views. It
is never pooled or voted with C2/C3, and comparison with GO-2372 is descriptive,
not inferential.

## Frozen input and method

The source is the same 275,602-byte Hu et al. OSF ZIP already pinned by
`k218_repeatability` (SHA-256
`4ee5cb6ad42015bd8fb10f64e54329d250137ab1fa129c89a14830946adc8f18`).
The isolated allowlist extracts only:

| View | Bytes | SHA-256 |
|---|---:|---|
| exoTEDRF C1 NRS2 | 46,925 | `bd5ffeacfd2962f44175872e90b1f335e87e5212f1c194ccc4cf3be2469e663a` |
| Eureka C1 NRS2 | 33,017 | `e2f2ee2489f81203e8292194c6e5fc949740fe407a98c34348a48b87bab7392b` |

Both have 335 rows with wavelength centres 3.832–5.168 µm. C1 was observed on
2023-01-20 under GO-2722.

No numerical method was tailored to C1. The package imports the committed
global `R=100` edge vector, overlap-aware inverse-variance rebinning, covariance
propagation, signed GLS model, native AR(1) sensitivities at `rho=0.25,0.5`, and
one-output-bin deletions from `k218_repeatability.analysis`. The domain remains
3.85–4.75 µm; the feature window remains 4.05–4.55 µm; the model remains
`y = alpha + beta*(lambda-4.30) + A*f`.

This was not blind or pre-unblinded. The method had already been committed for
C2/C3, but the first few C1 table rows were displayed while checking headers
before this implementation. The analysis is also post-publication, not held
out, and not externally preregistered.

## Frozen descriptor and claim boundary

Successful execution always has
`science_state=not_applicable_historical_context`. The descriptor is
`positive_local_contrast_in_both_correlated_views` only when both nominal views
have `A>0` and retrospective `z>=2`, and every required AR(1) and deletion fit
is valid with positive amplitude. Otherwise it is `criterion_not_met`.

The descriptor does not identify a molecule, establish atmospheric or
planetary origin, compare C1 inferentially with GO-2372, or provide evidence of
life. It cannot complete B3/B3b or establish real-data readiness. Important
limitations are C1's substantially shorter out-of-transit time baseline, shared
photons, post-publication/non-held-out status, and unavailable published
covariance. The diagonal and AR(1) matrices are analysis assumptions.

There is also a published treatment disagreement that these spectra cannot
adjudicate: Hu et al. describe masking a spot-crossing event in the Eureka C1
analysis, while Schmidt et al.'s peer-reviewed reanalysis reports no spot
crossing in the NIRSpec light curves and treats the spot event as NIRISS-specific.
After the first diagnostic execution, this limitation wording was clarified and
the Schmidt citation was added; no input, numerical method, threshold,
descriptor rule, or result value changed.

## Run

```bash
uv sync
uv run k218-c1-context download
uv run k218-c1-context extract
uv run k218-c1-context verify
uv run k218-c1-context run
```

The default `download` path deliberately reuses
`data/k218_repeatability/spectra-k2-18b.zip`. Extraction and artifacts are
isolated under `data/k218_c1_context/` and `artifacts/k218_c1_context/`.

## Frozen run result

The diagnostic executed successfully and returned
`science_state=not_applicable_historical_context` with
`context_descriptor=criterion_not_met`:

| Correlated view | A (ppm) | SE(A) (ppm) | Retrospective z | Nominal criterion |
|---|---:|---:|---:|---|
| Eureka | 26.9563 | 24.5775 | 1.0968 | Not met |
| exoTEDRF | 31.0411 | 27.1365 | 1.1439 | Not met |

Both amplitudes remained positive under `rho=0.25` and `rho=0.5`. All 20
one-bin-deletion fits were valid and positive in each view: 6.3832–43.6097 ppm
for Eureka and 5.0198–42.0632 ppm for exoTEDRF. The paired amplitude difference
was -4.0847 ppm (Eureka minus exoTEDRF); no significance was computed because
the cross-reduction covariance is unavailable.

The two real runs were byte-identical:

- canonical JSON SHA-256:
  `46c0c1381b07529377411560aedf697c3918f325b35712cee5e3a8cfa9307107`
- PNG SHA-256:
  `127286bb5090fc11ecf414e25c6956e02dfa475ef45c7b728358e94f4f5f3056`

Thus the historical C1 data are directionally positive under this local
descriptor but do not clear its fixed threshold. This is not evidence against
or for a molecule: identity, origin, atmosphere, biosignature, life, and
GO-2372 inference all remain unevaluated.

Sources: [Hu et al.](https://arxiv.org/abs/2507.12622),
[Schmidt et al.](https://doi.org/10.3847/1538-3881/ae019a),
[OSF record](https://doi.org/10.17605/OSF.IO/HPU8G), and
[JWST GO-2722](https://www.stsci.edu/jwst/science-execution/program-information?id=2722).
