"""Synthetic contract tests only: these do not qualify any real Windows runner."""
import copy
import unittest

from qualify_windows_runner import qualify


def healthy_fixtures():
    preflight = {
        "schema": 1,
        "kind": "runner_preparation",
        "status": "capacity_prepared_not_acceptance",
        "operating_system": "Microsoft Windows 10.0.22631",
        "selected_work_root": "C:\\b3117\\123-1-abcdef01",
        "write_probes": [{"writable": True}],
        "repository": "wirarua-stack/3117-bim-studio",
        "commit": "fake-commit-sha",
        "run_id": "123",
        "run_attempt": "1",
        "desktop_observation": {
            "session_id": 1,
            "user_interactive": True,
            "window_station_visible": True,
            "monitor_count": 1,
            "virtual_screen": {"width": 1920, "height": 1080},
            "errors": [],
        },
    }
    opengl = {
        "schema": 1,
        "kind": "windows_opengl_capability_probe",
        "system": "Windows",
        "status": "compatible_for_further_gui_testing",
        "windows_gui_acceptance": "not_executed",
        "version": "4.6.0 NVIDIA",
        "vendor": "NVIDIA Corporation",
        "renderer": "NVIDIA GeForce Test",
    }
    return preflight, opengl


class RunnerQualificationContractTests(unittest.TestCase):
    def check_blocked(self, preflight, opengl, problem):
        report = qualify(preflight, opengl)
        self.assertEqual(report["status"], "blocked")
        self.assertIn(problem, report["reason_codes"])
        self.assertFalse(report["release_ready"])
        self.assertFalse(report["windows_automated_acceptance_passed"])
        self.assertFalse(report["qt_coin_gui_tests_executed"])

    def test_good_fixture_qualifies_for_attempt_not_acceptance(self):
        preflight, opengl = healthy_fixtures()
        report = qualify(preflight, opengl, expected_run_id="123",
                         expected_run_attempt="1", expected_sha="fake-commit-sha",
                         expected_repository="wirarua-stack/3117-bim-studio")
        self.assertEqual(report["status"], "eligible_for_gui_test_attempt")
        self.assertFalse(report["freecad_launch_test_executed"])
        self.assertFalse(report["windows_automated_acceptance_passed"])
        self.assertFalse(report["release_ready"])

    def test_confirmed_hosted_opengl_1_1_is_blocked(self):
        preflight, opengl = healthy_fixtures()
        opengl.update(version="1.1.0", vendor="Microsoft Corporation",
                      renderer="GDI Generic", status="incompatible")
        self.check_blocked(preflight, opengl, "opengl_below_2_0_or_unknown")

    def test_software_renderer_rejected_even_with_version_claim(self):
        preflight, opengl = healthy_fixtures()
        opengl["renderer"] = "llvmpipe (LLVM 16.0.0)"
        self.check_blocked(preflight, opengl, "opengl_known_software_fallback")

    def test_windows_service_session_is_not_interactive(self):
        preflight, opengl = healthy_fixtures()
        preflight["desktop_observation"].update(
            session_id=0, user_interactive=False, window_station_visible=False)
        self.check_blocked(preflight, opengl, "desktop_no_nonzero_session")

    def test_hidden_station_is_blocked(self):
        preflight, opengl = healthy_fixtures()
        preflight["desktop_observation"]["window_station_visible"] = False
        self.check_blocked(preflight, opengl, "desktop_window_station_not_visible")

    def test_no_monitor_is_blocked(self):
        preflight, opengl = healthy_fixtures()
        preflight["desktop_observation"]["monitor_count"] = 0
        self.check_blocked(preflight, opengl, "desktop_no_monitor")

    def test_winapi_failures_are_not_silently_ignored(self):
        preflight, opengl = healthy_fixtures()
        preflight["desktop_observation"]["errors"] = ["Access denied"]
        self.check_blocked(preflight, opengl, "desktop_winapi_errors_or_missing_record")

    def test_invalid_virtual_screen_is_blocked(self):
        preflight, opengl = healthy_fixtures()
        preflight["desktop_observation"]["virtual_screen"]["width"] = 0
        self.check_blocked(preflight, opengl, "desktop_invalid_virtual_screen")

    def test_missing_or_invalid_preflight_fails_closed(self):
        _, opengl = healthy_fixtures()
        self.check_blocked(None, opengl, "runner_preflight_missing_or_invalid")

    def test_missing_opengl_fails_closed(self):
        preflight, _ = healthy_fixtures()
        self.check_blocked(preflight, None, "opengl_probe_missing_or_invalid")

    def test_missing_successful_write_probe_is_blocked(self):
        preflight, opengl = healthy_fixtures()
        preflight["write_probes"] = [{"writable": False}]
        self.check_blocked(preflight, opengl, "runner_no_successful_write_probe")

    def test_provenance_must_match_current_workflow_run(self):
        preflight, opengl = healthy_fixtures()
        report = qualify(preflight, opengl, expected_run_id="124")
        self.assertEqual(report["status"], "blocked")
        self.assertIn("runner_run_id_provenance_mismatch", report["reason_codes"])

    def test_non_windows_preflight_is_not_a_gpu_qualification(self):
        preflight, opengl = healthy_fixtures()
        preflight["operating_system"] = "Linux"
        self.check_blocked(preflight, opengl, "runner_not_native_windows")

    def test_missing_desktop_evidence_is_blocked(self):
        preflight, opengl = healthy_fixtures()
        del preflight["desktop_observation"]
        self.check_blocked(preflight, opengl, "desktop_observation_missing")


if __name__ == "__main__":
    unittest.main()
