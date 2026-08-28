import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "k218_o005_detector_manifest.json"
PROTOCOL_PATH = ROOT / "docs" / "K218_O005_DETECTOR_PROTOCOL.md"
EXECUTION_PATH = ROOT / "docs" / "k218_o005_detector_execution.json"
EXECUTION_DOC_PATH = ROOT / "docs" / "K218_O005_DETECTOR_EXECUTION.md"
CONFIG_PATH = ROOT / "docs" / "k218_o005_detector_config.json"
ENVIRONMENT_PATH = ROOT / "docs" / "k218_o005_jwst_environment.txt"
MANIFEST_SHA256 = "0a57f12bffb436879d7a4905f3dc9ce5311561935e0a85fb0d0e4c58f5024a29"
PROTOCOL_SHA256 = "4525f4e73b8328a85b2a65de6f8dba03e8498e4f268265dc49dec77abb0c9096"
EXECUTION_SHA256 = "52b2a8931a20a06b701999878751b0f4fa1687aea61fb1c1cb0ff75f93fa0187"
EXECUTION_DOC_SHA256 = "d104856eef8e93333999729b98bdbc2594283988e080f4175a5f9c0533801d26"
CONFIG_SHA256 = "eedd9e1ffe86a8a877b3b09b7971895ccdb31d1b0421dbee8f873accdcbd2d68"
ENVIRONMENT_SHA256 = "a746c3e9bca763539dc1cf486113f996571ab9952e9f66295d1f407acf660cde"


class K218O005DetectorProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw_manifest = MANIFEST_PATH.read_bytes()
        cls.manifest = json.loads(cls.raw_manifest)
        cls.raw_execution = EXECUTION_PATH.read_bytes()
        cls.execution = json.loads(cls.raw_execution)
        cls.config = json.loads(CONFIG_PATH.read_bytes())

    def test_protocol_files_are_byte_frozen(self):
        self.assertEqual(hashlib.sha256(self.raw_manifest).hexdigest(), MANIFEST_SHA256)
        self.assertEqual(
            hashlib.sha256(PROTOCOL_PATH.read_bytes()).hexdigest(),
            PROTOCOL_SHA256,
        )
        self.assertEqual(hashlib.sha256(self.raw_execution).hexdigest(), EXECUTION_SHA256)
        self.assertEqual(
            hashlib.sha256(EXECUTION_DOC_PATH.read_bytes()).hexdigest(),
            EXECUTION_DOC_SHA256,
        )
        self.assertEqual(hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest(), CONFIG_SHA256)
        self.assertEqual(
            hashlib.sha256(ENVIRONMENT_PATH.read_bytes()).hexdigest(),
            ENVIRONMENT_SHA256,
        )

    def test_exact_uncal_inputs_are_frozen(self):
        actual = {
            item["segment_id"]: (item["uri"], item["size_bytes"], item["sha256"])
            for item in self.manifest["inputs"]
        }
        self.assertEqual(
            actual,
            {
                "seg001": (
                    "mast:JWST/product/jw02372005001_04102_00001-seg001_nrs2_uncal.fits",
                    1_461_867_840,
                    "a5e880e3bd470d76412a3044994644208f4c7e67843a50dc4ccc6eacdca2c600",
                ),
                "seg002": (
                    "mast:JWST/product/jw02372005001_04102_00001-seg002_nrs2_uncal.fits",
                    1_459_771_200,
                    "da600d989d378ee415700c06760cd1929fdf3e8cba9b5053029660fe6a14b3e2",
                ),
                "seg003": (
                    "mast:JWST/product/jw02372005001_04102_00001-seg003_nrs2_uncal.fits",
                    1_459_771_200,
                    "8461c14c6d47d594764c539041606710095d047012565489c3f6c1916f5abb3f",
                ),
            },
        )

    def test_pipeline_environment_and_effective_primary_config_are_exact(self):
        environment = self.manifest["environment"]
        self.assertEqual(environment["python_package"], "jwst==3.0.0")
        self.assertEqual(environment["crds_context"], "jwst_1584.pmap")
        self.assertEqual(environment["pipeline_invocation"], "PipelineClass.call")

        primary = self.manifest["primary_reduction"]
        self.assertEqual(primary["branch_id"], "both_stage_clean_fit_profile")
        self.assertEqual(
            {
                key: primary["detector1"]["clean_flicker_noise"][key]
                for key in (
                    "skip",
                    "fit_method",
                    "background_method",
                    "mask_science_regions",
                    "n_sigma",
                    "apply_flat_field",
                    "single_mask_requested",
                    "single_mask_effective",
                    "save_mask",
                    "save_background",
                    "save_noise",
                )
            },
            {
                "skip": False,
                "fit_method": "median",
                "background_method": "median_image",
                "mask_science_regions": False,
                "n_sigma": 1.5,
                "apply_flat_field": False,
                "single_mask_requested": True,
                "single_mask_effective": False,
                "save_mask": False,
                "save_background": False,
                "save_noise": False,
            },
        )
        self.assertIn(
            "effective value to false",
            primary["detector1"]["clean_flicker_noise"]["single_mask_note"],
        )
        self.assertEqual(
            primary["spec2"]["clean_flicker_noise"],
            {
                "skip": False,
                "fit_method": "median",
                "background_method": None,
                "mask_science_regions": False,
                "n_sigma": 1.5,
                "single_mask": True,
                "save_mask": False,
                "save_background": False,
                "save_noise": False,
            },
        )
        self.assertEqual(
            primary["spec2"]["pixel_replace"],
            {
                "skip": False,
                "algorithm": "fit_profile",
                "n_adjacent_cols": 5,
                "must_precede": "extract_1d",
            },
        )
        self.assertEqual(
            primary["spec2"]["background_subtraction"]["expected_status"],
            "SKIPPED",
        )
        self.assertTrue(primary["tso3"]["pixel_replace"]["skip"])

    def test_sensitivities_are_correlated_and_cannot_be_combined(self):
        branches = {item["branch_id"]: item for item in self.manifest["sensitivity_branches"]}
        self.assertEqual(
            set(branches),
            {
                "detector1_clean_only_fit_profile",
                "both_stage_clean_mingrad",
                "both_stage_clean_no_pixel_replace",
            },
        )
        self.assertTrue(
            all(item["role"] == "correlated_engineering_sensitivity" for item in branches.values())
        )
        combination = self.manifest["combination_contract"]
        self.assertTrue(combination["all_branches_share_photons"])
        self.assertFalse(combination["independent_reduction_evidence"])
        self.assertEqual(combination["pooling"], "forbidden")
        self.assertEqual(combination["voting"], "forbidden")
        self.assertEqual(combination["combined_z_score"], "forbidden")

    def test_storage_rule_is_fail_closed(self):
        storage = self.manifest["storage"]
        self.assertEqual(storage["staged_single_primary_ceiling_bytes"], 20_000_000_000)
        self.assertEqual(storage["multi_variant_ceiling_bytes"], 40_000_000_000)
        self.assertIn("only before retaining multiple", storage["rule"])

    def test_science_claim_boundary_remains_not_run(self):
        state = self.manifest["current_state"]
        self.assertEqual(state["execution_status"], "PARTIAL")
        self.assertEqual(state["pipeline_execution_status"], "COMPLETE")
        self.assertEqual(state["protocol_conformance"], "NONCONFORMING")
        self.assertEqual(state["wavelength_dependent_morphology"], "NOT_RUN")
        self.assertEqual(state["science_status"], "NOT_RUN")
        for field in ("molecule", "atmosphere", "origin", "biosignature"):
            self.assertEqual(state[field], "NOT_EVALUATED")
        for field in ("evidence_of_life", "b3_complete", "b3b_complete", "real_data_readiness"):
            self.assertFalse(state[field])

        claim = self.manifest["claim_contract"]
        self.assertTrue(claim["engineering_outputs_do_not_authorize_science"])
        self.assertEqual(
            claim["allowed_claim"],
            "This manifest records the detector-level engineering contract for the public GO-2372 o005 NRS2 inputs; execution evidence is separate and wavelength science remains unopened.",
        )
        prohibited = set(claim["prohibited_claims"])
        self.assertTrue(
            {
                "wavelength-dependent morphology result",
                "molecule identification",
                "biosignature",
                "evidence of life",
                "B3 or B3b completion",
                "real-data readiness",
            }
            <= prohibited
        )

    def test_execution_record_schema_requires_auditable_segment_records(self):
        schema = self.manifest["execution_record_schema"]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            set(schema["properties"]["overall_status"]["enum"]),
            {"NOT_RUN", "PARTIAL", "COMPLETE", "FAILED"},
        )
        self.assertEqual(
            set(schema["properties"]["pipeline_execution_status"]["enum"]),
            {"NOT_RUN", "PARTIAL", "COMPLETE", "FAILED"},
        )
        self.assertEqual(
            set(schema["properties"]["protocol_conformance"]["enum"]),
            {"NOT_EVALUATED", "CONFORMING", "NONCONFORMING"},
        )
        segment = schema["$defs"]["segment_record"]
        self.assertEqual(
            set(segment["properties"]["segment_id"]["enum"]),
            {"seg001", "seg002", "seg003"},
        )
        self.assertEqual(
            set(segment["required"]),
            {
                "segment_id",
                "input_verification",
                "stages",
                "cal_step_statuses",
            },
        )
        stage = schema["$defs"]["stage_record"]
        self.assertEqual(
            set(stage["required"]),
            {"status", "runtime_seconds", "peak_rss_bytes", "outputs"},
        )
        reference = schema["$defs"]["calibration_reference"]
        self.assertEqual(
            set(reference["required"]),
            {"cal_step", "reference_name", "size_bytes", "sha256"},
        )
        record_state = schema["properties"]["current_state"]["properties"]
        self.assertEqual(record_state["wavelength_dependent_morphology"]["const"], "NOT_RUN")
        self.assertEqual(record_state["science_status"]["const"], "NOT_RUN")
        for field in ("molecule", "atmosphere", "origin", "biosignature"):
            self.assertEqual(record_state[field]["const"], "NOT_EVALUATED")
        self.assertFalse(record_state["evidence_of_life"]["const"])
        self.assertFalse(record_state["b3_complete"]["const"])
        self.assertFalse(record_state["b3b_complete"]["const"])
        self.assertFalse(record_state["real_data_readiness"]["const"])

        completion = schema["allOf"][0]["then"]["properties"]
        self.assertEqual(completion["pipeline_execution_status"]["const"], "COMPLETE")
        self.assertEqual(completion["protocol_conformance"]["const"], "CONFORMING")
        self.assertEqual(completion["branch_id"]["const"], "both_stage_clean_fit_profile")
        self.assertEqual(completion["segments"]["minItems"], 3)
        self.assertEqual(completion["segments"]["maxItems"], 3)
        completed = schema["$defs"]["completed_segment"]["allOf"][1]["properties"]
        self.assertEqual(completed["input_verification"]["properties"]["status"]["const"], "VERIFIED")
        self.assertEqual(
            completed["cal_step_statuses"]["properties"]["spec2_background_subtraction"]["const"],
            "SKIPPED",
        )
        self.assertEqual(
            completed["cal_step_statuses"]["properties"]["tso3_pixel_replace"]["const"],
            "NOT_RUN",
        )
        not_run = schema["allOf"][1]["then"]["properties"]
        self.assertEqual(not_run["pipeline_execution_status"]["const"], "NOT_RUN")
        self.assertEqual(not_run["protocol_conformance"]["const"], "NOT_EVALUATED")
        partial = schema["allOf"][2]["then"]["properties"]
        self.assertIn("COMPLETE", partial["pipeline_execution_status"]["enum"])
        self.assertNotIn("CONFORMING", partial["protocol_conformance"]["enum"])
        failed = schema["allOf"][3]["then"]["properties"]
        self.assertEqual(failed["pipeline_execution_status"]["const"], "FAILED")
        self.assertEqual(failed["protocol_conformance"]["const"], "NONCONFORMING")

    def test_execution_record_is_fail_closed_and_hash_linked(self):
        record = self.execution
        self.assertEqual(record["protocol_manifest_sha256"], MANIFEST_SHA256)
        self.assertEqual(record["overall_status"], "PARTIAL")
        self.assertEqual(record["pipeline_execution_status"], "COMPLETE")
        self.assertEqual(record["protocol_conformance"], "NONCONFORMING")
        self.assertEqual(
            record["prospective_protocol_status"],
            "POST_EXECUTION_RECONSTRUCTION_NOT_PREREGISTERED",
        )
        self.assertEqual(record["environment"]["config_sha256"], CONFIG_SHA256)
        self.assertEqual(
            record["environment"]["dependency_snapshot_sha256"],
            ENVIRONMENT_SHA256,
        )
        self.assertEqual(
            [item["segment_id"] for item in record["segments"]],
            ["seg001", "seg002", "seg003"],
        )
        self.assertTrue(
            all(item["input_verification"]["status"] == "VERIFIED" for item in record["segments"])
        )
        self.assertTrue(
            all(item["stages"]["detector1"]["status"] == "COMPLETE" for item in record["segments"])
        )
        self.assertTrue(
            all(item["stages"]["spec2"]["status"] == "COMPLETE" for item in record["segments"])
        )
        self.assertTrue(
            all(item["stages"]["engineering_qc"]["status"] == "NOT_RUN" for item in record["segments"])
        )
        self.assertTrue(
            all(item["cal_step_statuses"]["tso3_pixel_replace"] == "NOT_RUN" for item in record["segments"])
        )
        self.assertTrue(
            all(
                item["cal_step_statuses"]["spec2_background_subtraction"] == "SKIPPED"
                for item in record["segments"]
            )
        )
        warning_codes = {item["code"] for item in record["warnings_or_errors"]}
        self.assertIn("POST_RUN_CONFIG_RECONSTRUCTION", warning_codes)
        self.assertIn("BAD_LIN_CORR_MNEMONIC_IGNORED", warning_codes)
        self.assertIn("AUXILIARY_CLEAN_PRODUCTS_NOT_SAVED", warning_codes)
        self.assertEqual(record["current_state"]["science_status"], "NOT_RUN")
        self.assertFalse(record["current_state"]["evidence_of_life"])

    def test_bad_lin_check_is_bitwise_and_post_run(self):
        provenance = self.config["provenance"]
        self.assertEqual(
            provenance["invocation_configuration"],
            "post_run_reconstruction_from_six_contemporaneous_resolved_pipeline_logs",
        )
        self.assertEqual(
            provenance["reference_dq_check"],
            "post_run_metadata_check_before_wavelength_science_access",
        )
        check = self.config["warnings_and_post_run_metadata_checks"][
            "linearity_bad_lin_corr_mnemonic_ignored"
        ]
        self.assertEqual(
            check["method"],
            "count_nonzero((DQ.astype(uint64) & uint64(8)) != 0)",
        )
        self.assertEqual(check["dq_pixels_checked"], 532_480)
        self.assertEqual(check["bitwise_set_pixels"], 0)
        self.assertFalse(check["raw_equality_used_as_conclusion"])
        self.assertEqual(
            check["recognized_global_flag_counts"],
            {
                "NONLINEAR_bit_65536": 1_884,
                "NO_LIN_CORR_bit_1048576": 10_740,
            },
        )
        warning = next(
            item
            for item in self.execution["warnings_or_errors"]
            if item["code"] == "BAD_LIN_CORR_MNEMONIC_IGNORED"
        )
        self.assertIn("DQ.astype(uint64) & uint64(8)", warning["disposition"])
        self.assertIn("zero set pixels", warning["disposition"])


if __name__ == "__main__":
    unittest.main()
