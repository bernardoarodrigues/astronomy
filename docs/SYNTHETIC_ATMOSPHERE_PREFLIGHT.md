# B3a synthetic atmospheric engineering preflight

Milestone B3a is a compact public **engineering preflight**. It is not the
sealed B3 hidden scientific gate, does not establish real-data readiness, and
does not authorize a K2-18 b analysis. Its fixed output states are:

```text
execution_status = complete | error
engineering_preflight_status = PASS | INCOMPLETE
science_state = not_applicable_synthetic
real_data_readiness = not_established
```

A B3a `PASS` would mean only that this public smoke suite met its frozen gates
in the locked environment. It must never be described as “B3 complete.” The
current frozen v1 run is `INCOMPLETE`, which is an honest and useful result.

## Frozen source and non-use of observed depths

The bundled manifest is
[`src/synthetic_atmosphere_benchmark/data_manifest.json`](../src/synthetic_atmosphere_benchmark/data_manifest.json).
It reuses the corrected CC BY 4.0 Zenodo v3 record
[10.5281/zenodo.10408056](https://doi.org/10.5281/zenodo.10408056), cited by
[Moran et al. 2023](https://doi.org/10.3847/2041-8213/accb9c). No additional
download is needed after B2 extraction.

| Role | Member bytes | SHA-256 |
|---|---:|---|
| Eureka grid/widths/uncertainties | 7,436 | `8f39a23b236e0985f53db785bf46ae840a1e6830a73a82032643659fbe001733` |
| PICASO 1-bar water model | 27,730 | `3046872ef36ddc946de8eb774cfecb063650b393c86b304a9c46bcc5c9b70abc` |
| PHOENIX stellar models | 941,330 | `96e33d11190d685942e447d08361c88bf3d58533a3f3b46eab42505d911faeca` |

The loader selects the 109 Eureka rows at wavelength >= 2.87 micrometres and
reads only wavelength, bin width, and reported 1-sigma uncertainty. It never
parses or returns the observed transit-depth column. It likewise reads only
the M1 and M3 model rows from the stellar file, never the V1/V2 observations.

The planet template converts the author PICASO transit-depth model to ppm,
piecewise-linearly averages it over every Eureka bin, and projects it against
the nuisance design. The stellar template is `(M3/M1 - 1)` in ppm,
center-interpolated onto the Eureka grid with constant endpoint handling, then
projected identically. Both have unit nuisance-projected diagonal matched-
filter norm. Their frozen weighted correlation is
`-0.45253880950231695`; all grid/template byte hashes are in the manifest.

Downloaded data and generated artifacts remain outside Git under the existing
`data/gj486/` and `artifacts/` ignore rules.

## Exact synthetic model

For every public case,

```text
y = c + b*x + d*I(wavelength >= 3.8 um) + ap*tp + as*ts + L*z
L L^T = Sigma
```

`ap` and `as` remain signed. The nuisance basis is an intercept, centered
linear wavelength trend, and NRS2 step. The evaluator uses exact generalized
least squares and exact Gaussian 50%, 80%, and 95% coefficient intervals.
Covariance is either diagonal or within-detector AR(1), with zero covariance
across the NRS1/NRS2 gap. Every case is evaluated twice:

1. with the covariance declared in the truth-free challenge;
2. with a deliberately naive diagonal covariance.

Only the correct-covariance branch is gated. The naive branch is a
non-promotional diagnostic.

## Generator, evaluator, and scorer separation

- `generator.py` owns synthetic case construction and emits separate
  `ChallengeBundle` and `TruthBundle` objects.
- `evaluator.py` imports neither generator nor truth code. Its API accepts only
  a validated `ChallengeBundle`.
- `scorer.py` joins the frozen predictions to truth after evaluation and counts
  errors or missing predictions as failures rather than dropping them.

The challenge includes public grid/templates and covariance declarations, but
no family, injection coefficient, replicate number, seed, or expected class.
Case IDs and presentation order use non-semantic deterministic hashes with
independent domains. They are deliberately **not secret**: because the public
generator and family inventory are available, an evaluator can enumerate the
truth mapping. B3a therefore tests API separation, not blinding.
For each `(family, replicate, stream)`, a stable SHA-256-derived spawn key is
passed to NumPy `SeedSequence`, `PCG64DXSM`, and `Generator`. Results are
therefore independent of family loop order. The manifest freezes the bit
generator, 128-bit root entropy, spawn-key mapping, and contract hash. NumPy's
[parallel RNG guidance](https://numpy.org/doc/stable/reference/random/parallel.html)
motivates this explicit stream construction.

## Public suites and predeclared smoke gates

There are exactly 72 cases in each family, 648 total:

- null and correlated null;
- strong and weak planet;
- stellar only and detector only;
- planet plus stellar;
- an omitted-template signal;
- a deliberately conflicting signed-cancellation combination. The templates
  remain identifiable (weighted correlation `-0.453`); this is a decision-rule
  stress case, not a mathematical non-identifiability claim.

The frozen promotion threshold is one-sided `z >= 3`. Lack of fit is flagged
at four standard deviations above the expected chi-squared. The correct-
covariance smoke gates are:

| Metric | Gate |
|---|---:|
| Pooled unsafe over-specific classification over negative/confounded cases | <= 2% |
| Maximum per-family unsafe over-specific classification | <= 2% |
| Strong-planet power | >= 80% |
| Stellar-only power | >= 80% |
| Joint recovery | >= 70% |
| Weak-planet promotion / abstention | <= 20% / >= 70% |
| Omitted-template model-inadequacy classification | >= 75% |
| Signed-cancellation conflict classification | >= 70% |
| 50% / 80% / 95% aggregate interval coverage | 46-54% / 77-83% / 93-97% |
| Absolute mean planet and stellar coefficient bias | <= 0.20 |
| Pull mean / standard deviation | absolute mean <= 0.10 / 0.90-1.10 |
| Determinism, fraction/percent, micrometre/nanometre, order invariance | all true |

These 72-case cells are smoke tests, not precise estimates of a real or
synthetic unsafe-classification rate. B3b requires 2,000 cases per negative family,
1,000 per power cell, and 2,000 per key coverage cell, with secret entropy,
HMAC-derived identifiers, independent custody/scoring, preregistered digests,
exact binomial gates, and no post-reveal tuning.

## Reproduce

First prepare the pinned B2 source if it is not already present:

```bash
uv sync
uv run gj486-benchmark download --source nirspec
uv run gj486-benchmark extract --source nirspec
uv run synthetic-atmosphere-benchmark verify
uv run synthetic-atmosphere-benchmark run
```

The run writes canonical, timestamp-free JSON plus a deterministic plot to
`artifacts/synthetic-atmosphere/`:

- `challenge.json`
- `truth.json` (public development truth; never consumed by the evaluator)
- `predictions.json`
- `synthetic_atmosphere_preflight.json`
- `synthetic_atmosphere_preflight.png`

Repeated runs in the same locked environment must have identical hashes.

## Frozen v1 result

The public run completed all 648 cases and passed strong-planet, stellar, and
joint recovery; weak-signal restraint; coefficient-bias; aggregate 50/80/95
coverage; pull; and all determinism/unit/order checks. It remains `INCOMPLETE`
because:

- pooled unsafe over-specific classification was 20/432 = 4.63%, above 2%;
- maximum per-family unsafe over-specific classification was 17/72 = 23.61%, above 2%;
- omitted-template model-inadequacy classification was 36/72 = 50%, below 75%;
- signed-cancellation conflict classification was 31/72 = 43.06%, below 70%.

An adversarial prerelease review corrected misleading metric/family names and
added the missing maximum-family safeguard without changing any synthetic
draw, threshold, injection, or existing decision result. After that corrected
canonical v1 contract was finalized, no gate was changed in response to the
result. A future v2 must be designed and preregistered as a new benchmark
contract, not silently tuned against these revealed cases.

## Claim ceiling

The manifest's exact allowed claim is:

> The public B3a synthetic engineering preflight executed the frozen linear-
> Gaussian challenge and met its predeclared smoke gates in the locked
> environment. This is not the sealed B3 scientific gate and is not evidence
> about any real atmosphere.

Because v1 is incomplete, that success sentence is not currently available.
The manifest instead freezes this permitted report: “The B3a public synthetic
preflight executed all 648 cases but remains incomplete because unsafe-
specific-classification and diagnostic-classification gates were not met.”

Never claim B3 completion, K2-18 b authorization, a validated atmospheric
retrieval, readiness to detect K2-18 b, a real atmosphere or molecule,
biosignature, habitability, life, a real-data false-positive rate, or
robustness to unknown systematics.

## Network-free tests

```bash
uv run python -m unittest discover -s tests -p 'test_synthetic_*.py' -v
uv run python -m unittest discover -s tests -v
```

Tests use small generated grids and local temporary files. They cover manifest
and claim tampering, source checksums, proof that observed depths are not
parsed, malformed/nonfinite/nonpositive/nonmonotonic data, template binning,
signed amplitude recovery, null/negative behavior, covariance construction,
truth-free evaluator boundaries, per-case stream/order invariance, canonical
serialization, and depth/wavelength unit invariance.
