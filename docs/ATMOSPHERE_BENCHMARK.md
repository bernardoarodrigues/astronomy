# Milestone B1 — atmospheric positive control

Milestone B1 is an isolated, deterministic harness for a published WASP-39 b
transmission spectrum. It tests whether this repository can recover a frozen,
known 4.3 µm spectral feature from a small publisher-supplied table before any
retrospective atmospheric target analysis is attempted.

## Sources and scope

The bundled manifest pins version 1 of the publisher archive:

- [Zenodo record, DOI 10.5281/zenodo.6959427](https://doi.org/10.5281/zenodo.6959427),
  CC-BY-4.0;
- [Nature paper, DOI 10.1038/s41586-022-05269-w](https://doi.org/10.1038/s41586-022-05269-w);
- [STScI DD-ERS program 1366](https://www.stsci.edu/jwst/science-execution/approved-programs/dd-ers/program-1366);
- [MAST WASP-39 b PRISM ERS data, DOI 10.17909/3tmh-4209](https://doi.org/10.17909/3tmh-4209).

The 375,091-byte Zenodo ZIP is checked against both publisher MD5
`578368eb0c86014462f109d1e8699693` and local SHA-256
`5f69e0279885104b49593aea7523903118895a0dadaaff47a5f6a1beda82f7fb`.
Only three allowlisted text members are extracted: the primary FIREFLy
spectrum and the published ScCHIMERA full/no-CO₂ model pair. The ZIP and
extracted members live under ignored `data/atmosphere/` paths.

## Frozen primary calculation

The gating input is
`ZENODO/TRANSMISSION_SPECTRA_DATA/FIREFLY_REDUCTION.txt`, verified as 7,833
bytes with SHA-256
`83e5e45d5867f1abe6a8776469d4284daf2630f66b7f67736453d912a6bfdd27`.
It must contain 95 ordered rows with wavelength centre, absolute transit
depth, bin width, and reported 1σ depth uncertainty.

Exactly the 20 unre-binned rows satisfying `4.10 <= wavelength <= 4.60` µm are
used. With `x = wavelength - 4.30`, the models are:

```text
M0 = beta0 + beta1*x
M1 = M0 + A*exp(-0.5*(x/0.10)^2)
```

`A` is signed. Both models use weighted least squares with the reported
diagonal variances. The expected regression fingerprint is `A=1.5007e-3`,
`z=15.51`, and delta-chi-squared `=240.5`. The gating bands are:

- `0.00148 <= A <= 0.00152`;
- `15.3 <= A/SE(A) <= 15.7`;
- `235 <= chi2(M0) - chi2(M1) <= 246`;
- every leave-one-bin-out fit has `A > 0` and `z >= 10`;
- scaling depths and uncertainties to ppm leaves `z` and delta-chi-squared
  unchanged to `1e-10`.

## Robustness diagnostics

Four assumed covariance stress models use

```text
Sigma_ij = sigma_i*sigma_j *
           [delta_ij + rho*exp(-abs(lambda_i-lambda_j)/ell)]
```

for `rho` in `{0.25, 0.5}` and `ell` in `{1, 2}` median bin widths. These are
not reconstructed JWST/FIREFLy covariance matrices. Each stress fit must keep
`z >= 5` and delta-chi-squared `>= 25`.

A fixed-seed (`6959427`) 10,000-draw simulation from fitted M0 checks the signed
feature statistic under the diagonal-noise null. It requires `|mean(z)| <
0.03`, standard deviation between 0.97 and 1.03, and 4–6% of draws outside
`|z| > 1.96`.

The ScCHIMERA full/no-CO₂ difference is included only as a non-gating,
model-dependent attribution diagnostic. It cannot establish abundance,
retrieval validity, or independent detection.

## Reproduce

```bash
uv sync
uv run atmosphere-benchmark download
uv run atmosphere-benchmark extract
uv run atmosphere-benchmark verify
uv run atmosphere-benchmark run
```

The downloader defaults to 2 MB and can never exceed the repository's 20 GB
hard limit. It preflights `Content-Length`, streams through byte and digest
guards, and atomically publishes only a verified ZIP. Extraction rejects path
traversal, absolute/drive-like paths, backslashes, duplicates, encryption,
symlinks, excess members, and excess uncompressed size. It extracts only the
three manifest members through an atomic temporary directory and verifies each
SHA-256 before publication.

Outputs are `artifacts/atmosphere/atmosphere_benchmark.json` and
`artifacts/atmosphere/atmosphere_feature.png`. JSON keys, member records,
leave-one-out fits, and stress models have canonical ordering; timestamps and
machine-specific paths are excluded.

## Claim boundary

The only allowed conclusion is:

> The harness recovers a strong, correctly located 4.3-µm feature in the pinned
> published FIREFLy spectrum, consistent with the CO2 band identified by the
> JWST ERS team.

This is not an independent detection or confirmation, a reproduction of the
paper's 26σ analysis, an abundance or metallicity inference, validation of raw
JWST reduction or general retrieval validity, or evidence for habitability, a
biosignature, technosignature, or life.

## Network-free tests

```bash
uv run python -m unittest discover -s tests -v
```

Atmospheric tests use generated spectra, in-memory HTTP responses, and
temporary ZIPs. They do not contact Zenodo or require the publisher archive.
