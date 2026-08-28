from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

from k218_repeatability.analysis import run_benchmark
from k218_repeatability.manifest import load_manifest


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
# - {date: '__DATE__ 20:42'}
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


def table(reduction: str, visit: str) -> bytes:
    wave = 3.832 + 0.004 * np.arange(335)
    amplitude = 180.0 + (10.0 if visit == "visit_3" else 0.0)
    depth = 3000.0 + amplitude * ((wave >= 4.05) & (wave < 4.55))
    error_low = 35.0 + (np.arange(wave.size) % 3)
    error_high = error_low + 2.0
    rows: list[str] = []
    if reduction == "exoTEDRF":
        date = "2024-05-28" if visit == "visit_2" else "2024-12-12"
        for index, (centre, value, low_error, high_error) in enumerate(
            zip(wave, depth, error_low, error_high)
        ):
            rows.append(
                "NIRSPEC_G395H_NRS2,ExoTEP,uniform,"
                f"{index},{centre:.15g},{centre - 0.002:.15g},{centre + 0.002:.15g},"
                f"0,0,{value:.15g},{low_error:.15g},{high_error:.15g},0,0,0,none"
            )
        return (EXO_HEADER.replace("__DATE__", date) + "\n".join(rows) + "\n").encode()
    for centre, value, low_error, high_error in zip(wave, depth, error_low, error_high):
        rows.append(
            f"{centre:.15g} 0.002 {value / 1e6:.15g} "
            f"{low_error / 1e6:.15g} {high_error / 1e6:.15g}"
        )
    return (EUREKA_HEADER + "\n".join(rows) + "\n").encode()


class K218PipelineTests(unittest.TestCase):
    def test_network_free_pipeline_writes_canonical_deterministic_artifacts(self) -> None:
        base = load_manifest()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            extracted = root / "extracted"
            members = []
            for member in base.members:
                payload = table(member.reduction, member.visit)
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
            first = run_benchmark(extracted, first_dir, manifest)
            second = run_benchmark(extracted, second_dir, manifest)
            self.assertEqual(first, second)
            self.assertEqual(
                (first_dir / "k218_repeatability.json").read_bytes(),
                (second_dir / "k218_repeatability.json").read_bytes(),
            )
            self.assertEqual(
                hashlib.sha256((first_dir / "k218_repeatability.png").read_bytes()).hexdigest(),
                hashlib.sha256((second_dir / "k218_repeatability.png").read_bytes()).hexdigest(),
            )
            saved = json.loads((first_dir / "k218_repeatability.json").read_text())
            self.assertEqual(saved["execution_status"], "PASS")
            self.assertTrue(saved["retrospective"])
            self.assertFalse(saved["independent_reduction"])
            self.assertEqual(saved["planetary_origin"], "not_evaluated")
            self.assertEqual(saved["atmosphere"], "not_evaluated")
            self.assertEqual(saved["molecule"], "not_evaluated")
            self.assertEqual(saved["biosignature"], "not_evaluated")
            self.assertFalse(saved["evidence_of_life"])
            self.assertNotIn("timestamp", json.dumps(saved).lower())


if __name__ == "__main__":
    unittest.main()
