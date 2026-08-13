from __future__ import annotations

import json
import pathlib
import unittest

from repo_context import __version__
from repo_context.capabilities import NATIVE_CAPABILITIES, native_capability_manifest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ManifestConsistencyTests(unittest.TestCase):
    def test_capabilities_json_is_generated_from_runtime_source_of_truth(self):
        committed = json.loads((ROOT / "capabilities.json").read_text(encoding="utf-8"))
        self.assertEqual(committed, native_capability_manifest(__version__))
        self.assertEqual(set(committed["provides"]), NATIVE_CAPABILITIES)

    def test_every_native_capability_has_exactly_one_product_classification(self):
        manifest = native_capability_manifest(__version__)
        notes = manifest["notes"]
        classified = set(notes["core"]) | set(notes["fallback"]) | set(notes["advisory"])
        self.assertEqual(classified, NATIVE_CAPABILITIES)
        self.assertFalse(set(notes["core"]) & set(notes["fallback"]))
        self.assertFalse(set(notes["core"]) & set(notes["advisory"]))
        self.assertFalse(set(notes["fallback"]) & set(notes["advisory"]))


if __name__ == "__main__":
    unittest.main()
