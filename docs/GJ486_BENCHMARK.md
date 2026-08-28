# GJ 486 b retrospective ambiguity reproduction

Milestone B2 is a pipeline benchmark with an intentionally unresolved science
result. It has two separate evidence branches:

1. GO 1981 NIRSpec/G395H transmission spectra test whether a frozen, signed
   water template is recovered across three reductions of the same transits.
2. GO 1743 MIRI/LRS eclipse data reproduce three publisher fixed-model
   comparisons as an external constraint. These 22 eclipse points are never
   treated as transmission bins or combined with the NIRSpec fits.

Passing means `PASS / science_unresolved`: the frozen calculations were
reproduced and their ambiguity was exposed. It does not authenticate a
spectral feature, perform the missing direct planet-versus-star comparison, or
detect a planetary atmosphere.

## Frozen sources and guarded storage

The bundled manifest is
[`src/gj486_benchmark/data_manifest.json`](../src/gj486_benchmark/data_manifest.json).
Both payloads are CC BY 4.0 and remain outside Git.

### GO 1981 NIRSpec source

- Corrected Zenodo v3 record: [10.5281/zenodo.10408056](https://doi.org/10.5281/zenodo.10408056)
- `GJ486b_Zenodo_2023.zip`: 1,455,085 bytes
- MD5: `1f1674f4c96575d296d6e276b5920161`
- SHA-256: `b259b5e191a35c53280b58e44167760caf10881274b7ddcfa55f5d926a4ef444`
- Exact allowlist: the 7,436-byte transmission table, 27,730-byte 1-bar H2O
  PICASO model, and 941,330-byte stellar spectra/model table recorded in the
  manifest. No white-light curves or other atmospheric models are extracted.

### GO 1743 MIRI external constraint

- Zenodo version record:
  [10.5281/zenodo.13774462](https://doi.org/10.5281/zenodo.13774462)
  (concept DOI `10.5281/zenodo.13774461`)
- `WeinerMansfield2024.zip`: 288,070,101 bytes
- MD5: `925936ccc37bdddbf0ba015ac1d4e4f7`
- SHA-256: `427c6272719eacf8b29864a3e0e8469d57024791eff16ce19efa8c1c9b01fca2`
- Exact allowlist: the 22-point SPARTA joint spectrum, ultramafic surface
  model, 1-bar pure-H2O model, and 824 K blackbody file.

The archive central directory and matching supplied SHA-256 establish that
`Figure5/gj486b_bare_Ultramafic_post_TOA_flux_eclipse.dat` is **2,190,575
bytes**. This corrects the 2,190,573-byte handoff value; the bytes and supplied
digest themselves agree.

The default guards are 3 MB for NIRSpec and 400 MB for MIRI. Alternate
manifests cannot raise either hard limit above the project-wide
20,000,000,000-byte ceiling. Downloads check `Content-Length` when present,
streamed size, exact final size, MD5, and SHA-256 before an atomic move. ZIP
handling rejects traversal, absolute/drive-like names, duplicates, encryption,
symlinks, member-count excess, and uncompressed-size excess, then extracts
only the seven allowlisted files through atomic directories.

## Reproduce

```bash
uv sync
uv run gj486-benchmark download
uv run gj486-benchmark extract
uv run gj486-benchmark verify
uv run gj486-benchmark run
```

Individual sources can be managed with `--source nirspec` or `--source miri`.
`run` requires both extracted branches and writes byte-reproducible artifacts
when repeated in the same locked software environment:
`artifacts/gj486/gj486_benchmark.json` and
`artifacts/gj486/gj486_benchmark.png`.

## Frozen NIRSpec calculation

Eureka, Firefly, and Tiberius are analyzed independently. They are correlated
robustness views of the same GO 1981 transits, not three independent evidence
units.

For each reduction:

- discard rows with wavelength below 2.87 µm and do not rebin;
- keep the NRS1/NRS2 detector gap and define the detector indicator as
  `I(wavelength >= 3.8 µm)`;
- convert the archived PICASO 1-bar H2O transit depth from an absolute fraction
  to ppm, linearly interpolate it at the observed wavelength centres, and
  subtract its inverse-variance-weighted mean;
- fit signed weighted least squares with the reported diagonal variances:
  `M0 = c` versus `MW = c + a*t`;
- separately fit the conservative pair
  `M0s = c + d*I` versus `MWs = c + d*I + a*t`.

The fitted amplitude `a` is a dimensionless scale on the centered author
template. For each pair the output records `a`, `SE(a)`, signed `z=a/SE(a)`,
both chi-squared values, `delta_chi2`, degrees of freedom, and row counts.

| Reduction | Rows | z, no step | z, detector step |
|---|---:|---:|---:|
| Eureka | 109 | 3.52 | 3.07 |
| Firefly | 45 | 2.07 | 1.15 |
| Tiberius | 46 | 3.51 | 3.92 |

Each z fingerprint has tolerance 0.10. The frozen feature state is
`retrospective_template_regression_reproduced`. It depends only on matching
the preregistered per-reduction regression fingerprints; it does not count the
three correlated reductions as votes or combine their z values. The output
always sets `robust_spectral_feature` to false.

The JSON also includes:

- fraction/ppm/percent invariance, scaling data, uncertainties, and template
  together;
- every leave-one-bin-out refit;
- NRS1-only and NRS2-only fits;
- an affine-wavelength baseline stress, with and without the detector step;
- assumed within-detector AR(1) covariance at rho 0.25 and 0.5;
- assumed detector common modes of 20 and 40 ppm.

These are non-promotional sensitivity diagnostics. The machine-readable
assessment flags an influential bin, assumed-covariance sensitivity,
nuisance sensitivity, and detector-side disagreement in the pinned results.
For example, omitting the first retained Tiberius bin changes its no-step z
from 3.51 to 2.20; an AR(1) rho=0.5 changes Eureka's step z from 3.07 to 1.93;
and the affine-baseline stress changes Eureka's no-step z from 3.52 to about
2.62. `PASS` requires these diagnostics to be emitted, not to look favorable.
They can never promote an authenticity or detection claim.

## Stellar heterogeneity diagnostic

For each archived V1/V2 stellar spectrum and each M1/M2/M3 PHOENIX mixture,
the benchmark interpolates over the common wavelength overlap and fits exactly
one multiplicative normalization. The same nuisance form is used for every
model. M3, the heterogeneous photosphere/spot/facula mixture, must rank above
homogeneous M1 in both visits.

This is a **stellar heterogeneity clue**, not a fit of stellar contamination to
the transit spectrum. The exact POSEIDON transit-contamination posterior is not
deposited and is neither reconstructed nor fabricated here.

## MIRI publisher-comparison reproduction

The MIRI branch applies the archived 100-point Hanning smoothing recipe to
each full-resolution eclipse-ratio model, interpolates at the 22 SPARTA joint
centres, converts ratios to ppm, and evaluates chi-squared with no fitted
offset or normalization.

| Fixed model | chi-squared / 22 |
|---|---:|
| 824 K blackbody | 1.0461 |
| Ultramafic airless surface | 1.1793 |
| 1-bar pure H2O | 6.3887 |

This reproduces the publisher ranking and classifies the **specific** thick
1-bar pure-water model as disfavored relative to the allowed blackbody and
ultramafic examples. It is not a general exclusion of atmospheres, and thin
atmospheres remain unresolved. The MIRI study is literature/external context;
it is not combined with the GO 1981 transmission regressions.

## Program provenance and evidence state

The software hard-asserts these mappings:

- [GO 1981](https://www.stsci.edu/jwst-program-info/program/?program=1981):
  NIRSpec/G395H transmission;
- [GO 1743](https://www.stsci.edu/jwst-program-info/program/?program=1743):
  MIRI/LRS eclipse;
- [GO 5866](https://www.stsci.edu/jwst-program-info/program/?program=5866):
  NIRISS/SOSS transmission.

GO 5866 public archive time-series products are an availability checkpoint
only: `public_archive_time_series_products; no_B2_interpretation`. No compact
wavelength-binned author spectrum is used, and B2 makes no NIRISS inference.

Primary citations are Moran et al. 2023,
[DOI 10.3847/2041-8213/accb9c](https://doi.org/10.3847/2041-8213/accb9c),
and the MIRI study,
[DOI 10.3847/2041-8213/ad8161](https://doi.org/10.3847/2041-8213/ad8161).
The two Zenodo records above cite the exact machine-readable products.

## Claim ceiling

The exact allowed claim is:

> The harness reproduces the pinned GO 1981 NIRSpec water-template regressions
> and exposes their reduction, detector-side, influential-bin, covariance, and
> nuisance sensitivity; no direct planet-versus-star origin comparison is
> available in the deposited products.

Do not claim a planetary-atmosphere or water detection, independent
confirmation, three independent reductions, reproduced POSEIDON posterior,
confirmed stellar contamination, definitive airlessness, a NIRISS resolution,
habitability, a biosignature, a technosignature, or evidence of life.

## Network-free tests

```bash
uv run python -m unittest discover -s tests -p 'test_gj486_*.py' -v
uv run python -m unittest discover -s tests -v
```

Tests use synthetic tables, in-memory HTTP responses, and generated ZIPs. They
cover signed amplitude recovery (positive, null, and negative), scale
invariance, covariance construction, schema/nonfinite/nonpositive/monotonicity
failures, download guards, checksum failures, path traversal, allowlisting,
canonical JSON, publisher smoothing, model ranking, and claim/provenance gates.
