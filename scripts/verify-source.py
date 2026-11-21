#!/usr/bin/env python3
"""Authenticate the complete published baseline and the authored Row patch."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import re
import tarfile
ROOT = Path(__file__).resolve().parents[1]
BASELINE = '243281163e4a39303322385d5f9537736277026e'
ARCHIVE = 'd6bca1704194048f0f0bbc8a8e05ba85c0c67628b03bd59346dd2fdd946a1588'
UPSTREAM = 'd8bc862d20bedc72945a1da27c8b7045414c0261'
LICENSE = 'cecf589818a56c2da8a0a6cc82c8a215c9770988c033b6016c2b74bf79f38152'
CHANGED = {'src/local/rows.rs', 'src/local/impls.rs', 'src/local/statement.rs', 'src/statement.rs'}

def require(condition, message):
    """Reject failed evidence even when Python optimization is enabled."""
    if not condition:
        raise ValueError(str(message))


def git(*args):
    """Read the repository through Git's normal interface."""
    return subprocess.check_output(['git', *args], cwd=ROOT)

def verify(coverage=None, archive=None, ffi_root=None):
    """Verify every baseline file and optional production coverage presence."""
    if ffi_root:
        provider = Path(ffi_root).resolve()
        manifest = provider.parent / 'libsql-ffi.manifest.json'
        checker = provider.parent.parent / 'scripts/verify-libsql-vendor.py'
        require(provider == (checker.resolve().parents[1] / 'vendor/libsql-ffi').resolve(), 'Cargo provider path differs from the checker selected provider')
        require(hashlib.sha256(manifest.read_bytes()).hexdigest() == '86134dea69ef341167417309f74b0473352932046219f9de1609ff60413a7a65', 'provider manifest identity differs')
        require(hashlib.sha256(checker.read_bytes()).hexdigest() == 'ba97fbf31a5a52339b13fe82854b3eedd35ed0e090c124daa4aab307ed6487a6', 'provider checker identity differs')
        subprocess.run(['python3', str(checker)], check=True)
        print(f'Existing Gossil provider: {provider}; manifest SHA25686134dea69ef341167417309f74b0473352932046219f9de1609ff60413a7a65')
    provenance = json.loads(git('show', f'{BASELINE}:SOURCE-PROVENANCE.json'))
    require(provenance['archive_sha256'] == ARCHIVE, 'source identity disagreement')
    require(provenance['upstream_commit'] == UPSTREAM, 'source identity disagreement')
    require(provenance['license_sha256'] == LICENSE, 'source identity disagreement')
    require((ROOT / 'SOURCE-PROVENANCE.json').read_bytes() == git('show', f'{BASELINE}:SOURCE-PROVENANCE.json'), 'source identity disagreement')
    original_manifest = git('show', f'{BASELINE}:Cargo.toml').decode()
    test_entry = '[[test]]\nname = "row_text_regression"\npath = "tests/row_text_regression.rs"\nrequired-features = ["core"]\n\n'
    require((ROOT / 'Cargo.toml').read_text() == original_manifest.replace('[[test]]\nname = "encryption"', test_entry + '[[test]]\nname = "encryption"'), 'source identity disagreement')
    if archive:
        archive = Path(archive)
        require(hashlib.sha256(archive.read_bytes()).hexdigest() == ARCHIVE, 'source identity disagreement')
        with tarfile.open(archive) as source:
            files = {entry.name.split('/', 1)[1]: hashlib.sha256(source.extractfile(entry).read()).hexdigest() for entry in source.getmembers() if entry.isfile()}
        expected = {name: digest for name, digest in provenance['baseline_files'].items() if name != 'LICENSE.md'}
        require(files == expected, 'published archive inventory differs')
    paths = set(git('ls-tree', '-r', '--name-only', BASELINE).decode().splitlines())
    require(paths == set(provenance['baseline_files']) | {'SOURCE-PROVENANCE.json'}, 'source identity disagreement')
    for name, expected in provenance['baseline_files'].items():
        require(hashlib.sha256(git('show', f'{BASELINE}:{name}')).hexdigest() == expected, name)
        if name not in CHANGED | {'Cargo.toml', 'Cargo.lock', 'README.md'}:
            require(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name)
    original_readme = git('show', f'{BASELINE}:README.md')
    require((ROOT / 'README.md').read_bytes().startswith(original_readme + b'\n## Gossil maintenance contract\n'), 'upstream README prefix must remain unchanged')
    original_lock = git('show', f'{BASELINE}:Cargo.lock').decode()
    start = original_lock.index('[[package]]\nname = "libsql-ffi"\n')
    end = original_lock.index('\n[[package]]', start)
    entry = '\n'.join(line for line in original_lock[start:end].split('\n') if not line.startswith(('source =', 'checksum =')))
    require((ROOT / 'Cargo.lock').read_text() == original_lock[:start] + entry + original_lock[end:], 'only the existing ffi source override may change the lock')
    source_changes = set(git('diff', '--name-only', BASELINE, '--', 'src').decode().splitlines())
    require(source_changes == CHANGED, source_changes)
    for path in (ROOT / 'src').rglob('*'):
        require(not path.is_symlink(), path)
        if path.is_file():
            require(path.relative_to(ROOT).as_posix() in paths, path)
    contract = json.loads((ROOT / 'evidence/coverage-contract.json').read_text())
    require(contract['baseline'] == BASELINE, 'source identity disagreement')
    require(set(contract['files']) == CHANGED, 'source identity disagreement')
    for name, row in contract['files'].items():
        data = (ROOT / name).read_bytes()
        require(hashlib.sha256(data).hexdigest() == row['sha256'], name)
        actual = {}
        line_number = 0
        for line in git('diff', '--unified=0', BASELINE, '--', name).decode().splitlines():
            if line.startswith('@@'):
                line_number = int(re.search('\\+(\\d+)', line).group(1))
            elif line.startswith(('+++', '---')):
                continue
            elif line.startswith('+'):
                actual[str(line_number)] = line[1:]
                line_number += 1
            elif line.startswith(' '):
                line_number += 1
        require(actual == {line: item['source'] for line, item in row['added_lines'].items()}, name)
        for item in row['added_lines'].values():
            require(item['kind'] in {'executable', 'test', 'blank', 'comment', 'syntax', 'declaration'}, 'source identity disagreement')
    if coverage:
        reported = {}
        current = None
        for line in Path(coverage).read_text().splitlines():
            if line.startswith('SF:'):
                path = Path(line[3:])
                if not path.is_absolute():
                    path = ROOT / path
                try:
                    current = path.resolve().relative_to(ROOT.resolve()).as_posix()
                    reported.setdefault(current, {})
                except ValueError:
                    current = None
            elif current is not None and line.startswith('DA:'):
                number, count = line[3:].split(',')[:2]
                previous = reported[current].get(number, 0)
                reported[current][number] = previous + int(count)
        for name, row in contract['files'].items():
            require(name in reported, f'changed source absent from coverage: {name}')
            for number, item in row['added_lines'].items():
                if item['kind'] == 'executable':
                    require(number in reported[name], f'executable line absent from coverage: {name}:{number}')
                    require(reported[name][number] > 0, f'uncovered executable line: {name}:{number}')
    print(f'Verified all {len(paths)} baseline files and the bounded production correction.')
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--coverage', help='also reject corrected files absent from this LCOV report')
    parser.add_argument('--archive', help='authenticate and compare the complete published .crate payload')
    parser.add_argument('--ffi-root', help='authenticate and verify this existing Gossil provider')
    args = parser.parse_args()
    verify(args.coverage, args.archive, args.ffi_root)
