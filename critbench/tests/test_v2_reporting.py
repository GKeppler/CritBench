"""V2 fixture isolation and aggregate validity, without paid model calls."""
import math
import sys
from pathlib import Path
from types import SimpleNamespace
import json
import asyncio

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tasksv2.static_fixtures import mount_problems, declared_files
from inspect_critbench.v2_metrics import summarize


def row(value, fixtures, floor=False):
    return dict(score=value, success=value == 1, fixture_ids=fixtures, floor_control=floor)


def test_controls_excluded_and_shared_fixtures_clustered():
    rows = [row(1, ['a']), row(1, ['a']), row(0, ['b']), row(0, ['c'], True)]
    result = summarize(rows)
    assert result['headline_mean'] == pytest.approx(2 / 3)
    assert result['floor_mean'] == 0
    assert result['fixture_clusters'] == 2
    assert result['fixture_cluster_stderr'] == pytest.approx(4 / 9)
    assert result['headline_full_success'] == pytest.approx(2 / 3)


def test_cross_fixture_task_merges_components():
    result = summarize([row(1, ['a']), row(0, ['b']), row(1, ['a', 'b'])])
    assert result['fixture_clusters'] == 1
    assert math.isnan(result['fixture_cluster_stderr'])
    assert math.isnan(summarize([])['headline_mean'])


@pytest.mark.parametrize('family', ['scl', 'pcap'])
def test_all_static_mounts_are_exact_files(family):
    for path in (ROOT / 'tasksv2' / family).glob('*.yaml'):
        raw = yaml.safe_load(path.read_text())
        compose = ROOT / 'inspect_critbench/compose' / raw['sandbox']
        assert mount_problems(raw, compose) == [], path


def test_directory_mount_does_not_pass_file_gate(tmp_path):
    raw = yaml.safe_load((ROOT / 'tasksv2/scl/scl_ied_inventory.yaml').read_text())
    compose = tmp_path / 'bad.yaml'
    compose.write_text(yaml.safe_dump({'services': {'default': {'volumes': [
        f'{ROOT / "tasks/scd"}:/code/tasks/scd:ro']}}}))
    assert mount_problems(raw, compose)


def test_inspect_v2_metadata_and_metrics_integration():
    pytest.importorskip('inspect_ai')
    from inspect_ai.scorer import SampleScore, Target
    from inspect_critbench.dataset import critbench_dataset
    from inspect_critbench.scorer import critbench_scorer, v2_summary
    from inspect_critbench.evals import critbench_scl_v2
    from tasksv2.validate import correct_answer
    from tasks.task_schema import load_task
    task = critbench_scl_v2()
    assert task.version == 2 and task.metrics
    scores = []
    samples = list(critbench_dataset('../tasksv2/scl'))
    assert len(samples) == 19
    assert sum(s.metadata['floor_control'] for s in samples) == 3
    for sample in samples:
        assert set(sample.metadata) == {'yaml_path', 'benchmark_version', 'floor_control',
                                        'fixture_ids', 'family', 'hint_level'}
        rawtask = load_task(Path(sample.metadata['yaml_path']))
        labels = json.loads((ROOT / 'tasksv2/scl/labels.json').read_text())[sample.id]
        answer = json.dumps(correct_answer(rawtask, labels))
        state = SimpleNamespace(metadata=sample.metadata, output=SimpleNamespace(completion=answer), messages=[])
        score = asyncio.run(critbench_scorer()(state, Target('')))
        scores.append(SampleScore(score=score, sample_id=sample.id))
    summary = v2_summary()(scores)
    assert summary['headline_mean'] == 1
    assert summary['headline_n'] == 16 and summary['floor_n'] == 3
    assert summary['fixture_clusters'] == 2


def test_inspect_log_reports_only_v2_aggregates(tmp_path):
    pytest.importorskip('inspect_ai')
    from inspect_ai import Task, eval as inspect_eval
    from inspect_ai.solver import solver
    from inspect_critbench.dataset import critbench_dataset
    from inspect_critbench.scorer import critbench_scorer, v2_summary
    from tasksv2.validate import correct_answer
    from tasks.task_schema import load_task

    @solver
    def known_answer():
        async def solve(state, generate):
            path = Path(state.metadata['yaml_path'])
            labels = json.loads((path.parent / 'labels.json').read_text())[state.sample_id]
            state.output.completion = json.dumps(correct_answer(load_task(path), labels))
            return state
        return solve

    samples = list(critbench_dataset('../tasksv2/scl'))[:2]
    for sample in samples:
        sample.sandbox = None
    task = Task(dataset=samples, solver=known_answer(), scorer=critbench_scorer(),
                metrics=[v2_summary()], version=2)
    logs = inspect_eval(task, model='mockllm/model', log_dir=str(tmp_path), display='none')
    assert logs[0].status == 'success', logs[0].error
    metrics = logs[0].results.scores[0].metrics
    assert 'headline_mean' in metrics and 'mean' not in metrics
    assert metrics['headline_n'].value == 1 and metrics['floor_n'].value == 1
