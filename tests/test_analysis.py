from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from voyager_benchmark.analysis import (
    AnalysisError,
    Hit,
    evaluate_known_signal_recovery,
    parse_turbo_seti_dat,
)
from voyager_benchmark.manifest import load_manifest


class AnalysisTests(unittest.TestCase):
    def test_parses_and_sorts_official_shape_fixture(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "turbo_seti_hits.dat"
        hits = parse_turbo_seti_dat(fixture)
        self.assertEqual([hit.top_hit_number for hit in hits], [1, 2, 3])
        self.assertEqual(hits[1].uncorrected_frequency_mhz, 8419.297028)

    def test_all_known_targets_recover(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "turbo_seti_hits.dat"
        recovery = evaluate_known_signal_recovery(
            load_manifest(), parse_turbo_seti_dat(fixture)
        )
        self.assertTrue(recovery["passed"])
        self.assertTrue(all(item["recovered"] for item in recovery["targets"]))

    def test_missing_required_target_fails(self) -> None:
        carrier_only = [
            Hit(
                top_hit_number=1,
                drift_rate_hz_per_s=-0.37,
                snr=100.0,
                uncorrected_frequency_mhz=8419.297028,
                corrected_frequency_mhz=8419.297028,
            )
        ]
        recovery = evaluate_known_signal_recovery(load_manifest(), carrier_only)
        self.assertFalse(recovery["passed"])

    def test_drift_outside_tolerance_fails_target(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "turbo_seti_hits.dat"
        hits = parse_turbo_seti_dat(fixture)
        wrong_drift = [
            Hit(
                top_hit_number=hit.top_hit_number,
                drift_rate_hz_per_s=(
                    0.5 if hit.top_hit_number == 2 else hit.drift_rate_hz_per_s
                ),
                snr=hit.snr,
                uncorrected_frequency_mhz=hit.uncorrected_frequency_mhz,
                corrected_frequency_mhz=hit.corrected_frequency_mhz,
            )
            for hit in hits
        ]
        recovery = evaluate_known_signal_recovery(load_manifest(), wrong_drift)
        carrier = next(
            item for item in recovery["targets"] if item["id"] == "carrier"
        )
        self.assertTrue(carrier["frequency_within_tolerance"])
        self.assertFalse(carrier["drift_within_tolerance"])
        self.assertFalse(recovery["passed"])

    def test_carrier_must_be_strongest(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "turbo_seti_hits.dat"
        hits = parse_turbo_seti_dat(fixture)
        weak_carrier = [
            Hit(
                top_hit_number=hit.top_hit_number,
                drift_rate_hz_per_s=hit.drift_rate_hz_per_s,
                snr=10.0 if hit.top_hit_number == 2 else hit.snr,
                uncorrected_frequency_mhz=hit.uncorrected_frequency_mhz,
                corrected_frequency_mhz=hit.corrected_frequency_mhz,
            )
            for hit in hits
        ]
        recovery = evaluate_known_signal_recovery(load_manifest(), weak_carrier)
        self.assertTrue(recovery["required_targets_passed"])
        self.assertFalse(recovery["carrier_strongest"])
        self.assertFalse(recovery["passed"])

    def test_malformed_hit_row_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            path = Path(raw_dir) / "bad.dat"
            path.write_text("1 2 3\n", encoding="utf-8")
            with self.assertRaisesRegex(AnalysisError, "at least 5"):
                parse_turbo_seti_dat(path)


if __name__ == "__main__":
    unittest.main()
