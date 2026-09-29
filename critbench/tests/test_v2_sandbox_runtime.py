"""Opt-in Docker check: RUN_DOCKER_TESTS=1 pytest -q <this file>."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tasksv2.static_fixtures import declared_files

CONFIGS = {}
for path in (ROOT / 'tasksv2').glob('*/*.yaml'):
    raw = yaml.safe_load(path.read_text())
    if raw.get('sandbox'):
        CONFIGS[raw['sandbox']] = sorted(declared_files(raw))


@pytest.mark.skipif(os.environ.get('RUN_DOCKER_TESTS') != '1', reason='opt-in local Docker test')
@pytest.mark.parametrize('name,expected', sorted(CONFIGS.items()))
def test_only_declared_readonly_files_reach_agent(name, expected):
    project = f'critbench-v2-test-{os.getpid()}'
    compose = ROOT / 'inspect_critbench/compose' / name
    prefix = ['docker', 'compose', '-p', project, '-f', str(compose)]
    script = '''import pathlib, json
expected = json.loads(EXPECTED)
found = sorted(str(p) for d in ['/code/tasks/scd', '/code/tasks/pcaps']
               for p in pathlib.Path(d).glob('*') if p.is_file())
assert found == expected, (found, expected)
for p in expected:
    try:
        open(p, 'ab').close()
    except OSError:
        continue
    raise AssertionError('writable fixture: ' + p)
'''.replace('EXPECTED', repr(json.dumps(expected)))
    try:
        subprocess.run(prefix + ['run', '--rm', '--no-deps', '--entrypoint', 'python3',
                                 'default', '-c', script],
                       capture_output=True, text=True, timeout=90, check=True)
    finally:
        subprocess.run(prefix + ['down'], capture_output=True, timeout=30, check=True)
