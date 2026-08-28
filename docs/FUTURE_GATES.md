# Future benchmark gates

These gates are intentionally out of scope for Phase 1. No Phase 2 or BLC1
payload was downloaded while creating this repository.

## Phase 2 — HIP 56242

Data curation identified an official compact Green Bank Telescope ABACAD
cadence at MJD 57532, centered at 1475.09765625 MHz. The exact archive query is:

<https://breakthroughinitiatives.org/opendatasearch?project=GBT&file_type=HDF5&mjd=57532.1&mjd_range=0.03&search=Search&perPage=100>

The six `.gpuspec.0002.h5` products total exactly 1,447,990,002 bytes
(approximately 1.45 GB). The MD5 values below are official archive metadata;
they have not been locally verified because Phase 2 data was not downloaded.

| Cadence position | Target / scan | Official source | Bytes | Archive MD5 |
|---|---|---|---:|---|
| A1 (ON) | HIP56242 0021 | [spliced_blc0001020304050607_guppi_57532_07456_HIP56242_0021.gpuspec.0002.h5](https://bldata.berkeley.edu/pipeline/AGBT16A_999_200/holding/spliced_blc0001020304050607_guppi_57532_07456_HIP56242_0021.gpuspec.0002.h5) | 241,256,281 | `66c6e248a56cb471200138876498edc6` |
| B (OFF) | HIP55382 0022 | [spliced_blc0001020304050607_guppi_57532_07807_HIP55382_0022.gpuspec.0002.h5](https://bldata.berkeley.edu/pipeline/AGBT16A_999_200/holding/spliced_blc0001020304050607_guppi_57532_07807_HIP55382_0022.gpuspec.0002.h5) | 241,200,670 | `c6e3fcf17a47799f9509ca1513c0ea1a` |
| A2 (ON) | HIP56242 0023 | [spliced_blc0001020304050607_guppi_57532_08157_HIP56242_0023.gpuspec.0002.h5](https://bldata.berkeley.edu/pipeline/AGBT16A_999_200/holding/spliced_blc0001020304050607_guppi_57532_08157_HIP56242_0023.gpuspec.0002.h5) | 241,491,975 | `0f4330705d3f0e2222aa2a33694af272` |
| C (OFF) | HIP55428 0024 | [spliced_blc0001020304050607_guppi_57532_08494_HIP55428_0024.gpuspec.0002.h5](https://bldata.berkeley.edu/pipeline/AGBT16A_999_200/holding/spliced_blc0001020304050607_guppi_57532_08494_HIP55428_0024.gpuspec.0002.h5) | 241,740,167 | `352682fb311f167e25b30a7affc5840d` |
| A3 (ON) | HIP56242 0025 | [spliced_blc0001020304050607_guppi_57532_08831_HIP56242_0025.gpuspec.0002.h5](https://bldata.berkeley.edu/pipeline/AGBT16A_999_200/holding/spliced_blc0001020304050607_guppi_57532_08831_HIP56242_0025.gpuspec.0002.h5) | 241,206,213 | `ee73921156d6a00d99364e62cdf4e1eb` |
| D (OFF) | HIP55603 0026 | [spliced_blc0001020304050607_guppi_57532_09173_HIP55603_0026.gpuspec.0002.h5](https://bldata.berkeley.edu/pipeline/AGBT16A_999_200/holding/spliced_blc0001020304050607_guppi_57532_09173_HIP55603_0026.gpuspec.0002.h5) | 241,094,696 | `75b8020e715bd54a1924c83f956ff6da` |

These approximately 3 kHz frequency-resolution / 1 s time-resolution products
are suitable inputs for cadence orchestration and ON/OFF validation. They are
not the final data products for measuring narrowband-search sensitivity. The
corresponding high-resolution set is approximately 92.54 GB and therefore
exceeds the current 20 GB download ceiling; it must not be fetched without a
separately reviewed scope and explicit authorization.

### Activation prerequisites

Phase 2 remains inactive until all of the following are complete:

1. Preregister the target selection, search space, thresholds, candidate cuts,
   acceptance criteria, exclusions, and stopping rules before examining
   unblinded candidate results.
2. Freeze a machine-readable manifest and checksum lock. Confirm every byte
   count and archive MD5 after download, add a locally computed SHA-256, record
   data-license status, and preserve immutable provenance where available.
3. Measure injection/recovery completeness as surfaces across signal strength,
   drift rate, frequency position, linewidth, duty cycle, and RFI occupancy;
   one aggregate recovery percentage is insufficient.
4. Perform lower-threshold forced measurements in every OFF scan at each ON-hit
   frequency and drift trajectory, rather than treating a thresholded OFF
   nondetection as proof of absence.
5. Run label-permutation and null controls, including shuffled ON/OFF labels,
   OFF-as-ON searches, time reversal where valid, and noise-only/synthetic
   controls with prespecified false-positive metrics.
6. Search the full observed band for combs, harmonics, mirrored features,
   clock structure, and intermodulation products before promoting any hit.
7. Require an independent implementation to reproduce candidate generation,
   ON/OFF measurements, rejection decisions, and completeness results.
8. Enforce strict claim vocabulary: an algorithmic threshold crossing is a
   `pipeline detection`; a detection surviving internal checks may be a
   `signal of interest`; `technosignature candidate` requires independent
   replication and follow-up; archive-only analysis is never `evidence of
   life`.

Synthetic or reduced fixtures must keep CI independent of these payloads, and
activation must add a new manifest without changing the frozen Phase 1 result
contract.

## BLC1

BLC1 should remain a later, separate validation gate. Before activation it
needs an immutable, license-reviewed data selection; an explicit compute and
download budget; a versioned analysis protocol; and independent review of the
expected outputs. It must not inherit Voyager thresholds or known-signal
expectations by analogy.

Adding either gate requires a new manifest entry and must not silently change
the frozen Phase 1 result contract.
