# K2-18 b public o005 held-out preflight

## Outcome

The public May 2025 GO-2372 G395H visit is the highest-value held-out
replication target found in this milestone. It was not used in the published
C2/C3 benchmark. A metadata-only inspection nevertheless blocked a
claim-bearing Stage-3 analysis before any wavelength-dependent flux or depth
was examined.

The archived `x1dints` primary header records JWST pipeline `2.0.1`, CRDS
context `jwst_1535.pmap`, and all three directly relevant steps as `SKIPPED`:

- `S_CLNFNS`: flicker/1/f-noise cleaning;
- `S_PXREPL`: replacement of flagged pixels before extraction;
- `S_BKDSUB`: background subtraction.

STScI warns that uncorrected NIRSpec/BOTS 1/f noise can materially increase
time-series scatter and appear as irregular wavelength-dependent undulations,
especially on NRS2. It also warns that omitted pixel replacement can leave
spurious one-pixel absorption features. Both failure modes overlap the proposed
NRS2 4.3-micrometre morphology test. The standard product is therefore useful
for engineering exploration, but it cannot support a claim-bearing result.

No o005 wavelength-dependent morphology was fitted. The outcome is
`NOT_RUN / BLOCKED`, not a positive, negative, or null science result.

## Frozen public inventory

The machine-readable snapshot is
[`k218_o005_manifest.json`](k218_o005_manifest.json). The core observation is:

- MAST observation ID:
  `jw02372-o005_t001_nirspec_f290lp-g395h-s1600a1-sub2048`;
- observation: 2025-05-26 04:49:25–13:44:00 UTC;
- public release: 2026-05-26;
- 2,089 integrations at 14.432 seconds each in three segments;
- Stage-3 `x1dints`: 971,706,240 bytes, SHA-256
  `79d5957df2bc0a4c3c15e576bff2926c2316868131bd3ae9d6a3df3f94f2648b`;
- white-light ECSV: 231,355 bytes, SHA-256
  `e2105bfec8cd34f6ef32af2d9bd52fdccff5f545606aa48333803d3dce82cc1b`.

MAST exposes size and modification validators, not a cryptographic content
digest, so each SHA-256 above was computed after a complete guarded download.
Source products remain outside Git. The combined Stage-3 FITS primary header
says `DETECTOR=NRS1`, but its six `EXTRACT1D` extensions alternate detectors;
a future reader must select NRS2 from extension headers, specifically versions
2, 4, and 6.

The final planned GO-2372 G395H visit, observation o006, remains under exclusive
access until 2026-12-10. It is not used here.

## Deferred detector-level protocol

The future test is a separate prospective hypothesis,
`H-K218-O005-G395H-MORPH`. It must never be appended silently to the already
executed C2/C3 test.

Before opening wavelength-dependent results:

1. Start from o005 NRS2 `uncal` data and run group-level
   `clean_flicker_noise`; run pixel replacement before extraction and record the
   exact JWST/CRDS/environment hashes.
2. Freeze several extraction widths and treat them, plus the archived Stage-3
   spectrum, as correlated views of one visit. Never combine their z-scores or
   count them as independent evidence.
3. Preserve the existing global R=100 edges, NRS2-only 3.85–4.75 micrometre
   domain, 4.05–4.55 micrometre feature window, and signed intercept+slope+
   feature-fraction contrast.
4. Use `TDB-MID` integration times. The prospective transit centre is
   `60656.708449 + 5 * 32.940045 = 60821.408674` in
   BJD-TDB-minus-2,400,000.5. Broadband timing may refine that centre before
   wavelength depths are opened.
5. Freeze the transit and systematics model, externally generated
   wavelength-dependent limb-darkening priors, DQ masks, and robust outlier
   policy. A quadratic baseline is a sensitivity view, not a result-selected
   alternative.
6. Estimate the full 20-by-20 depth covariance with joint moving-block
   residual bootstraps across wavelength. Freeze block lengths and propagate
   timing and limb-darkening uncertainty.
7. Pass null and injected-feature recovery gates for false positives, coverage,
   and amplitude bias before unblinding.
8. Require a positive nominal contrast with retrospective `z>=2`, plus positive
   amplitude under every valid extraction, baseline, covariance, limb-darkening,
   and leave-one-bin-out sensitivity. Anything else is `SCIENCE_UNRESOLVED`.

Even a passing result would describe one held-out visit-level morphology only.
It could not identify a molecule, establish an atmosphere or origin, repair the
C2/C3 contradiction, complete B3/B3b, or support a biosignature or life claim.

## Storage decision

The held-out Stage-3 bundle is under 1 GB. The public NRS2 `uncal`, `rateints`,
`calints`, `crfints`, and per-segment `x1dints` products total about 14.3 GB,
before the 0.97 GB combined Stage-3 bundle, CRDS files, and local outputs. The
existing 20 GB ceiling is sufficient only with staged cleanup. Raising it to
40 GB would be justified if the detector-level experiment needs to retain
multiple full reduction variants and calibration caches; storage is not the
current blocker, so the ceiling was not changed.

References:

- [NIRSpec BOTS known issues](https://jwst-docs.stsci.edu/known-issues/nirspec-known-issues/nirspec-bots-known-issues)
- [JWST TSO Stage-3 pipeline](https://jwst-pipeline.readthedocs.io/en/latest/jwst/pipeline/calwebb_tso3.html)
- [JWST white-light product](https://jwst-pipeline.readthedocs.io/en/latest/jwst/white_light/description.html)
- [MAST API](https://mast.stsci.edu/api/v0/MastApiTutorial.html)
