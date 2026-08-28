# Exploration plan

Version 0.1, frozen 2026-08-28.

## Objective

Build a sequence of reproducible experiments that can find and reject possible
signs of life without allowing an interesting plot to outrun the evidence. The
project has two independent tracks:

1. **Atmospheric biosignature assessment:** reproduce spectra and retrievals,
   test instrument, stellar, chemical and interior alternatives, and state the
   narrowest claim the data support.
2. **Radio technosignature search:** calibrate narrowband recovery and false
   positives, validate ON/OFF cadence logic, then run a preregistered search.

Neither track can validate the other. A molecule is not a technosignature, a
radio hit is not evidence of biological origin, and habitability is not life.

## What Phase 1 taught us

The Voyager benchmark recovered the three expected components at
8419.274374, 8419.297028 and 8419.319368 MHz. Their measured drift rates were
-0.397966, -0.377557 and -0.397966 Hz/s, all within 0.006 Hz/s of the frozen
reference values. The carrier was strongest at S/N 245.71; the sidebands were
S/N 31.22 and 30.61. The input was exactly 50,549,227 bytes with SHA-256
`c9a9a54f4140e3754ffb2455fae4eeb2eb70c8207123116ee953e4fce15c36ac`.

This establishes known-signal recovery for one morphology and dataset. It does
not establish calibrated survey sensitivity or reliable RFI classification.
The next radio milestone must therefore add injection/recovery surfaces and
ON/OFF negative controls before examining unknown candidates.

Other operational lessons:

- Freeze source URLs, byte counts, checksums, software versions and expected
  results before analysis.
- Treat a detection threshold as an algorithm setting, not a measured
  sensitivity; sensitivity comes from injections into representative data.
- Download size and data-license status are gates. The observation payloads
  stay outside Git unless redistribution is explicitly allowed.
- Start atmospheric work with published spectra and tables. Reprocessing raw
  JWST detector ramps is a later independent-reduction experiment.
- Multiple reductions of the same transit are correlated views of one evidence
  unit, not independent confirmations.
- Preserve negative and contradictory results. A clean null is a useful result.

## Ranked target portfolio

Archive holdings and approximate sizes are a metadata snapshot from
2026-08-28. Sizes refer to recommended science products where available, not
every raw and intermediate product.

| Rank | System | Role and first test | Public-data starting point | Why it belongs |
|---:|---|---|---|---|
| 1 | K2-18 b | Retrospective atmospheric controversy benchmark | Published spectra first; JWST GO-2722 and five public GO-2372 visits, about 7.8 GB of recommended products | Test whether CH4, CO2 and especially DMS/DMDS survive independent reductions, retrievals, molecule inventories and stellar models. |
| 2 | GJ 486 b | Stellar false-positive benchmark | Published GO-1981 NIRSpec spectrum/model tables; separate GO-1743 MIRI author-data constraint; GO-5866 NIRISS public archive time series only | Its water-like feature has explicit planetary-atmosphere and cool-starspot explanations, while the current deposited evidence remains origin-unresolved. |
| 3 | WASP-39 b | Atmospheric positive control | Published spectrum first; public JWST/HST data, about 32.2 GB of recommended JWST products | Recover a strong CO2 atmosphere before interpreting weaker sub-Neptune or rocky-planet spectra. This is a method control, not a life target. |
| 4 | TRAPPIST-1 system | Active-star and inner-planet controls; later radio cadence | Published spectra; extensive JWST/HST/K2/TESS holdings. BL filterbanks are roughly 0.35-0.81 GB per file | Use b/c as atmosphere-poor controls when testing e; validate stellar-contamination handling and an existing ON/OFF radio cadence. |
| 5 | LHS 1140 b | Temperate atmosphere/interior discrimination | Published spectra first; public JWST/HST/TESS. Full recommended JWST holdings are about 125.8 GB | Compare water-world, mini-Neptune and secondary-atmosphere explanations without presuming habitability. |
| 6 | Proxima Centauri system | Radio hard-negative benchmark | Published BLC1 products/subsets first; full Parkes campaign is TB-scale | Reproduce how an ON/OFF signal of interest was ultimately attributed to terrestrial interference. The planet does not transit. |
| 7 | TOI-700 d/e | Transit-pipeline and injection benchmark | Public TESS light curves, hundreds of MB; low-single-digit GB with pixel products | Test multi-sector detrending, ephemerides, shallow-signal recovery and selection completeness. |
| 8 | Kepler-186 f/system | Long-period transit/completeness control | About 113 MB of Kepler light curves; about 0.6 GB with target-pixel products | Recover a sparse 129.9-day transit and quantify detrending and long-period selection bias. |

The currently verified Breakthrough Listen targets in this portfolio are
TRAPPIST-1, LHS 1140 and Proxima Centauri. K2-18 b has already received a
published 544 MHz-9.8 GHz VLA/MeerKAT narrowband search with no viable
candidate. Its high-resolution technosignature products are request-only, so a
new K2-18 b radio analysis is not the first practical repository experiment.

## K2-18 b: live hypotheses, not a conclusion

As of the plan date, K2-18 b is securely a transiting, temperate sub-Neptune.
Its habitable-zone irradiation does not demonstrate a liquid ocean, a
habitable surface or life.

| Hypothesis | Current repository status | Test with existing public data | Stop condition |
|---|---|---|---|
| `H-K218-CH4` — methane is a robust planetary feature | Literature-supported; locally unverified | Reproduce across at least two reductions and retrieval codes, observing modes, leave-one-visit-out fits, opacity/noise variants and stellar models | If valid reductions disagree or one visit/detector dominates, report `pipeline_sensitive` |
| `H-K218-CO2` — carbon dioxide is independently recoverable | Supported but less mature than CH4 | Require consistent G395H abundance posteriors and held-out predictive improvement after detector offsets and alternative absorbers | If alternatives remain within the frozen evidence threshold, report `unidentified_or_blended_absorber` |
| `H-K218-DMS` — DMS/DMDS causes repeatable absorption | Not a robust detection | Compare flat, correlated-noise, DMS, DMDS and hydrocarbon/broad-inventory models with molecule-search multiplicity correction | If binning, reduction, red-noise or molecule inventory changes the result, stop before “molecule detected” |
| `H-K218-OCEAN` — observations favor a Hycean ocean | Unresolved | Compare self-consistent Hycean, gas-rich mini-Neptune, supercritical-water and magma-ocean models using held-out predictions | If any non-ocean model stays competitive, use only “consistent with”; present transmission data alone are insufficient |
| `H-K218-STAR` — stellar heterogeneity does not explain the spectrum | Active confounder | Jointly model K2 variability and HST/JWST epochs with spot/facula priors | If the 95% upper bound permits stellar contamination above half the feature amplitude, stop before planetary attribution |
| `H-K218-RADIO` — a repeatable narrowband transmitter is present | Published search found no viable candidate | Existing paper constrains only sampled frequencies, epochs, sensitivities and signal morphology | No archive-only null may become “no technology” or “no life”; promotion requires independent repeat observations |

CH4 and CO2 are compatible with many non-biological environments. Even a
future robust DMS detection would still require quantitative abiotic source and
sink tests before the phrase “potential biosignature” could be considered.

## Execution order

### Milestone A — freeze the evidence system

- Keep [`hypothesis_ledger.json`](hypothesis_ledger.json) under review.
- Add a per-dataset manifest with immutable identifiers, checksums, data rights,
  calibration context and independence groups.
- Add a per-run record with code/environment hashes, reduction choices, priors,
  convergence, exclusions and output hashes.
- Freeze each hypothesis, null, model family, multiplicity family, success gate
  and stopping rule before looking at the relevant unblinded result.

### Milestone B — smallest atmospheric proof of method

- [x] Recover WASP-39 b's strong CO2 feature from a published spectrum.
- [x] Reproduce the archived GJ 486 b NIRSpec water-template regressions and their sensitivity diagnostics; label the direct planet-versus-star comparison `not_evaluated`, preserve `science_unresolved`, and reproduce GO-1743 MIRI only as a separate fixed-model constraint.
- [ ] Run the identical retrieval harness on synthetic spectra with hidden truth.
- [ ] Only then run the frozen K2-18 b CH4 and CO2 replication.
- [ ] Treat the K2-18 b DMS/DMDS exercise as an adversarial model-comparison test,
   not a search optimized to recover sulfur.

### Milestone C — radio classification

1. Add synthetic positive/negative drift, band-edge, intermittent and RFI-like
   injections; publish completeness as a surface, not one percentage.
2. Activate the documented 1.45 GB HIP 56242 cadence for ON/OFF orchestration.
3. Reproduce the BLC1 selection and terrestrial-interference rejection using a
   reviewed, size-bounded subset.
4. Freeze a target-selection rule and conduct a blind public-data cadence
   search. A candidate is not required for success.

### Milestone D — scale only after gates pass

- Move from published spectra to independent raw-data reductions.
- Add TRAPPIST-1 and LHS 1140 b only with reviewed storage/compute budgets.
- Add TOI-700 and Kepler-186 injection/recovery experiments to quantify target
  selection and transit completeness.
- Seek new observations only for hypotheses that public data cannot decide,
  such as independent K2-18 b DMS confirmation, simultaneous stellar
  monitoring or repeat multi-observatory radio coverage.

## Claim ladder

Atmospheric: `validated dataset` -> `authentic feature` -> `planetary feature`
-> `identified molecule` -> `environment inference` -> `potential
biosignature candidate`.

Radio: `pipeline detection` -> `cadence event` -> `signal of interest` ->
`unexplained signal of interest` -> `candidate technosignature`.

The repository never automatically emits `evidence of life`. That judgment
requires new independent data, active exclusion of non-life explanations and
professional domain review.

## Primary and official sources

### K2-18 b

- [NASA Webb overview](https://science.nasa.gov/missions/webb/webb-discovers-methane-carbon-dioxide-in-atmosphere-of-k2-18-b/)
- [NASA Exoplanet Archive](https://exoplanetarchive.ipac.caltech.edu/overview/K2-18%20b)
- [JWST GO-2722](https://www.stsci.edu/jwst-program-info/program/?program=2722)
  and [GO-2372](https://www.stsci.edu/jwst-program-info/program/?program=2372)
- [Madhusudhan et al. 2023 near-infrared analysis](https://doi.org/10.3847/2041-8213/acf577)
- [Schmidt et al. independent reanalysis](https://doi.org/10.3847/1538-3881/ae019a)
- [Madhusudhan et al. MIRI DMS/DMDS analysis](https://doi.org/10.3847/2041-8213/adc1c8)
- [Luque et al. independent MIRI analysis](https://doi.org/10.1051/0004-6361/202555580)
- [Welbanks et al. standards-of-evidence assessment](https://doi.org/10.1038/s41550-025-02730-4)
- [Pica-Ciamarra et al. broad molecule search](https://doi.org/10.3847/2041-8213/ae5dcc)
- [Wogan et al. gas-rich mini-Neptune alternative](https://www.nature.com/articles/s41550-024-02216-9)
- [Tremblay et al. VLA/MeerKAT technosignature search](https://doi.org/10.3847/1538-3881/ae448e)

### Complementary targets and methods

- [GJ 486 b NASA assessment](https://science.nasa.gov/missions/webb/webb-finds-water-vapor-but-from-a-rocky-planet-or-its-star/)
- [WASP-39 b NASA CO2 assessment](https://science.nasa.gov/missions/webb/nasas-webb-detects-carbon-dioxide-in-exoplanet-atmosphere/)
- [NASA TRAPPIST-1 Webb assessment](https://science.nasa.gov/mission/webb/science-overview/science-explainers/what-is-webb-revealing-about-the-trappist-1-system/)
- [NASA LHS 1140 b assessment](https://science.nasa.gov/blogs/webb/2024/06/05/reconnaissance-of-potentially-habitable-worlds-with-nasas-webb/)
- [Official BLC1 evidence and data](https://seti.berkeley.edu/blc1/)
- [NASA TOI-700 d catalog](https://science.nasa.gov/exoplanet-catalog/toi-700-d/)
- [NASA Kepler-186 f catalog](https://science.nasa.gov/exoplanet-catalog/kepler-186-f/)
- [Catling et al. biosignature assessment framework](https://doi.org/10.1089/ast.2017.1737)
