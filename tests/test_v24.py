from __future__ import annotations

import io
import json
import pathlib
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from repo_context import __version__
from repo_context.capabilities import CORE_CAPABILITIES, NATIVE_CAPABILITIES
from repo_context.claim_verification import claim_aware_verification_recall, derive_verification_requirements
from repo_context.cli import main
from repo_context.scanner import build_index
from repo_context.schema_registry import list_schemas, validate_contract


def make_ui_repo(root: pathlib.Path) -> None:
    (root / "SettingsPanel.tsx").write_text(
        """import { getModalMotion } from './motionTokens';
import { useTranslation } from 'react-i18next';

export function SettingsPanel() {
  const { t } = useTranslation();
  return <div className=\"fixed bottom-0 md:inset-0 md:m-auto md:max-w-2xl\">
    <button role=\"tab\" aria-selected=\"true\">{t('profile')}</button>
    <button role=\"tab\">安全性</button>
  </div>;
}
""",
        encoding="utf-8",
    )
    (root / "motionTokens.ts").write_text(
        "export function getModalMotion(reduced = false) { return reduced ? {opacity: 1} : {y: 0}; }\n",
        encoding="utf-8",
    )
    (root / "other.tsx").write_text("export const unrelated = '其他中文';\n", encoding="utf-8")
    (root / "store.ts").write_text(
        "import { persist } from 'zustand/middleware';\nexport const store = persist(() => ({ isDarkMode: false }), { name: 'app-store' });\n",
        encoding="utf-8",
    )


class ClaimRequirementTests(unittest.TestCase):
    def test_version_and_schema_count(self):
        self.assertEqual(__version__, "2.4.0")
        self.assertEqual(len(list_schemas()), 31)

    def test_responsive_requirement_is_derived(self):
        plan = derive_verification_requirements({"text": "Settings is a bottom sheet on desktop", "path": "SettingsPanel.tsx"})
        kinds = {x["kind"] for x in plan["requirements"]}
        self.assertIn("responsive-variants", kinds)
        self.assertFalse(plan["semantic_truth_claimed"])
        self.assertEqual(plan["model_calls_added"], 0)

    def test_usage_target_prefers_called_symbol_not_file_anchor(self):
        plan = derive_verification_requirements({
            "text": "`SettingsPanel.tsx` uses getModalMotion for desktop dialog motion",
            "path": "SettingsPanel.tsx",
        })
        usage = [x for x in plan["requirements"] if x["kind"] == "runtime-usage"]
        self.assertEqual(len(usage), 1)
        self.assertIn("getModalMotion", usage[0]["search_pattern"])
        self.assertNotIn("SettingsPanel\\s", usage[0]["search_pattern"])


class ClaimAwareRecallTrapTests(unittest.TestCase):
    def test_responsive_partial_context_trap_recalls_breakpoint_counter_context(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); make_ui_repo(root)
            result = claim_aware_verification_recall(
                build_index(root),
                {"text": "SettingsPanel is a bottom sheet on desktop", "path": "SettingsPanel.tsx"},
                budget=700, persist=False,
            )
            self.assertEqual(result["metrics"]["model_calls_added"], 0)
            self.assertGreaterEqual(result["verification"]["counter_context_signals"], 1)
            joined = "\n".join(str(x.get("content") or "") for x in result["model_payload"]["evidence"])
            self.assertIn("md:inset-0", joined)
            self.assertFalse(result["verification"]["semantic_truth_claimed"])
            self.assertTrue(validate_contract("claim-verification-recall", result)["valid"])

    def test_import_is_not_treated_as_runtime_usage(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); make_ui_repo(root)
            result = claim_aware_verification_recall(
                build_index(root),
                {"text": "`SettingsPanel.tsx` uses getModalMotion", "path": "SettingsPanel.tsx"},
                budget=700, persist=False,
            )
            usage = next(x for x in result["model_payload"]["observations"] if x["kind"] == "runtime-usage")
            self.assertEqual(usage["status"], "challenge-signal")
            self.assertEqual(usage["match_count"], 0)
            self.assertEqual(result["verification"]["status"], "challenged")

    def test_localization_check_is_scoped_to_claimed_component(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); make_ui_repo(root)
            result = claim_aware_verification_recall(
                build_index(root),
                {"text": "SettingsPanel is fully localized", "path": "SettingsPanel.tsx"},
                budget=700, persist=False,
            )
            hardcoded = next(x for x in result["model_payload"]["observations"] if x["requirement_id"] == "hardcoded-visible-copy")
            self.assertEqual(hardcoded["status"], "challenge-signal")
            self.assertEqual(hardcoded["paths"], ["SettingsPanel.tsx"])
            search = next(x for x in result["sidecar"]["searches"] if x["requirement_id"] == "hardcoded-visible-copy")
            self.assertEqual(search["scope_paths"], ["SettingsPanel.tsx"])

    def test_no_hardcoded_copy_does_not_invent_challenge(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "Settings.tsx").write_text(
                "import { useTranslation } from 'react-i18next';\nexport function Settings(){ const {t}=useTranslation(); return <div>{t('security')}</div>; }\n",
                encoding="utf-8",
            )
            result = claim_aware_verification_recall(
                build_index(root), {"text": "Settings is fully localized", "path": "Settings.tsx"},
                budget=500, persist=False,
            )
            self.assertEqual(result["verification"]["challenge_signals"], 0)
            self.assertGreaterEqual(result["verification"]["support_signals"], 1)
            self.assertEqual(result["verification"]["status"], "provisionally-supported")

    def test_persistence_requirement_finds_code_contract(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); make_ui_repo(root)
            result = claim_aware_verification_recall(
                build_index(root), {"text": "dark mode is persisted after reload", "path": "store.ts"},
                budget=500, persist=False,
            )
            obs = next(x for x in result["model_payload"]["observations"] if x["kind"] == "persistence")
            self.assertGreater(obs["match_count"], 0)
            self.assertEqual(result["metrics"]["model_calls_added"], 0)

    def test_accessibility_requirement_collects_keyboard_semantics(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); make_ui_repo(root)
            result = claim_aware_verification_recall(
                build_index(root), {"text": "Settings tabs have keyboard accessibility", "path": "SettingsPanel.tsx"},
                budget=500, persist=False,
            )
            obs = next(x for x in result["model_payload"]["observations"] if x["kind"] == "accessibility")
            self.assertGreater(obs["match_count"], 0)
            # Presence of ARIA is evidence context, not proof of complete keyboard behavior.
            self.assertFalse(result["verification"]["semantic_truth_claimed"])

    def test_aggregate_model_visible_budget_is_hard_bounded(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); make_ui_repo(root)
            result = claim_aware_verification_recall(
                build_index(root),
                {"text": "`SettingsPanel.tsx` uses getModalMotion for desktop dialog motion and is fully localized with keyboard accessibility", "path": "SettingsPanel.tsx"},
                budget=220, top_k=6, persist=False,
            )
            self.assertLessEqual(result["metrics"]["model_visible_tokens"], 220)
            self.assertEqual(result["metrics"]["model_calls_added"], 0)


    def test_bottom_sheet_without_breakpoint_does_not_fake_counter_context(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "Sheet.tsx").write_text(
                "export function Sheet(){ return <div className=\"fixed bottom-0\">Sheet</div>; }\n",
                encoding="utf-8",
            )
            result = claim_aware_verification_recall(
                build_index(root), {"text": "Sheet is a bottom sheet on desktop", "path": "Sheet.tsx"},
                budget=400, persist=False,
            )
            self.assertEqual(result["verification"]["counter_context_signals"], 0)
            variants = next(x for x in result["model_payload"]["observations"] if x["requirement_id"] == "responsive-variants")
            self.assertEqual(variants["status"], "checked-no-match")

    def test_missing_scoped_path_does_not_fall_back_to_whole_repository(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); make_ui_repo(root)
            result = claim_aware_verification_recall(
                build_index(root), {"text": "MissingPanel is fully localized", "path": "MissingPanel.tsx"},
                budget=400, persist=False,
            )
            self.assertEqual(result["verification"]["requirements_completed"], 0)
            self.assertFalse(result["context_status"]["sufficient"])
            self.assertTrue(result["context_status"]["escalation_recommended"])
            for search in result["sidecar"]["searches"]:
                self.assertEqual(search.get("reason"), "scope-unavailable")

    def test_generic_claim_stays_inconclusive_without_truth_guess(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); make_ui_repo(root)
            result = claim_aware_verification_recall(
                build_index(root), "SettingsPanel architecture is elegant", budget=400, persist=False,
            )
            self.assertEqual(result["verification"]["status"], "inconclusive")
            self.assertFalse(result["verification"]["semantic_truth_claimed"])


class ClaimAwareRecallCliTests(unittest.TestCase):
    def test_claim_recall_cli(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); make_ui_repo(root)
            out = io.StringIO(); err = io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                rc = main([
                    "claim-recall", "Settings is fully localized", "--repo", td,
                    "--path", "SettingsPanel.tsx", "--budget", "500", "--pretty",
                ])
            self.assertEqual(rc, 0, err.getvalue())
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["schema"], "repo-context-claim-verification-recall/v1")
            self.assertEqual(payload["metrics"]["model_calls_added"], 0)

    def test_capability_is_core(self):
        self.assertIn("context.claim-verification-recall", NATIVE_CAPABILITIES)
        self.assertIn("context.claim-verification-recall", CORE_CAPABILITIES)


if __name__ == "__main__":
    unittest.main()
