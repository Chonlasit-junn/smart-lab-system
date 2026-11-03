import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_policy import find_process_match, find_window_match
from program_identity import program_usage_name, read_executable_identity


class ProgramIdentityTests(unittest.TestCase):
    def setUp(self):
        self.rule = {"app_name": "StarRail", "match_type": "process_name_or_title",
                     "match_value": "StarRail", "enabled": True}

    def match(self, observed, identity):
        return find_process_match([self.rule], observed, executable_identity=identity)

    def test_title_alone_never_matches(self):
        self.assertIsNone(find_window_match([self.rule], "StarRail - Notepad"))
        self.assertIsNone(self.match("notepad.exe", {"original_filename": "NOTEPAD.EXE"}))

    def test_renamed_notepad_is_not_a_game(self):
        self.assertIsNone(self.match("StarRail.exe", {"original_filename": "NOTEPAD.EXE",
                                                     "product_name": "Honkai: Star Rail"}))

    def test_real_game_matches_even_when_renamed(self):
        for observed in ("StarRail.exe", "notes.exe"):
            with self.subTest(observed=observed):
                self.assertEqual(self.match(observed, {"original_filename": "StarRail.exe"}), self.rule)

    def test_missing_identity_does_not_guess_from_filename(self):
        self.assertIsNone(self.match("StarRail.exe", None))
        self.assertIsNone(self.match("StarRail.exe", {}))

    def test_product_fallback_is_exact_and_only_without_original_name(self):
        self.assertEqual(self.match("game.exe", {"product_name": "Honkai: Star Rail"}), self.rule)
        self.assertIsNone(self.match("game.exe", {"product_name": "StarRail Notes"}))

    def test_title_rule_is_inert_even_with_identity(self):
        self.rule["match_type"] = "window_title"
        self.assertIsNone(self.match("StarRail.exe", {"original_filename": "StarRail.exe"}))

    def test_path_alone_cannot_identify_a_renamed_editor(self):
        self.rule.update(match_type="exe_path", match_value=r"C:\StarRail.exe")
        self.assertIsNone(find_process_match([self.rule], "StarRail.exe", r"C:\StarRail.exe",
                                            {"original_filename": "notepad.exe"}))

    def test_missing_file_returns_no_identity(self):
        self.assertEqual(read_executable_identity("missing-identity-test.exe"), {})

    def test_usage_name_preserves_original_identity_after_exe_rename(self):
        self.assertEqual(
            program_usage_name("StarRail.exe", r"C:\Apps\StarRail.exe", {
                "original_filename": " NOTEPAD.EXE ",
                "internal_name": "notepad", "product_name": "Windows",
            }),
            "notepad.exe",
        )

    def test_usage_name_can_use_internal_identity_without_original_filename(self):
        self.assertEqual(
            program_usage_name("renamed.exe", r"C:\Apps\renamed.exe", {
                "original_filename": " ", "internal_name": "Editor.exe",
            }),
            "editor.exe",
        )

    def test_shared_product_name_does_not_merge_different_windows_apps(self):
        identity = {"product_name": "Microsoft Windows Operating System"}
        for observed in ("notepad.exe", "mspaint.exe"):
            with self.subTest(observed=observed):
                self.assertEqual(program_usage_name(observed, executable_identity=identity), observed)

    def test_usage_without_metadata_uses_image_basename_without_storing_path(self):
        self.assertEqual(
            program_usage_name("short.exe", r"C:\Program Files\Some App\Actual-App.EXE", {}),
            "actual-app.exe",
        )
        self.assertEqual(program_usage_name(" EDITOR.EXE ", None, {}), "editor.exe")

    def test_usage_without_any_image_name_is_not_guessed_from_product_name(self):
        self.assertIsNone(program_usage_name("", None, {"product_name": "Some Product"}))
        self.assertIsNone(program_usage_name(" ", " ", {}))

    def test_usage_normalizes_embedded_path_to_a_filename(self):
        self.assertEqual(
            program_usage_name("renamed.exe", executable_identity={
                "original_filename": r"C:\Build\NOTEPAD.EXE",
            }),
            "notepad.exe",
        )

    @unittest.skipUnless(os.name == "nt", "Windows version resource API")
    def test_real_notepad_copy_renamed_to_starrail_is_not_a_game(self):
        source = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "notepad.exe"
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "StarRail.exe"
            shutil.copyfile(source, target)
            identity = read_executable_identity(str(target))
            self.assertTrue(identity, "Windows EXE metadata must remain readable after renaming")
            self.assertIsNone(self.match(target.name, identity))
            self.assertEqual(program_usage_name(target.name, str(target), identity), "notepad.exe")
