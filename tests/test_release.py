"""Release-structure and localization regression tests."""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def leaf_keys(value: object, prefix: str = "") -> set[str]:
    if not isinstance(value, dict):
        return {prefix}
    result: set[str] = set()
    for key, child in value.items():
        result |= leaf_keys(child, f"{prefix}.{key}" if prefix else key)
    return result


class ReleaseTests(unittest.TestCase):
    def test_options_menu_and_selector_labels_exist(self) -> None:
        folder = ROOT / "custom_components" / "my_wallet"
        expected_menu = {
            "settings",
            "add_contribution",
            "add_lot",
            "edit_contribution",
            "remove_contribution",
            "edit_lot",
            "add_dividend",
            "edit_dividend",
            "remove_dividend",
            "add_plan",
            "edit_plan",
            "remove_plan",
            "restore_execution",
            "add_valor",
            "edit_valor",
            "remove_valor",
        }
        for path in [
            folder / "strings.json",
            *(folder / "translations").glob("*.json"),
        ]:
            document = json.loads(path.read_text(encoding="utf-8"))
            menu = document["options"]["step"]["init"]["menu_options"]
            self.assertEqual(set(menu), expected_menu, path.name)
            selector_options = document["selector"]["allocation_mode"]["options"]
            self.assertEqual(set(selector_options), {"percentage", "fixed"})

    def test_translation_keys_match(self) -> None:
        folder = ROOT / "custom_components" / "my_wallet"
        sources = [folder / "strings.json", *(folder / "translations").glob("*.json")]
        documents = [json.loads(path.read_text(encoding="utf-8")) for path in sources]
        expected = leaf_keys(documents[0])
        for path, document in zip(sources[1:], documents[1:], strict=True):
            self.assertEqual(leaf_keys(document), expected, path.name)

    def test_manifest_version_and_no_generated_files(self) -> None:
        manifest = json.loads(
            (ROOT / "custom_components" / "my_wallet" / "manifest.json").read_text()
        )
        self.assertEqual(manifest["version"], "1.3.1")
        if not (ROOT / ".git").exists():
            return
        tracked = subprocess.check_output(
            ["git", "ls-files"], cwd=ROOT, text=True
        ).splitlines()
        unwanted = [
            path
            for path in tracked
            if "__pycache__" in Path(path).parts
            or Path(path).suffix in {".pyc", ".pyo"}
        ]
        self.assertEqual(unwanted, [])

    def test_english_sources_are_identical(self) -> None:
        folder = ROOT / "custom_components" / "my_wallet"
        self.assertEqual(
            json.loads((folder / "strings.json").read_text()),
            json.loads((folder / "translations" / "en.json").read_text()),
        )


if __name__ == "__main__":
    unittest.main()
