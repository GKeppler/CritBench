"""Read-only validator and independent grader boundary probes for tasksv2."""
from pathlib import Path
import copy
import importlib.util
import json
import sys
import yaml
from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'critbench'))
from tasks.task_schema import load_task, render_objective, template_vars
from evaluation.evaluator import evaluate
from evaluation.structured import check_evidence, check_field
spec = importlib.util.spec_from_file_location('v2_validator', ROOT / 'critbench/tasksv2/validate.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
rows = []
for family in ('scl', 'pcap', 'vm', 'hardware'):
    folder = ROOT / 'critbench/tasksv2' / family
    truth = validator._load_truth(folder)
    labels = json.loads((folder / 'labels.json').read_text())
    for path in sorted(folder.glob('*.yaml')):
        raw = yaml.safe_load(path.read_text())
        problems, profile = validator.check_task(path, truth, labels, strict=True)
        row = {'id': raw['id'], 'path': str(path.relative_to(ROOT)), 'family': family,
               'validator_problems': problems, 'profile': profile, 'additional_probes': {}}
        if raw['id'] not in labels:
            row['status'] = 'awaiting_baseline'
            rows.append(row)
            continue
        row['status'] = 'current'
        task = load_task(path)
        answer = validator.correct_answer(task, labels[task.id])
        done = validator.synthetic_state(task, labels[task.id], 'label')
        row['additional_probes']['correct_no_transcript'] = evaluate(task, json.dumps(answer), ied_state=done, transcript=[]).to_dict()
        # Test omission at EACH graded answer field, not just the first one.
        omissions = {}
        for field in task.evaluation.fields:
            if 'path' not in field or field['check'] in ('live_state', 'evidence'):
                continue
            changed = copy.deepcopy(answer)
            parts = field['path'].split('.')
            parent = changed
            for part in parts[:-1]: parent = parent[part]
            del parent[parts[-1]]
            omissions[field['path']] = evaluate(task, json.dumps(changed), ied_state=done, transcript=[]).to_dict()
        row['additional_probes']['each_field_omitted'] = omissions
        # Identify sibling files exposed by directory mounts vs declared environment paths.
        if raw.get('sandbox'):
            compose = ROOT / 'critbench/inspect_critbench/compose' / raw['sandbox']
            cfg = yaml.safe_load(compose.read_text())
            visible = set()
            for service in cfg.get('services', {}).values():
                for volume in service.get('volumes', []):
                    source, target, *_ = volume.split(':')
                    local = (compose.parent / source).resolve()
                    if local.is_dir():
                        visible.update(str(Path(target) / f.relative_to(local)) for f in local.rglob('*') if f.is_file())
            declared = {v for v in raw.get('environment', {}).values() if isinstance(v, str) and v.startswith('/code/')}
            row['undeclared_visible_fixtures'] = sorted(visible - declared)
        rows.append(row)

# A real echo process could generate this exact output; this only tests the
# recorded-output predicate and executes no network or shell command.
echo = [{'type': 'function_call', 'name': 'bash', 'call_id': '1',
         'arguments': json.dumps({'cmd': 'printf device42'})},
        {'type': 'function_call_output', 'call_id': '1', 'output': 'device42'}]
probes = {
    'echo_output_evidence_passes': check_evidence(echo, {'tool': ['bash']}, {'device':'device42','value':999}).passed,
    'numeric_fact_not_required_by_evidence': check_evidence(echo, {'tool':['bash']}, {'device':'device42','value':-123456}).passed,
    'numeric_only_evidence_unverifiable': not check_evidence(echo, {'tool':['bash']}, {'value':42}).passed,
    'integer_accepts_boolean': check_field({'n':True}, {'path':'n','check':'integer'}, 1).passed,
    'distinct_64bit_hex_ids_compare_equal': check_field({'id':'0xec4670fffe0aafaf'}, {'path':'id','check':'scalar'}, '0xec4670fffe0aafae').passed,
    'wrong_explicit_fc_reference_passes': check_field({'ref':'simpleIOprotection/PTOC1$MX$StrVal$setMag$f'}, {'path':'ref','check':'reference'}, 'simpleIOprotection/PTOC1$SP$StrVal$setMag$f').passed,
}
(OUT / 'harness_probe_results.json').write_text(json.dumps({'tasks':rows,'boundary_probes':probes}, indent=2)+'\n')
print(json.dumps({'tasks':len(rows),'pending':sum(r['status']=='awaiting_baseline' for r in rows),
                  'validator_failures':{r['id']:r['validator_problems'] for r in rows if r['status']!='awaiting_baseline' and r['validator_problems']},
                  'tasks_with_undeclared_sibling_fixtures':sum(bool(r.get('undeclared_visible_fixtures')) for r in rows),
                  'boundary_probes':probes}, indent=2))
