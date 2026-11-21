"""Failure controls for independent test-binary coverage inputs."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('fresh_coverage', ROOT / 'scripts/fresh-coverage.py')
COVERAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COVERAGE)


class FreshCoverageTests(unittest.TestCase):
    """A target cannot borrow another target's identity or profile evidence."""

    def setUp(self):
        """Create an isolated target containing two distinguishable test objects."""
        self.temp = tempfile.TemporaryDirectory()
        self.target = Path(self.temp.name).resolve()
        self.binary = self.target / 'unit'
        self.binary.write_bytes(b'unit')
        self.label = 'unittests src/lib.rs'
        self.line = f'Running {self.label} ({self.binary})\n'

    def tearDown(self):
        """Remove only fixture-owned files."""
        self.temp.cleanup()

    def test_one_binary(self):
        """Exactly one existing selected binary is accepted."""
        self.assertEqual(COVERAGE.executed_binary(self.line, self.label, self.target), self.binary)

    def test_duplicate_binary_identity(self):
        """Two matching lines cannot impersonate two different target executions."""
        with self.assertRaises(ValueError):
            COVERAGE.executed_binary(self.line * 2, self.label, self.target)

    def test_wrong_target(self):
        """A unit record does not establish regression-target execution."""
        with self.assertRaises(ValueError):
            COVERAGE.executed_binary(self.line, 'tests/row_text_regression.rs', self.target)

    def test_profiles_are_per_target(self):
        """Another target's fresh profile cannot fill this target's missing inputs."""
        (self.target / 'other-1.profraw').write_bytes(b'fixture')
        with self.assertRaises(ValueError):
            COVERAGE.fresh_profiles(self.target, 'unit')

    def test_exact_profile_prefix(self):
        """Only the requested nonce contributes profile inputs."""
        own = self.target / 'unit-1.profraw'
        own.write_bytes(b'fixture')
        (self.target / 'other-1.profraw').write_bytes(b'fixture')
        self.assertEqual(COVERAGE.fresh_profiles(self.target, 'unit'), [own])


if __name__ == '__main__':
    unittest.main()
