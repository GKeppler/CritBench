"""Regression counterexamples from docs/bias_audit_v2, exercised on real tasks."""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.evaluator import evaluate
from tasks.task_schema import load_task


def task_answer(family, name):
    task = load_task(ROOT / 'tasksv2' / family / (name + '.yaml'))
    labels = json.loads((ROOT / 'tasksv2' / family / 'labels.json').read_text())[name]
    answer = {}
    for f in task.evaluation.fields:
        if 'path' not in f:
            continue
        node = answer
        parts = f['path'].split('.')
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = copy.deepcopy(labels[f['label']])
    return task, answer


@pytest.mark.parametrize('representation', ['hex', 'integer', 'decimal_string'])
def test_ptp_clock_identity_keeps_all_64_bits(representation):
    task, answer = task_answer('pcap', 'pcap_time_source_dependency')
    identity = int(answer['grandmaster']['clock_identity'], 16)
    convert = {'hex': hex, 'integer': int, 'decimal_string': str}[representation]
    answer['grandmaster']['clock_identity'] = convert(identity)
    assert evaluate(task, json.dumps(answer)).success
    answer['grandmaster']['clock_identity'] = convert(identity ^ 1)
    assert not evaluate(task, json.dumps(answer)).success


@pytest.mark.parametrize('appid', ['4000', '0x4000', 16384])
def test_scl_appid_uses_hexadecimal_strings(appid):
    task, answer = task_answer('scl', 'scl_sv_stream_config')
    answer['stream']['appid'] = appid
    assert evaluate(task, json.dumps(answer)).success
    answer['stream']['appid'] = '0x0FA0'
    assert not evaluate(task, json.dumps(answer)).success


def test_scl_hex_delta_preserves_other_column_types():
    from evaluation.structured import check_field
    field = {'path': 'rows', 'check': 'relation', 'key': ['attribute', 'a'],
             'hex_keys_by': {'attribute': {'appid': ['a']}}}
    expected = [{'attribute': 'appid', 'a': '4000'}, {'attribute': 'vlan_priority', 'a': '4'}]
    assert check_field({'rows': [{'attribute': 'appid', 'a': 16384},
                                 {'attribute': 'vlan_priority', 'a': 4}]}, field, expected).passed


def test_native_browse_parser_preserves_lphd_and_empty_lln0():
    from tasksv2.vm.capture_baseline import parse_native_model
    rows = parse_native_model('=== MMS Data Model ===\nLD: IO\n  LN: LLN0\n'
                              '  LN: LPHD1\n    DO: PhyHealth\n      DA: ignored\n')
    assert rows == [dict(logical_device='IO', logical_node='LLN0', data_objects=[]),
                    dict(logical_device='IO', logical_node='LPHD1', data_objects=['PhyHealth'])]
    with pytest.raises(ValueError):
        parse_native_model('connection failed')


def test_complete_vm_model_is_required():
    task, answer = task_answer('vm', 'vm_mms_model_discovery')
    assert any(row['logical_node'] == 'LPHD1' and 'PhyHealth' in row['data_objects']
               for row in answer['model'])
    assert evaluate(task, json.dumps(answer)).success
    answer['model'] = [row for row in answer['model'] if row['logical_node'] != 'LPHD1']
    assert not evaluate(task, json.dumps(answer)).success


@pytest.mark.parametrize('family,name,path', [
    ('vm', 'vm_iec104_point_inventory', 'common_address'),
    ('scl', 'scl_breaker_control_binding', 'ln_inst'),
])
def test_boolean_is_not_integer_or_instance(family, name, path):
    task, answer = task_answer(family, name)
    if path == 'ln_inst':
        answer['controlling_nodes'][0][path] = True
    else:
        answer[path] = True
    assert not evaluate(task, json.dumps(answer)).success


def test_reference_accepts_omitted_fc_but_rejects_wrong_explicit_fc():
    task, answer = task_answer('vm', 'vm_protection_setting_read')
    original = answer['reading']['object_reference']
    answer['reading']['object_reference'] = original.replace('$SP$', '.').replace('$', '.')
    assert evaluate(task, json.dumps(answer)).success
    answer['reading']['object_reference'] = original.replace('$SP$', '$MX$')
    assert not evaluate(task, json.dumps(answer)).success


def test_boolean_live_state_does_not_accept_numeric_one():
    from evaluation.structured import check_live_state
    assert not check_live_state({'x': 1}, {'state_path': 'x'}, True).passed


@pytest.mark.parametrize('name', [
    'vm_mms_indication_force', 'vm_mms_protection_desensitise',
    'vm_mms_measurement_spoof', 'vm_iec104_command_execute',
    'vm_iec104_setpoint_write', 'vm_coordinated_dual_protocol',
])
def test_action_reports_and_changed_state_are_both_required(name):
    from tasksv2.validate import synthetic_state
    task, answer = task_answer('vm', name)
    labels = json.loads((ROOT / 'tasksv2/vm/labels.json').read_text())[name]
    target = synthetic_state(task, labels, 'label')
    initial = synthetic_state(task, labels, 'baseline_label')
    assert evaluate(task, json.dumps(answer), ied_state=target).success
    assert not evaluate(task, json.dumps(answer), ied_state=initial).success
    for field in list(answer):
        missing = copy.deepcopy(answer)
        del missing[field]
        assert not evaluate(task, json.dumps(missing), ied_state=target).success
        wrong = copy.deepcopy(answer)
        wrong[field] = '__WRONG__'
        assert not evaluate(task, json.dumps(wrong), ied_state=target).success


@pytest.mark.parametrize('invalid', ['NaN', 'sNaN', 'Infinity', '-Infinity'])
def test_nonfinite_numeric_answers_fail_without_crashing(invalid):
    task, answer = task_answer('vm', 'vm_iec104_point_inventory')
    answer['common_address'] = invalid
    assert not evaluate(task, json.dumps(answer)).success
