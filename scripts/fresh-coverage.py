#!/usr/bin/env python3
"""Export only fresh per-target profiles without deleting cached profiles."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid


def executed_binary(stderr, label, target):
    """Require exactly the selected executed binary in the coverage target tree."""
    paths = []
    plain = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', stderr)
    for line in plain.splitlines():
        if f'Running {label} ' in line:
            match = re.search(r' \((.+)\)$', line)
            if match:
                paths.append(Path(match.group(1)).resolve())
    if len(paths) != 1 or not paths[0].is_file() or not paths[0].is_relative_to(target):
        raise ValueError(f'expected exactly one executed binary for {label}')
    return paths[0]


def fresh_profiles(target, prefix):
    """Refuse a successful target run that produced no profiles of its own."""
    paths = sorted(target.glob(f'{prefix}-*.profraw'))
    if not paths:
        raise ValueError('the selected successful run produced no fresh profiles')
    return paths


def run(arguments):
    """Run both normal test targets separately and merge only their fresh inputs."""
    target = Path(os.environ['CARGO_LLVM_COV_TARGET_DIR']).resolve()
    groups = []
    binaries = []
    profiles = []
    for label, selection in [('unittests src/lib.rs', ['--lib']),
                             ('tests/row_text_regression.rs', ['--test', 'row_text_regression'])]:
        prefix = f'gossil-libsql-{uuid.uuid4().hex}'
        env = dict(os.environ, CARGO_TERM_COLOR='never', LLVM_PROFILE_FILE_NAME=f'{prefix}-%p-%m.profraw')
        # --no-report implicitly preserves old build/profile inputs; no cleanup is requested.
        command = ['cargo', 'llvm-cov', 'test', '--no-report', *arguments, *selection]
        result = subprocess.run(command, env=env, text=True, capture_output=True)
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        if result.returncode:
            raise SystemExit(result.returncode)
        binary = executed_binary(result.stderr, label, target)
        inputs = fresh_profiles(target, prefix)
        binaries.append(binary)
        profiles.extend(inputs)
        groups.append({'label': label, 'command': command, 'profile_prefix': prefix,
                       'profiles': {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs},
                       'binary': str(binary), 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest()})
    if len(set(binaries)) != 2:
        raise ValueError('the unit and regression targets must have distinct binaries')
    tools = Path(subprocess.check_output(['rustc', '--print', 'target-libdir'], text=True).strip()).parent / 'bin'
    output = Path('target/fresh-coverage') / uuid.uuid4().hex
    output.mkdir(parents=True)
    profdata = output / 'run.profdata'
    subprocess.run([str(tools / 'llvm-profdata'), 'merge', '-sparse', *map(str, profiles), '-o', str(profdata)], check=True)
    command = [str(tools / 'llvm-cov'), 'export', '-format=lcov', f'-instr-profile={profdata}']
    for binary in binaries:
        command.extend(['-object', str(binary)])
    report = subprocess.check_output(command)
    Path('target/row-fix.lcov').write_bytes(report)
    (output / 'inputs.json').write_text(json.dumps({
        'status': 'fresh successful per-target runs only; no profile or cache cleanup',
        'groups': groups, 'report_sha256': hashlib.sha256(report).hexdigest(),
    }, indent=2) + '\n')
    print(f'Fresh profile manifest: {output / "inputs.json"}')


if __name__ == '__main__':
    run(sys.argv[1:])
