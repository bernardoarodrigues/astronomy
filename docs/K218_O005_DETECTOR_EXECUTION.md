# K2-18 b o005 detector engineering execution

## Outcome

The public GO-2372 o005 NRS2 inputs completed a serial `jwst==3.0.0` /
`jwst_1584.pmap` Detector1 and Spec2 engineering reduction. This is a technical
pipeline-completion result only: `pipeline_execution_status=COMPLETE`, overall
status `PARTIAL`, and `protocol_conformance=NONCONFORMING`. The resolved
configuration was reconstructed from the pipeline logs after execution and
before wavelength-science access; it was not externally preregistered. Exact
input, output, log, environment, configuration, context-map, and
calibration-reference hashes are recorded in
[`k218_o005_detector_execution.json`](k218_o005_detector_execution.json).

No wavelength-dependent flux, depth, spectrum, feature amplitude, or
morphology was opened. The wavelength-morphology and science states therefore
remain `NOT_RUN`; molecule, atmosphere, origin, and biosignature states remain
`NOT_EVALUATED`, and evidence of life is false.

## Header-only and log-only checks

These checks establish file integrity and pipeline bookkeeping. They are
metadata QC, not the missing detector-space or time-series engineering QC.

The three `x1dints` headers cover all 2,089 integrations without an integration
number gap:

| Segment | Integrations | Detector1 runtime / max RSS | Spec2 runtime / max RSS |
| --- | ---: | ---: | ---: |
| seg001 | 1-697 | 161.40 s / 15,249,588,224 B | 98.57 s / 5,339,332,608 B |
| seg002 | 698-1393 | 217.60 s / 15,261,794,304 B | 97.38 s / 5,344,919,552 B |
| seg003 | 1394-2089 | 163.18 s / 14,823,489,536 B | 97.99 s / 5,339,004,928 B |

Each `x1dints` primary header records `CAL_VER=3.0.0`,
`CRDS_CTX=jwst_1584.pmap`, `DETECTOR=NRS2`, `EXP_TYPE=NRS_BRIGHTOBJ`,
`S_CLNFNS=COMPLETE`, `S_PXREPL=COMPLETE`, and `S_EXTR1D=COMPLETE`.
`S_BKDSUB=SKIPPED` is expected because a standard BOTS Level-2 association has
no background member; it is not a failed background correction. `S_FLAT` and
`S_PHOTOM` are intentionally `SKIPPED` for this relative time-series
engineering branch.

The Spec2 logs contain one pixel-replacement entry per integration. They record
240,718 replacements across 697 integrations in seg001 (345-439 per
integration), 240,172 across 696 in seg002 (345-364), and 240,191 across 696 in
seg003 (345-357). These are pipeline-QC counts, not evidence for any spectral
feature. Pixel replacement is applied in memory after the saved `calints`, so
the `x1dints` header and ordered log, not the `calints` header, are the status
sources.

## Configuration provenance and warnings

All Detector1 logs requested `single_mask=true`. The pipeline emitted the same
warning in every segment and changed the effective value to false because the
`median_image` background method requires a draft `rateints` product. Both
Detector1 and Spec2 logs show `save_mask=false`, `save_background=false`, and
`save_noise=false`; no auxiliary diagnostic cubes were retained. The saved
configuration records both requested and effective values rather than
retroactively calling the effective value the requested one.

Spec2 emitted a non-fatal CRDS parameter lookup error for the unknown
`pars-targcentroidstep` reference type in each segment, then completed the BOTS
path. This warning and the absence of diagnostic cubes prevent treating the
run as a prospectively conforming validation. They do not change the narrower
fact that all three selected engineering paths produced hash-recorded outputs
with the expected terminal headers.

Detector1 also warned that `BAD_LIN_CORR` is not a recognized runtime DQ
mnemonic. A post-run metadata check evaluated
`count_nonzero((DQ.astype(uint64) & uint64(8)) != 0)` over all 532,480 pixels
in the selected linearity-reference DQ extension. It found zero pixels with
the declared raw bit 8 set; raw equality was not used to reach that conclusion.
The reference contains 1,884 `NONLINEAR` pixels under global bit 65,536 and
10,740 `NO_LIN_CORR` pixels under global bit 1,048,576. Their science-trace
impact remains part of future blinded QC; no science flux was inspected.

## Storage and science boundary

The staged inputs, CRDS cache, primary outputs, and logs occupied about 11.35
GB of allocated disk, below the 20,000,000,000-byte project ceiling. The 40 GB
ceiling was not activated. It becomes justified only for retained same-context
reduction variants or large diagnostic cubes.

This execution demonstrates a path that runs the 1/f cleaning and pixel
replacement skipped in the archived Stage-3 product. It does not supply the
frozen transit/systematics model, extraction-width sensitivities, joint
wavelength covariance, null calibration, or injection-recovery gates needed
before the held-out morphology can be opened. It therefore cannot update the
C1/C2/C3 result or support any molecular or life claim.
