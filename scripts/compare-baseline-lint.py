#!/usr/bin/env python3
"""Admit only Clippy diagnostics from unchanged authenticated upstream tokens."""
from collections import Counter
import difflib
import io
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
BASE = '243281163e4a39303322385d5f9537736277026e'
# Reviewed lexical subset, not a general Rust parser. Unsupported nested comments and
# non-ASCII tokens outside protected comments/literals fail closed below.
TOKENS = re.compile(rb'//[^\n]*|/\*[\s\S]*?\*/|b?r(?P<h>\#{0,255})"[\s\S]*?"(?P=h)|b?"(?:\\.|[^"\\])*"|b?\'(?:\\.|[^\'\\])\'|[A-Za-z_][A-Za-z_0-9]*|[^\s]')


def require(condition, message):
    """Fail closed without relying on Python assertions."""
    if not condition:
        raise ValueError(message)


def diagnostics(output):
    """Read all warning/error compiler messages and reject malformed JSON records."""
    records = [json.loads(line) for line in output.splitlines() if line.strip()]
    return [item['message'] for item in records
            if item.get('reason') == 'compiler-message' and item['message']['level'] in {'warning', 'error'}]


@lru_cache(maxsize=32)
def token_origin(original, current):
    """Cache only immutable byte-pair mappings, never path-dependent results."""
    before = list(TOKENS.finditer(original))
    after = list(TOKENS.finditer(current))
    for token in before + after:
        value = token.group()
        require(not (value.startswith(b'/*') and b'/*' in value[2:]), 'unsupported nested block comment')
        require(value[0] < 128, 'unsupported non-ASCII token outside a protected comment/literal')
    mapping = {}
    for tag, i, j, k, l in difflib.SequenceMatcher(None, [x.group() for x in before], [x.group() for x in after], autojunk=False).get_opcodes():
        if tag == 'equal':
            mapping.update({new: old for old, new in zip(range(i, j), range(k, l))})
    return after, mapping


def signature(message, root, originals):
    """Bind each primary span to consecutive unchanged tokens in its Git baseline blob."""
    require(message.get('code') is not None, 'diagnostic has no lint code')
    locations = []
    for span in message['spans']:
        if not span['is_primary']:
            continue
        path = Path(span['file_name'])
        if not path.is_absolute():
            path = root / path
        name = path.resolve().relative_to(root.resolve()).as_posix()
        require(name in originals, f'diagnostic in authored/unrecognized source: {name}')
        after, mapping = token_origin(originals[name], path.read_bytes())
        indices = [i for i, token in enumerate(after) if token.start() < span['byte_end'] and token.end() > span['byte_start']]
        require(bool(indices), 'primary diagnostic span has no source tokens')
        require(all(i in mapping for i in indices), f'diagnostic touches authored tokens: {name}')
        origin = [mapping[i] for i in indices]
        require(origin == list(range(origin[0], origin[-1] + 1)), 'diagnostic origin is not consecutive')
        locations.append((name, origin[0], origin[-1]))
    require(bool(locations), 'diagnostic has no primary source location')
    return (message['code']['code'], message['message'], tuple(locations))


def compare(current, baseline, current_root, baseline_root, originals):
    """Reject every new diagnostic, changed origin and compiler error."""
    require(all(item['level'] == 'warning' for item in baseline), 'baseline has a non-lint/compiler error')
    require(all(item['level'] == 'warning' for item in current), 'current has a non-lint/compiler error')
    admitted = Counter(signature(item, baseline_root, originals) for item in baseline)
    observed = Counter(signature(item, current_root, originals) for item in current)
    require(not observed - admitted, f'new or changed diagnostics: {list((observed - admitted).elements())}')
    return {'baseline_diagnostics': sum(admitted.values()), 'current_diagnostics': sum(observed.values()),
            'new_diagnostics': 0, 'removed_diagnostics': sum((admitted - observed).values()),
            'admitted_diagnostics': [repr(item) for item in observed.elements()]}


def validate_strict(result, ordinary, root, originals):
    """Retain strict failures, accepting only the exact ordinary lint promotions."""
    raw = diagnostics(result.stdout)
    normal = Counter(signature(item, root, originals) for item in ordinary)
    strict = Counter(signature(item, root, originals) for item in raw)
    require(strict == normal, 'strict run differs from ordinary diagnostic inventory')
    expected = 101 if raw else 0
    require(result.returncode == expected, 'unexpected strict exit status')
    require(all(item['level'] == 'error' for item in raw), 'unexpected strict diagnostic severity')
    require(not re.search(r'internal compiler error|panicked|fatal error|signal:|no space|could not execute', result.stderr, re.I), 'strict run has an operational/compiler failure')
    for line in result.stderr.splitlines():
        if line.startswith('error:'):
            require(line.startswith('error: could not compile `libsql`') and 'previous error' in line, 'unrecognized strict error outside diagnostics')


def run():
    """Execute the same library/test targets, compiler, features and provider on both sources."""
    compiler = subprocess.check_output(['rustc', '-Vv'], text=True)
    output = ROOT / 'target/lint-comparison' / uuid.uuid4().hex
    output.mkdir(parents=True)
    archive = subprocess.check_output(['git', 'archive', BASE], cwd=ROOT)
    with tempfile.TemporaryDirectory(prefix='gossil-libsql-lint-') as temp:
        pristine = Path(temp).resolve()
        with tarfile.open(fileobj=io.BytesIO(archive)) as source:
            source.extractall(pristine, filter='data')
        originals = {name: (pristine / name).read_bytes() for name in json.loads((pristine / 'SOURCE-PROVENANCE.json').read_text())['baseline_files']}
        # Only the explicit test harness and identical provider-source override are grafted.
        for name in ['Cargo.toml', 'Cargo.lock', 'tests/row_text_regression.rs']:
            (pristine / name).write_bytes((ROOT / name).read_bytes())
        env = dict(os.environ, CARGO_TARGET_DIR=os.environ.get('CARGO_TARGET_DIR', str(ROOT / 'target')))
        ffi = str(Path(os.environ['GOSSIL_LIBSQL_FFI_PATH']).resolve())
        ordinary = {}
        strict = {}
        for label, root in [('baseline', pristine), ('current', ROOT)]:
            common = ['--manifest-path', str(root / 'Cargo.toml'), '--config', f'patch.crates-io.libsql-ffi.path="{ffi}"', '--locked', '--no-default-features', '--features', 'core', '--lib', '--test', 'row_text_regression', '--message-format=json']
            for mode in ['ordinary', 'strict']:
                command = ['cargo', 'clippy', *common, *(['--', '-D', 'warnings'] if mode == 'strict' else [])]
                result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)
                (output / f'{label}-{mode}.stdout.jsonl').write_text(result.stdout)
                (output / f'{label}-{mode}.stderr.txt').write_text(result.stderr)
                (output / f'{label}-{mode}.execution.json').write_text(json.dumps({'argv': command, 'returncode': result.returncode}, indent=2) + '\n')
                print(f'{label} {mode}: exit {result.returncode}; raw evidence {output}')
                if mode == 'ordinary':
                    require(result.returncode == 0, f'{label} ordinary compilation failed')
                    ordinary[label] = diagnostics(result.stdout)
                else:
                    strict[label] = result
        report = compare(ordinary['current'], ordinary['baseline'], ROOT, pristine, originals)
        validate_strict(strict['baseline'], ordinary['baseline'], pristine, originals)
        validate_strict(strict['current'], ordinary['current'], ROOT, originals)
        report.update({'status': 'zero new diagnostics; inherited strict failures remain visible', 'compiler': compiler,
                       'baseline': BASE, 'ffi_path': ffi, 'typecheck': 'required by Just dependency before this comparison',
                       'test_harness_graft': ['Cargo.toml explicit row target', 'Cargo.lock identical FFI path override', 'tests/row_text_regression.rs']})
        (output / 'comparison.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    run()
