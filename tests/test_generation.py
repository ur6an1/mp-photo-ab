"""Generation contract tests; never call paid APIs."""
import base64
from contextlib import redirect_stdout, redirect_stderr
from datetime import date
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import generate
import providers
from thumbnail_preview import preview
from PIL import Image


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.reference = self.root / "product.png"
        Image.new("RGB", (100, 150), "red").save(self.reference)
        self.brief = {"current_image": str(self.reference), "reference_images": [str(self.reference)],
                      "category": "Техника", "marketplace": "Ozon"}
        (self.root / "brief.json").write_text(json.dumps(self.brief))
        (self.root / "hypotheses.json").write_text(json.dumps([
            {"id": "B", "variable": "background", "change": "Синий фон", "selected": True}]))
        self.arguments = ["--experiment", str(self.root)]
        self.raw = self.reference.read_bytes()

    def paid_arguments(self):
        return [*self.arguments, "--run", "--estimated-cost-usd", "1", "--budget-usd", "2",
                "--cost-source", "Official price incl inputs conservative estimate", "--cost-checked-on", date.today().isoformat()]

    def test_dry_run_does_not_construct_provider_or_write(self):
        with patch.object(generate, "get_provider") as provider, redirect_stdout(StringIO()) as output:
            self.assertEqual(generate.main(self.arguments), 0)
        provider.assert_not_called()
        self.assertIn("Синий фон", output.getvalue())
        self.assertFalse((self.root / "generation.json").exists())

    def test_budget_rejected_before_provider(self):
        with patch.object(generate, "get_provider") as provider, redirect_stderr(StringIO()):
            self.assertEqual(generate.main([*self.paid_arguments(), "--budget-usd", "0.1"]), 2)
        provider.assert_not_called()

    def test_paid_batch_is_not_repeated(self):
        provider = Mock()
        provider.edit.return_value = self.raw
        with patch.object(generate, "get_provider", return_value=provider), redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            self.assertEqual(generate.main(self.paid_arguments()), 0)
            self.assertEqual(generate.main(self.paid_arguments()), 2)
        self.assertEqual(provider.edit.call_count, 2)
        with Image.open(self.root / "images/control-normalized.jpg") as control:
            self.assertEqual(control.size, (900, 1200))
            self.assertTrue(control.info.get("icc_profile"))
        self.assertEqual(provider.edit.call_args.args[1][0], self.root / "images/control-normalized.jpg")
        with Image.open(self.root / "images/B-1.jpg") as result:
            self.assertEqual(result.size, (900, 1200))
            self.assertTrue(result.info.get("icc_profile"))

    def test_uncertain_failure_stops_without_retry_and_no_secret_echo(self):
        provider = Mock()
        provider.edit.side_effect = RuntimeError("SECRET_TOKEN")
        with patch.object(generate, "get_provider", return_value=provider), redirect_stdout(StringIO()), redirect_stderr(StringIO()) as output:
            self.assertEqual(generate.main(self.paid_arguments()), 3)
        self.assertEqual(provider.edit.call_count, 1)
        self.assertNotIn("SECRET_TOKEN", output.getvalue())
        journal = (self.root / "generation.json").read_text()
        self.assertNotIn("SECRET_TOKEN", journal)
        self.assertIn("ошибка", journal)

    def test_missing_reference_blocks_paid_call(self):
        self.brief["reference_images"] = []
        (self.root / "brief.json").write_text(json.dumps(self.brief))
        with patch.object(generate, "get_provider") as provider, redirect_stderr(StringIO()):
            self.assertEqual(generate.main(self.paid_arguments()), 2)
        provider.assert_not_called()

    def test_existing_output_blocks_paid_call(self):
        (self.root / "images").mkdir()
        (self.root / "images/B-1.jpg").write_bytes(self.raw)
        with patch.object(generate, "get_provider") as provider, redirect_stderr(StringIO()):
            self.assertEqual(generate.main(self.paid_arguments()), 2)
        provider.assert_not_called()

    def test_dangling_output_symlink_blocks_before_provider(self):
        (self.root / "images").mkdir()
        (self.root / "images/B-1.jpg").symlink_to(self.root / "missing.jpg")
        with patch.object(generate, "get_provider") as provider, redirect_stderr(StringIO()):
            self.assertEqual(generate.main(self.paid_arguments()), 2)
        provider.assert_not_called()
        self.assertFalse((self.root / "generation.json").exists())

    def test_provider_uses_reference_edit(self):
        client = Mock()
        client.images.edit.return_value = SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(self.raw).decode())])
        result = providers.OpenAIProvider(client=client).edit("prompt", [self.reference])
        self.assertEqual(result, self.raw)
        kwargs = client.images.edit.call_args.kwargs
        self.assertEqual(kwargs["input_fidelity"], "high")
        self.assertEqual(kwargs["quality"], "medium")
        self.assertEqual(kwargs["n"], 1)
        self.assertEqual(len(kwargs["image"]), 1)

    def test_path_traversal_hypothesis_rejected(self):
        with self.assertRaises(ValueError):
            generate.build_jobs(self.brief, [{"id": "../escape", "selected": True}], 2)

    def test_preview_geometry_and_no_overwrite(self):
        output = self.root / "preview.jpg"
        preview(self.reference, [self.reference], [self.reference], output)
        with Image.open(output) as result:
            self.assertEqual(result.size, (384, 560))
            self.assertTrue(result.info.get("icc_profile"))
        with self.assertRaises(FileExistsError):
            preview(self.reference, [self.reference], [], output)


if __name__ == "__main__":
    unittest.main()
