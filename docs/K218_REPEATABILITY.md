# K2-18 b GO-2372 published-spectrum repeatability

Milestone scope: retrospective observation-layer morphology only. This harness
does not retrieve an atmosphere, identify a molecule, estimate a discovery
significance, validate a raw JWST reduction, or complete B3/B3b.

## Frozen source and visit selection

The sole payload is Hu et al.'s public OSF file `spectra-k2-18b.zip`:

- download: <https://osf.io/download/j6p7r/>
- OSF record DOI: <https://doi.org/10.17605/OSF.IO/HPU8G>
- exact size: 275,602 bytes
- SHA-256: `4ee5cb6ad42015bd8fb10f64e54329d250137ab1fa129c89a14830946adc8f18`
- data license: `NOASSERTION`

The OSF API exposes no license value for this record. The repository's MIT
software license therefore must not be interpreted as licensing the payload.
The ZIP and extracted files stay outside Git.

The selection rule was frozen from visit metadata before running any spectral
fit: select every NIRSpec/G395H visit in GO-2372 for which both archived Eureka
and exoTEDRF NRS2 views exist. The complete G395H inventory in the paper is:

| Paper label | Program | Date (UT) | Eligibility |
|---|---|---|---|
| C1 / archive Visit 1 | GO-2722 | 2023-01-20 | Ineligible historical program |
| C2 / archive Visit 2 | GO-2372 | 2024-05-28 | Eligible |
| C3 / archive Visit 3 | GO-2372 | 2024-12-12 | Eligible |

This gives two evidence units—C2 and C3—with two paired, correlated reduction
views per unit. No spectrum value or fit result participates in selection.
The exoTEDRF ECSV files contain an embedded `visit: '1'` field in both selected
files; the harness records it as a reduction-local label and uses the frozen
archive filenames, dates, and paper table for the science-visit mapping.

Only these four NRS2 members are extracted:

| View | Archive member | Bytes | SHA-256 |
|---|---|---:|---|
| exoTEDRF C2 | `spectra/nirspec_exotedrf_by_visit/K2_18_b_NIRSPEC_G395H_NRS2_0004um_Spectrum_Visit2.spec` | 46,978 | `fc6bf0dac2666cc5ad756a7a34cf5bd9a02efbc842bc2c011a18b4d479b65bc4` |
| exoTEDRF C3 | `spectra/nirspec_exotedrf_by_visit/K2_18_b_NIRSPEC_G395H_NRS2_0004um_Spectrum_Visit3.spec` | 46,978 | `7ec58214c6a485e80b53586cad024faff401fecf1bcd7fd2cce50cb6bb748789` |
| Eureka C2 | `spectra/nirspec_eureka_by_visit/S6_k2_18b_g395_nrs2_ap3_bg9_rp^2_Table_Save_g395_nrs2_c2.txt` | 33,063 | `fc760dc18d194ec78eae1798e4c6802e98bc0ecd8ac57120dd0ad674cbcb6b69` |
| Eureka C3 | `spectra/nirspec_eureka_by_visit/S6_k2_18b_g395_nrs2_ap3_bg9_rp^2_Table_Save_g395_nrs2_c3.txt` | 33,054 | `5a814195e5220dd9428c23c6c9f764914a8615c7d7c8e214071bc02b6d72251d` |

Each file must have 335 strictly ordered, contiguous native cells spanning
centres 3.832–5.168 µm. exoTEDRF declares wavelength and transit depth units as
µm and ppm. Eureka omits ECSV unit tags; its frozen field semantics are
wavelength in µm and `rp^2` as fractional transit depth, validated against a
strict value scale and converted to ppm. In both formats the symmetric
uncertainty is exactly `max(error_low, error_high)`, and both inputs must be
positive.

## Prospective morphology calculation

The manifest and gates were frozen internally before the first spectral fit,
but they were not registered with an external time-stamping service. This is
therefore an internally predeclared retrospective analysis, not an externally
preregistered study.

The calculation uses NRS2 only. It deliberately excludes the 3.3 µm region.
Every view uses the identical global edge vector

`e_k = 1 µm × exp(k/100)`, for `k=135,...,155`.

The 21-edge/20-bin vector has SHA-256
`7f7e418fc0bfde1478d7ade8a4fef0f774bc7bb0f3046a918be7bc763d3b2d28`
when encoded as newline-joined Python float64 `format(.17g)` values with no
trailing newline. All output cells are wholly within 3.85–4.75 µm. A cell is
rejected rather than clipped unless native intervals cover it to relative
tolerance `1e-12` and coverage fraction at least `0.999999999999`.

For native cell `i` and output cell `j`, let `o_ji` be their wavelength-interval
overlap and `sigma_i` the conservative reported uncertainty. The frozen row
weights are

`W_ji = (o_ji / sigma_i^2) / sum_m(o_jm / sigma_m^2)`.

Every used row of `W` must sum to one. `W_ji` is exactly zero without actual
interval overlap; a native cell may contribute to adjacent output cells only
through its real overlap. Rebinning and covariance propagation are

`y_out = W y_native`, and `C_out = W C_native W^T`.

The nominal native covariance is diagonal. The two sensitivity covariances are
full within-detector AR(1) matrices with `rho=0.25` and `rho=0.5`, propagated
through the same `W` and fit by full GLS.

For geometric output-bin centre `lambda` and the exact fraction `f` of each
output interval overlapping 4.05–4.55 µm, the signed model is

`y = alpha + beta (lambda - 4.30) + A f`.

Each cell reports `A` and its standard error in ppm, `z=A/SE(A)`, bin count,
design rank, normal-matrix condition number, and slope–amplitude correlation.
Here `z` is a retrospective standardized contrast, not discovery significance.
Every leave-one-output-bin-out diagnostic refits the full model and fails
closed if invalid.

Common-effect and Cochran-Q diagnostics combine only the two distinct visits
within one reduction. They are descriptive and assume no cross-visit
covariance because no such covariance is published. For each visit, the
Eureka-minus-exoTEDRF amplitude is reported without a significance because
their cross-reduction covariance is not available. Cross-reduction z
combination and voting are prohibited.

## Frozen outcome rule

`repeatable_positive_morphology` is allowed only if all four nominal cells are
present and valid with `A>0` and `z>=2`, every required AR(1) result is valid
with `A>0`, every one-bin deletion is valid with `A>0`, and nothing is missing
or failed. Every other valid execution returns
`SCIENCE_UNRESOLVED / criterion_not_met`. There is deliberately no state based
on all four `|z|` values being below 2.

Regardless of outcome, output fixes `retrospective=true`,
`independent_reduction=false`, planetary origin, atmosphere, molecule, and
biosignature to `not_evaluated`, and `evidence_of_life=false`.

## Run

```bash
uv sync
uv run k218-repeatability download
uv run k218-repeatability extract
uv run k218-repeatability verify
uv run k218-repeatability run
```

The downloader defaults to a 1,000,000-byte guard and cannot exceed the global
20,000,000,000-byte ceiling. It checks available HTTP length metadata, streamed
length, exact final size, and SHA-256, and publishes the file atomically only
after verification. Extraction rejects unsafe names, links, encryption,
duplicates, member-count or expansion-limit violations, and writes exactly the
four allowlisted files atomically.

`run` writes canonical `artifacts/k218_repeatability/k218_repeatability.json`
and `artifacts/k218_repeatability/k218_repeatability.png`. Neither contains a
timestamp or an absolute input path.

## Frozen run result

The first run after freezing the manifest and methods returned
`execution_status=PASS` and
`SCIENCE_UNRESOLVED / criterion_not_met`. The nominal full-GLS results were:

| Reduction | Visit | A (ppm) | SE(A) (ppm) | Retrospective z | Nominal criterion |
|---|---|---:|---:|---:|---|
| Eureka | C2 / visit_2 | 50.2211 | 18.5475 | 2.7077 | Met |
| Eureka | C3 / visit_3 | -33.1768 | 18.5032 | -1.7930 | Not met |
| exoTEDRF | C2 / visit_2 | 55.1672 | 22.7551 | 2.4244 | Met |
| exoTEDRF | C3 / visit_3 | -1.5401 | 24.6041 | -0.0626 | Not met |

Both C2 views retained positive amplitudes at `rho=0.25` and `rho=0.5` and in
every one-bin deletion. Both C3 views had negative nominal and AR(1)
amplitudes; Eureka C3 remained negative in every deletion, while exoTEDRF C3
deletions ranged from -16.0193 to 5.7062 ppm. Therefore C3 fails the frozen
sign and nominal-z requirements under both correlated reduction views, and the
repeatable-positive state is unavailable.

Within Eureka, the two-visit common effect was 8.4226 ± 13.0994 ppm with
`Q=10.1332` for one degree of freedom. Within exoTEDRF it was
29.0242 ± 16.7057 ppm with `Q=2.8631`. These are within-reduction visit
diagnostics only. The paired Eureka-minus-exoTEDRF amplitude differences were
-4.9461 ppm for C2 and -31.6367 ppm for C3; no significance was calculated.

All four views used the same 20 global cells and edge hash. Coverage stayed
within the frozen `1e-12` tolerance, every weight row summed to one within
floating-point precision, weights without overlap were exactly zero, and the
only multi-cell native contributions were the 19 native rows that actually
straddled global edges.

Two runs in the same locked environment were byte-identical:

- canonical JSON SHA-256:
  `b5c8832942a0e1d91ad854d156f6d2460ff4823195ae182bc9c9176fe904c59e`
- PNG SHA-256:
  `e9ed232109405f712b82fbe07daa13e961ab2bf0a78a829f1545b8571002992f`

This result contradicts the ledger's all-cells-positive morphology hypothesis.
It does not identify the feature, resolve its origin, or update a molecular
hypothesis. Hu et al.'s Appendix C independently reports visit-level G395H
inconsistency, especially C2 versus C1/C3, so this local-contrast result is
consistent with a published warning rather than evidence that the planet's
atmosphere varied.

## Claim boundary and provenance

The only allowed description is published-spectrum feature repeatability. A
passing morphology state would not be an independent molecule detection,
planetary or atmospheric attribution, biosignature, evidence of life, or B3/B3b
completion. This observation-layer hypothesis cannot update
`H-K218-CO2`, B3b, or real-data readiness.

Sources:

- [Hu et al. preprint](https://arxiv.org/abs/2507.12622)
- [OSF public record](https://doi.org/10.17605/OSF.IO/HPU8G)
- [JWST GO-2372 program page](https://www.stsci.edu/jwst/science-execution/program-information?id=2372)
