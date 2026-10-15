"""Check publication tooling with temporary metadata, never with a live account."""

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "configure_meest_repository", ROOT / "scripts/configure_repository.py"
)
configure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(configure)


class RepositoryTests(unittest.TestCase):
    def test_configure_owner_and_maintainer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "custom_components/meest").mkdir(parents=True)
            (root / ".github").mkdir()
            manifest = root / "custom_components/meest/manifest.json"
            manifest.write_text(
                json.dumps({"domain": "meest", "name": "Meest", "version": "0.1.0"})
            )
            with (
                patch.object(configure, "ROOT", root),
                patch.object(
                    sys,
                    "argv",
                    ["configure", "test-org/ha-meest", "--maintainer", "test-maintainer"],
                ),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                configure.main()
            result = json.loads(manifest.read_text())
            self.assertEqual(result["documentation"], "https://github.com/test-org/ha-meest")
            self.assertEqual(result["codeowners"], ["@test-maintainer"])
            self.assertEqual((root / ".github/CODEOWNERS").read_text(), "* @test-maintainer\n")
            self.assertEqual(result["version"], "0.1.0")

    def test_configure_rejects_placeholder_and_path(self):
        for value in ["OWNER/REPOSITORY", "../escape", "https://github.com/a/b"]:
            with (
                self.subTest(value=value),
                patch.object(sys, "argv", ["configure", value]),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                configure.main()

    def test_yaml_and_translations(self):
        for folder in [ROOT / ".github", ROOT / "examples"]:
            for path in folder.rglob("*"):
                if path.suffix in (".yaml", ".yml"):
                    self.assertIsInstance(
                        yaml.load(path.read_text(encoding="utf8"), Loader=yaml.BaseLoader), dict
                    )
        integration = ROOT / "custom_components/meest"
        for lang in ["en", "uk"]:
            strings = json.loads(
                (integration / "translations" / f"{lang}.json").read_text(encoding="utf8")
            )
            self.assertEqual(set(strings["entity"]["sensor"]), {"ready_for_pickup", "in_transit"})
            self.assertIn("reauth_confirm", strings["config"]["step"])
