"""Release-structure and localization regression tests."""

from __future__ import annotations

import json
import re
import subprocess
import tomllib
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


def leaf_values(value: object, prefix: str = "") -> dict[str, str]:
    if not isinstance(value, dict):
        return {prefix: str(value)}
    result: dict[str, str] = {}
    for key, child in value.items():
        result |= leaf_values(child, f"{prefix}.{key}" if prefix else key)
    return result


class ReleaseTests(unittest.TestCase):
    def test_options_menu_and_selector_labels_exist(self) -> None:
        folder = ROOT / "custom_components" / "my_wallet"
        expected_menu = {
            "settings",
            "add_contribution",
            "plan_contribution",
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

        expected_values = leaf_values(documents[0])
        placeholder_pattern = re.compile(r"{([A-Za-z0-9_]+)}")
        for path, document in zip(sources[1:], documents[1:], strict=True):
            actual_values = leaf_values(document)
            for key, expected_value in expected_values.items():
                self.assertEqual(
                    set(placeholder_pattern.findall(actual_values[key])),
                    set(placeholder_pattern.findall(expected_value)),
                    f"{path.name}: {key}",
                )

    def test_release_versions_and_metadata(self) -> None:
        manifest = json.loads(
            (ROOT / "custom_components" / "my_wallet" / "manifest.json").read_text()
        )
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())
        hacs = json.loads((ROOT / "hacs.json").read_text())
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

        self.assertEqual(manifest["version"], "1.9.0")
        self.assertEqual(project["project"]["version"], "1.9.0")
        self.assertIn("## 1.9.0", changelog)
        self.assertEqual(hacs["homeassistant"], "2026.8.0")
        self.assertEqual(project["project"]["requires-python"], ">=3.14.2")
        self.assertEqual(manifest["codeowners"], ["@PenDrag92"])
        self.assertEqual(
            manifest["documentation"],
            "https://github.com/PenDrag92/ha-my-wallet-custom",
        )
        self.assertEqual(
            manifest["issue_tracker"],
            "https://github.com/PenDrag92/ha-my-wallet-custom/issues",
        )

    def test_release_notes_describe_ledger_hardening(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        audit = (ROOT / "AUDIT.md").read_text(encoding="utf-8")
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

        self.assertIn("## 1.3.2", changelog)
        for text in (readme, audit, changelog):
            self.assertIn("opening", text.lower())
            self.assertIn("cash", text.lower())
        self.assertIn("not an independent", audit)
        self.assertIn("security certification", audit)

    def test_position_selection_precedes_its_metrics_and_alias_keeps_symbol(
        self,
    ) -> None:
        source = (
            ROOT / "custom_components" / "my_wallet" / "frontend" / "my-wallet-panel.js"
        ).read_text(encoding="utf-8")
        self.assertLess(
            source.index("this._renderPositionSelection(main, wallet);"),
            source.index("this._renderStats(main, wallet, position);"),
        )
        self.assertIn('first.append(node("span", item.symbol, "hint"))', source)
        self.assertIn('this._call("position_aliases"', source)

    def test_no_generated_files_are_tracked(self) -> None:
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

    def test_validation_workflow_is_complete_and_pinned(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text()
        expected_actions = {
            "actions/checkout",
            "actions/setup-python",
            "hacs/action",
            "home-assistant/actions/hassfest",
        }
        for action in expected_actions:
            self.assertRegex(
                workflow,
                rf"(?m)uses:\s+{re.escape(action)}@[0-9a-f]{{40}}(?:\s+#.*)?$",
            )

        uses_revisions = re.findall(r"uses:\s+[^@\s]+@([^\s#]+)", workflow)
        self.assertTrue(uses_revisions)
        self.assertTrue(
            all(re.fullmatch(r"[0-9a-f]{40}", item) for item in uses_revisions)
        )

        required_fragments = {
            "permissions:\n  contents: read",
            'python-version: "3.14"',
            "homeassistant==2026.8.3",
            "ruff check .",
            "ruff format --check .",
            "python -m unittest discover -v",
            "node --test tests/chart-scales.test.mjs",
            "bandit -q -r custom_components/my_wallet",
            "json.loads",
            "yaml.safe_load",
            "python -m compileall -q custom_components tests",
            "import custom_components.my_wallet.config_flow",
            "import custom_components.my_wallet.coordinator",
            "import custom_components.my_wallet.sensor",
            "category: integration",
        }
        for fragment in required_fragments:
            self.assertIn(fragment, workflow)

    def test_release_workflow_is_tag_driven_and_pinned(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text()
        self.assertRegex(
            workflow,
            r"uses:\s+actions/checkout@[0-9a-f]{40}(?:\s+#.*)?",
        )
        for fragment in (
            'tags: ["v*"]',
            "contents: write",
            "CHANGELOG.md",
            "gh release create",
            "sha256",
        ):
            self.assertIn(fragment, workflow)

    def test_english_sources_are_identical(self) -> None:
        folder = ROOT / "custom_components" / "my_wallet"
        self.assertEqual(
            json.loads((folder / "strings.json").read_text()),
            json.loads((folder / "translations" / "en.json").read_text()),
        )


if __name__ == "__main__":
    unittest.main()
