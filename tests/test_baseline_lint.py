"""Negative controls for the explicit immutable-upstream diagnostic contract."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('baseline_lint', ROOT / 'scripts/compare-baseline-lint.py')
LINT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LINT)


class BaselineLintTests(unittest.TestCase):
    """New diagnostics, source drift and fatal failures are never admitted."""

    def setUp(self):
        """Create distinct baseline and candidate trees for source-origin controls."""
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name) / 'base'
        self.current = Path(self.temp.name) / 'current'
        self.source = b'fn old() { let value = "a b"; }\n'
        for root in [self.base, self.current]:
            (root / 'src').mkdir(parents=True)
            (root / 'src/example.rs').write_bytes(self.source)
        self.originals = {'src/example.rs': self.source}

    def tearDown(self):
        """Remove only these test-owned source files."""
        self.temp.cleanup()

    def diagnostic(self, root, token=b'value', message='inherited', level='warning'):
        """Construct one diagnostic with real byte offsets in the selected source."""
        source = (root / 'src/example.rs').read_bytes()
        start = source.index(token)
        return {'level': level, 'code': {'code': 'clippy::example'}, 'message': message,
                'spans': [{'file_name': 'src/example.rs', 'is_primary': True,
                           'byte_start': start, 'byte_end': start + len(token)}]}

    def compare(self, current=None, baseline=None):
        """Compare the selected synthetic diagnostics through the real predicate."""
        return LINT.compare(current if current is not None else [self.diagnostic(self.current)],
                            baseline if baseline is not None else [self.diagnostic(self.base)],
                            self.current, self.base, self.originals)

    def test_unchanged_origin(self):
        """An unchanged origin and exact code/message are admitted."""
        self.assertEqual(self.compare()['new_diagnostics'], 0)

    def test_formatting_preserves_origin(self):
        """Outer Rust whitespace changes do not invent a new source origin."""
        (self.current / 'src/example.rs').write_bytes(b'fn old() {\n    let value = "a b";\n}\n')
        self.assertEqual(self.compare()['new_diagnostics'], 0)

    def test_added_diagnostic(self):
        """A changed message is rejected even at a known baseline location."""
        with self.assertRaisesRegex(ValueError, 'new or changed'):
            self.compare([self.diagnostic(self.current, message='new warning')])

    def test_missing_baseline(self):
        """A missing baseline diagnostic cannot excuse a current warning."""
        with self.assertRaisesRegex(ValueError, 'new or changed'):
            self.compare(baseline=[])

    def test_authored_token(self):
        """A warning on a changed source token fails source-origin admission."""
        (self.current / 'src/example.rs').write_bytes(self.source.replace(b'value', b'other'))
        with self.assertRaisesRegex(ValueError, 'authored tokens'):
            self.compare([self.diagnostic(self.current, token=b'other')])

    def test_literal_whitespace_is_semantic(self):
        """Whitespace inside a literal remains part of its immutable token."""
        (self.current / 'src/example.rs').write_bytes(self.source.replace(b'a b', b'ab'))
        with self.assertRaisesRegex(ValueError, 'authored tokens'):
            self.compare([self.diagnostic(self.current, token=b'"ab"')], [self.diagnostic(self.base, token=b'"a b"')])

    def test_nested_comment_fails_closed(self):
        """Unsupported nested comments cannot silently erase meaningful bytes."""
        source = b'/* outer /* nested */ tail */ fn old() { let value = 1; }'
        self.originals['src/example.rs'] = source
        for root in [self.base, self.current]:
            (root / 'src/example.rs').write_bytes(source)
        with self.assertRaisesRegex(ValueError, 'unsupported nested'):
            self.compare()

    def test_unicode_identifier_fails_closed(self):
        """Unsupported identifier lexing cannot silently weaken source matching."""
        source = 'fn café() { let value = 1; }'.encode()
        self.originals['src/example.rs'] = source
        for root in [self.base, self.current]:
            (root / 'src/example.rs').write_bytes(source)
        with self.assertRaisesRegex(ValueError, 'unsupported non-ASCII'):
            self.compare()

    def test_compiler_error(self):
        """An ordinary compiler error fails even with a baseline warning twin."""
        with self.assertRaisesRegex(ValueError, 'compiler error'):
            self.compare([self.diagnostic(self.current, level='error')])

    def test_missing_lint_code(self):
        """An uncoded/fatal diagnostic cannot be admitted as an inherited lint."""
        message = self.diagnostic(self.current)
        message['code'] = None
        with self.assertRaisesRegex(ValueError, 'no lint code'):
            self.compare([message])

    def strict(self, stderr='', returncode=101):
        """Create the raw strict counterpart of an ordinary warning."""
        message = self.diagnostic(self.current, level='error')
        output = json.dumps({'reason': 'compiler-message', 'message': message}) + '\n'
        return SimpleNamespace(stdout=output, stderr=stderr, returncode=returncode)

    def test_exact_raw_strict_failure_remains_visible(self):
        """Only the recorded promotion of the ordinary warning is recognized."""
        LINT.validate_strict(self.strict(), [self.diagnostic(self.current)], self.current, self.originals)

    def test_operational_failure(self):
        """A fatal raw failure is rejected despite otherwise matching diagnostics."""
        with self.assertRaisesRegex(ValueError, 'operational'):
            LINT.validate_strict(self.strict('fatal error: tool failed'), [self.diagnostic(self.current)], self.current, self.originals)

    def test_unexpected_exit_status(self):
        """Non-lint process exit codes never turn into admission success."""
        with self.assertRaisesRegex(ValueError, 'exit status'):
            LINT.validate_strict(self.strict(returncode=1), [self.diagnostic(self.current)], self.current, self.originals)


if __name__ == '__main__':
    unittest.main()
