"""Failure controls for the immutable baseline and authored coverage contract."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("source_verifier", ROOT / "scripts/verify-source.py")
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


class SourceVerifierTests(unittest.TestCase):
    """Preservation and coverage checks reject incomplete evidence."""

    def setUp(self):
        """Copy this small owned repository without compiler artifacts."""
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "source"
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns("target", "__pycache__", ".qualification"))
        VERIFIER.ROOT = self.root

    def tearDown(self):
        """Restore the verifier root and remove only test-owned files."""
        VERIFIER.ROOT = ROOT
        self.temp.cleanup()

    def report(self, mode="complete"):
        """Write synthetic coverage solely to test acceptance and rejection logic."""
        contract = json.loads((self.root / "evidence/coverage-contract.json").read_text())
        records = []
        for name, row in contract["files"].items():
            records.append(f"SF:{self.root / name}")
            for number, item in row["added_lines"].items():
                if item["kind"] == "executable":
                    if mode == "missing":
                        mode = "complete"
                        continue
                    count = 0 if mode == "zero" else 1
                    records.append(f"DA:{number},{count}")
            records.append("end_of_record")
        path = self.root / "synthetic.lcov"
        path.write_text("\n".join(records) + "\n")
        return path

    def test_complete_source_and_coverage(self):
        """A complete inventory and positive executable counts pass."""
        VERIFIER.verify(self.report())

    def test_baseline_drift(self):
        """An unrelated engine-facing source change fails preservation."""
        (self.root / "src/value.rs").write_text("")
        with self.assertRaises(ValueError):
            VERIFIER.verify()

    def test_upstream_readme_prefix(self):
        """A maintenance appendix cannot excuse editing original upstream prose."""
        (self.root / "README.md").write_text("replacement")
        with self.assertRaisesRegex(ValueError, "README prefix"):
            VERIFIER.verify()

    def test_extra_source(self):
        """An untracked source file cannot escape source classification."""
        (self.root / "src/extra.rs").write_text("")
        with self.assertRaises(ValueError):
            VERIFIER.verify()

    def test_wrong_archive(self):
        """A different archive fails before extraction or compilation."""
        archive = self.root / "wrong.crate"
        archive.write_bytes(b"wrong")
        with self.assertRaises(ValueError):
            VERIFIER.verify(archive=archive)

    def test_unrelated_lock_change(self):
        """Dependency changes beyond the provider source override fail."""
        with (self.root / "Cargo.lock").open("a") as out:
            out.write("\n")
        with self.assertRaisesRegex(ValueError, "only the existing ffi"):
            VERIFIER.verify()

    def test_sibling_provider_path(self):
        """The selected Cargo directory must be the directory the checker verifies."""
        provider = self.root / "qualification/vendor/other-ffi"
        provider.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "Cargo provider path differs"):
            VERIFIER.verify(ffi_root=provider)

    def test_wrong_provider_manifest(self):
        """A different provider is rejected before any external checker runs."""
        provider = self.root / "qualification/vendor/libsql-ffi"
        provider.mkdir(parents=True)
        (provider.parent / "libsql-ffi.manifest.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "provider manifest identity"):
            VERIFIER.verify(ffi_root=provider)

    def test_missing_coverage_record(self):
        """Omitting one executable line fails even when both SF records exist."""
        with self.assertRaisesRegex(ValueError, "line absent"):
            VERIFIER.verify(self.report("missing"))

    def test_zero_coverage_count(self):
        """A represented but unexecuted authored line fails."""
        with self.assertRaisesRegex(ValueError, "uncovered executable"):
            VERIFIER.verify(self.report("zero"))

    def test_source_hash_drift(self):
        """Changing a corrected file without updating the contract fails."""
        with (self.root / "src/local/rows.rs").open("a") as out:
            out.write("\n")
        with self.assertRaises(ValueError):
            VERIFIER.verify()

    def test_missing_line_classification(self):
        """Every added source line must remain classified."""
        path = self.root / "evidence/coverage-contract.json"
        contract = json.loads(path.read_text())
        lines = contract["files"]["src/local/rows.rs"]["added_lines"]
        del lines[next(iter(lines))]
        path.write_text(json.dumps(contract))
        with self.assertRaises(ValueError):
            VERIFIER.verify()


if __name__ == "__main__":
    unittest.main()
