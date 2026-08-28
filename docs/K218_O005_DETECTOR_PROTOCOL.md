# K2-18 b o005 detector-level engineering protocol

## Status and boundary

This document records an engineering-only reduction contract for the three
public GO-2372 o005 NRS2 `uncal` segments. The configuration was captured and
saved after the detector/Spec2 engineering execution but before any
wavelength-dependent flux was opened. It is therefore not an externally
preregistered engineering run. The machine-readable contract is
[`k218_o005_detector_manifest.json`](k218_o005_detector_manifest.json).

All three primary Detector1 and Spec2 executions completed. Their exact
environment and requested/effective configuration are captured in
[`k218_o005_jwst_environment.txt`](k218_o005_jwst_environment.txt) and
[`k218_o005_detector_config.json`](k218_o005_detector_config.json); exact
inputs, outputs, logs, references, resource use, and header-only QC are in the
separate execution record. Wavelength-dependent morphology and science status
remain `NOT_RUN`. Molecule, atmosphere, origin, and biosignature states are
`NOT_EVALUATED`; evidence of life, B3/B3b completion, and real-data readiness
are false. A corrected extraction remains engineering evidence until the
separately frozen transit, covariance, null, and injection gates are
implemented and passed.

No wavelength-dependent flux, depth, feature amplitude, or morphology may be
opened under this protocol. It cannot update the existing C2/C3 result.

## Frozen inputs

All three payloads were hashed as complete local files and remain excluded from
Git:

| Segment | MAST product | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| seg001 | `jw02372005001_04102_00001-seg001_nrs2_uncal.fits` | 1,461,867,840 | `a5e880e3bd470d76412a3044994644208f4c7e67843a50dc4ccc6eacdca2c600` |
| seg002 | `jw02372005001_04102_00001-seg002_nrs2_uncal.fits` | 1,459,771,200 | `da600d989d378ee415700c06760cd1929fdf3e8cba9b5053029660fe6a14b3e2` |
| seg003 | `jw02372005001_04102_00001-seg003_nrs2_uncal.fits` | 1,459,771,200 | `8461c14c6d47d594764c539041606710095d047012565489c3f6c1916f5abb3f` |

Before processing, each local file must match both its exact byte count and
SHA-256. A mismatch is a hard failure.

## Frozen environment and primary reduction

Use `jwst==3.0.0` with `CRDS_CONTEXT=jwst_1584.pmap`. Invoke
`Detector1Pipeline.call()` and `Spec2Pipeline.call()` and preserve the logged
resolved configuration; do not treat constructor defaults as an execution
record. Record the Python version, dependency-snapshot hash, configuration
hash, and every logged CRDS reference filename, byte count, and SHA-256.

The primary branch is `both_stage_clean_fit_profile`:

1. Detector1 `clean_flicker_noise` is enabled with `fit_method=median`,
   `background_method=median_image`, `mask_science_regions=false`,
   `n_sigma=1.5`, and `apply_flat_field=false`. The logged requested
   `single_mask=true` is changed by `jwst 3.0.0` to an effective false because
   `median_image` requires a draft `rateints` product. That expected runtime
   adaptation must be reported. Mask, background, and noise diagnostic cubes
   were not saved; the three matching warning streams and output hashes were
   retained instead.
2. Spec2 `clean_flicker_noise` is also enabled, using `fit_method=median`, no
   background method, `mask_science_regions=false`, and `n_sigma=1.5`. Its
   mask, background, and noise diagnostic cubes were not saved.
3. Enable Spec2 `pixel_replace` with `algorithm=fit_profile` and
   `n_adjacent_cols=5`. It must run before `extract_1d`.
4. Keep TSO3 pixel replacement off to prevent double replacement.
5. A standard BOTS Level-2 association has no background member, so Spec2
   background subtraction is expected to be `SKIPPED`. This is not a failed
   attempt to enable a pipeline correction. Any future custom off-trace
   treatment requires a new freeze.

Process segments serially. Preserve logs and hashes before deleting an input or
intermediate. A failure, an unexpected warning-driven parameter change, an
unexpected calibration-step status, or a reference mismatch stops that segment
and is recorded rather than silently repaired. The expected `single_mask`
adaptation above is the only accepted runtime parameter change.

## Correlated sensitivity branches

After the primary branch is technically complete, the frozen engineering
sensitivities change one decision at a time:

- `detector1_clean_only_fit_profile` skips only the Spec2 rate-level flicker
  cleaning;
- `both_stage_clean_mingrad` replaces `fit_profile` with `mingrad`;
- `both_stage_clean_no_pixel_replace` skips Spec2 pixel replacement.

These branches reuse the same photons and are correlated views of one evidence
unit. Pooling, voting, combined z-scores, or describing them as independent
reductions is forbidden. The archived pipeline 2.0.1 / CRDS 1535 product is a
calibration-confounded diagnostic comparison, not a controlled sensitivity.

Engineering QC may report only detector-space and time-series behavior such as
the requested versus effective configuration, calibration-step statuses,
mask/replacement counts, column-correlated residual metrics, runtime, peak RSS,
and deterministic output hashes. It must not inspect or report a
wavelength-dependent feature.

## Storage rule

The 20,000,000,000-byte ceiling applies to one staged primary reduction with
verified hashes followed by cleanup. The completed staged footprint was about
11.35 GB of allocated disk, so the ceiling was not raised. Increase it to
40,000,000,000 bytes only before retaining multiple full variants or
diagnostic cubes. A single-segment pilot or staged primary does not justify the
increase.

## Execution records and completion

The manifest embeds a fail-closed JSON Schema for a separate execution record.
It permits `NOT_RUN`, `PARTIAL`, `COMPLETE`, or `FAILED` overall status and
records each segment independently. Each segment records input verification;
Detector1, Spec2, and engineering-QC status; runtime and peak RSS; output names,
sizes, and hashes; calibration-step statuses; and calibration reference names,
sizes, and hashes.

A one-segment pilot is `PARTIAL`, never full completion. `COMPLETE` is reserved
for all three verified inputs completing the primary Detector1, Spec2, and
engineering-QC stages with the expected effective configuration and complete
hash/reference records. The saved record does not meet that prospective
definition: its pipeline execution is `COMPLETE`, but overall status is
`PARTIAL`, protocol conformance is `NONCONFORMING`, and detector/time-series
engineering QC is `NOT_RUN`. Wavelength morphology and science status remain
`NOT_RUN`, and no molecule, atmosphere, origin, biosignature, life, B3/B3b,
readiness, or independent-replication claim is authorized.

Primary references:

- [JWST calibration context build table](https://jwst-crds.stsci.edu/display_build_contexts/)
- [JWST Build 13 context](https://jwst-crds.stsci.edu/browse/jwst_1584.pmap)
- [Official NIRSpec/BOTS pipeline notebook](https://github.com/spacetelescope/jwst-pipeline-notebooks/blob/main/notebooks/NIRSPEC/BOTS/JWPipeNB-NIRSpec-BOTS.ipynb)
- [NIRSpec/BOTS known issues](https://jwst-docs.stsci.edu/known-issues/nirspec-known-issues/nirspec-bots-known-issues)
