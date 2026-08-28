from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

from k218_c1_context.analysis import analyze_spectra, classify_context, run_diagnostic
from k218_c1_context.manifest import ManifestError, load_manifest
from k218_repeatability.data import VisitSpectrum


EXO_HEADER = """# %ECSV 1.0
# ---
# datatype:
# - {name: instrname, datatype: string}
# - {name: reference, datatype: string}
# - {name: bandpass, datatype: string}
# - {name: iwave, datatype: int64}
# - {name: wave, unit: um, datatype: float64}
# - {name: waveMin, unit: um, datatype: float64}
# - {name: waveMax, unit: um, datatype: float64}
# - {name: xMin, datatype: int64}
# - {name: xMax, datatype: int64}
# - {name: yval, unit: ppm, datatype: float64}
# - {name: yerrLow, unit: ppm, datatype: float64}
# - {name: yerrUpp, unit: ppm, datatype: float64}
# - {name: wlcLow, datatype: float64}
# - {name: wlcUpp, datatype: float64}
# - {name: ignore, datatype: int64}
# - {name: referenceLink, datatype: string}
# delimiter: ','
# meta: !!omap
# - {visit: '1'}
# - {date: '2023-01-20 20:42'}
# schema: astropy-2.0
instrname,reference,bandpass,iwave,wave,waveMin,waveMax,xMin,xMax,yval,yerrLow,yerrUpp,wlcLow,wlcUpp,ignore,referenceLink
"""

EUREKA_HEADER = """# %ECSV 1.0
# ---
# datatype:
# - {name: wavelength, datatype: float64}
# - {name: bin_width, datatype: float64}
# - {name: rp^2_value, datatype: float64}
# - {name: rp^2_errorneg, datatype: float64}
# - {name: rp^2_errorpos, datatype: float64}
# schema: astropy-2.0
wavelength bin_width rp^2_value rp^2_errorneg rp^2_errorpos
"""


def synthetic_spectrum(reduction: str, amplitude_ppm: float) -> VisitSpectrum:
    edges = np.arange(3.83, 4.731, 0.01)
    lower = edges[:-1]
    upper = edges[1:]
    wave = (lower + upper) / 2
    sigma = np.full_like(wave, 15.0)
    depth = 3000.0 + amplitude_ppm * ((wave >= 4.05) & (wave < 4.55))
    return VisitSpectrum(
        reduction=reduction,
        visit="visit_1",
        detector="NRS2",
        wavelength_micrometres=wave,
        lower_micrometres=lower,
        upper_micrometres=upper,
        depth_ppm=depth,
        uncertainty_ppm=sigma,
        source_error_low_ppm=sigma,
        source_error_high_ppm=sigma,
        source_metadata={"synthetic": "true"},
    )


def table(reduction: str) -> bytes:
    wave = 3.832 + 0.004 * np.arange(335)
    depth = 3000.0 + 180.0 * ((wave >= 4.05) & (wave < 4.55))
    error_low = 35.0 + (np.arange(wave.size) % 3)
    error_high = error_low + 2.0
    rows: list[str] = []
    if reduction == "exoTEDRF":
        for index, (centre, value, low_error, high_error) in enumerate(
            zip(wave, depth, error_low, error_high)
        ):
            rows.append(
                "NIRSPEC_G395H_NRS2,ExoTEP,uniform,"
                f"{index},{centre:.15g},{centre - 0.002:.15g},{centre + 0.002:.15g},"
                f"0,0,{value:.15g},{low_error:.15g},{high_error:.15g},0,0,0,none"
            )
        return (EXO_HEADER + "\n".join(rows) + "\n").encode()
    for centre, value, low_error, high_error in zip(wave, depth, error_low, error_high):
        rows.append(
            f"{centre:.15g} 0.002 {value / 1e6:.15g} "
            f"{low_error / 1e6:.15g} {high_error / 1e6:.15g}"
        )
    return (EUREKA_HEADER + "\n".join(rows) + "\n").encode()


class C1ContextTests(unittest.TestCase):
    def test_manifest_is_frozen_and_isolated(self) -> None:
        manifest = load_manifest()
        self.assertEqual(manifest.canonical_sha256, "7e586d625c79a027b95802c7b408d1bd3962a42702fc5f9442dc48c8ffac6680")
        self.assertEqual({member.visit for member in manifest.members}, {"visit_1"})
        self.assertEqual(len(manifest.members), 2)
        self.assertEqual(manifest.output_contract["science_state"], "not_applicable_historical_context")
        raw = json.loads(
            (Path(__file__).parents[1] / "src/k218_c1_context/data_manifest.json").read_text()
        )
        raw["analysis"]["feature_micrometres"] = [4.0, 4.6]
        with tempfile.TemporaryDirectory() as temporary:
            changed = Path(temporary) / "manifest.json"
            changed.write_text(json.dumps(raw))
            with self.assertRaisesRegex(ManifestError, "frozen"):
                load_manifest(changed)

    def test_descriptor_requires_both_correlated_views(self) -> None:
        manifest = load_manifest()
        spectra = [
            ("eureka_visit_1_nrs2", synthetic_spectrum("Eureka", 180.0)),
            ("exotedrf_visit_1_nrs2", synthetic_spectrum("exoTEDRF", 170.0)),
        ]
        analysis = analyze_spectra(spectra, manifest)
        self.assertEqual(
            analysis["context"]["context_descriptor"],
            "positive_local_contrast_in_both_correlated_views",
        )
        self.assertFalse(analysis["evidence_structure"]["independent_reduction_evidence"])
        self.assertEqual(analysis["evidence_structure"]["pooling_with_go2372"], "prohibited_not_performed")
        one = classify_context(analysis["cells"][:1])
        self.assertEqual(one["context_descriptor"], "criterion_not_met")

    def test_network_free_pipeline_is_deterministic_and_fail_closed(self) -> None:
        base = load_manifest()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            extracted = root / "extracted"
            members = []
            for member in base.members:
                payload = table(member.reduction)
                path = extracted / member.path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
                members.append(
                    replace(
                        member,
                        size_bytes=len(payload),
                        sha256=hashlib.sha256(payload).hexdigest(),
                    )
                )
            manifest = replace(base, members=tuple(members))
            first_dir = root / "first"
            second_dir = root / "second"
            first = run_diagnostic(extracted, first_dir, manifest)
            second = run_diagnostic(extracted, second_dir, manifest)
            self.assertEqual(first, second)
            self.assertEqual(
                (first_dir / "k218_c1_context.json").read_bytes(),
                (second_dir / "k218_c1_context.json").read_bytes(),
            )
            self.assertEqual(
                hashlib.sha256((first_dir / "k218_c1_context.png").read_bytes()).hexdigest(),
                hashlib.sha256((second_dir / "k218_c1_context.png").read_bytes()).hexdigest(),
            )
            self.assertEqual(first["execution_status"], "PASS")
            self.assertEqual(first["science_state"], "not_applicable_historical_context")
            self.assertFalse(first["externally_preregistered"])
            self.assertFalse(first["independent_reduction_evidence"])
            self.assertEqual(first["comparison_to_go2372"], "descriptive_only_not_inferential")
            self.assertEqual(first["molecule"], "not_evaluated")
            self.assertFalse(first["evidence_of_life"])
            self.assertFalse(first["b3_completion"])
            self.assertFalse(first["b3b_completion"])
            self.assertFalse(first["real_data_readiness"])
            self.assertFalse(first["transparency"]["blind_or_pre_unblinded"])
            self.assertIn(
                "shorter out-of-transit time baseline",
                " ".join(first["transparency"]["limitations"]),
            )
            self.assertIn(
                "Schmidt et al.",
                " ".join(first["transparency"]["limitations"]),
            )
            self.assertNotIn("timestamp", json.dumps(first).lower())


if __name__ == "__main__":
    unittest.main()
