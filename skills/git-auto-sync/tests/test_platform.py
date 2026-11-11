import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(SKILL_DIR / "scripts"))
import git_platform as platform_mod


class PlatformGuidanceTests(unittest.TestCase):
    def test_windows_keeps_powershell_guidance(self):
        guidance = platform_mod.auth_guidance("win32")
        self.assertIn("Windows PowerShell", guidance)
        self.assertIn("gh auth login", guidance)

    def test_macos_gets_terminal_not_powershell_guidance(self):
        guidance = platform_mod.auth_guidance("darwin")
        self.assertNotIn("PowerShell", guidance)
        self.assertIn("终端", guidance)
        self.assertIn("gh auth login", guidance)

    def test_linux_gets_generic_guidance(self):
        guidance = platform_mod.auth_guidance("linux")
        self.assertNotIn("PowerShell", guidance)
        self.assertIn("gh auth login", guidance)

    def test_unknown_platform_falls_back_to_generic(self):
        guidance = platform_mod.auth_guidance("plan9")
        self.assertIn("gh auth login", guidance)
        self.assertNotIn("PowerShell", guidance)

    def test_windows_is_the_only_full_support_platform(self):
        self.assertTrue(platform_mod.is_windows("win32"))
        self.assertFalse(platform_mod.is_windows("darwin"))


class DependencyCheckTests(unittest.TestCase):
    def test_git_available_returns_true_on_zero_exit(self):
        def runner(command):
            return 0

        self.assertTrue(platform_mod.git_available(runner=runner))

    def test_git_missing_returns_false_on_file_not_found(self):
        def runner(command):
            raise FileNotFoundError()

        self.assertFalse(platform_mod.git_available(runner=runner))

    def test_git_missing_returns_false_on_nonzero_exit(self):
        def runner(command):
            return 1

        self.assertFalse(platform_mod.git_available(runner=runner))

    def test_dependency_report_empty_when_git_present(self):
        report = platform_mod.check_dependencies(
            platform_name="win32", git_runner=lambda command: 0,
        )
        self.assertIsNone(report)

    def test_dependency_report_flags_missing_git(self):
        report = platform_mod.check_dependencies(
            platform_name="win32", git_runner=lambda command: 1,
        )
        self.assertEqual(report["status"], "missing_dependency")
        self.assertIn("git", report["error"])


if __name__ == "__main__":
    unittest.main()

