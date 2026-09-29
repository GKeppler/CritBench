"""Offline v2 VM oracle probes and hardware pending checks. No network calls."""
import copy,importlib.util,json,pathlib,sys
R=pathlib.Path(__file__).resolve().parents[2];B=R/'docs/bias_audit_v2';sys.path.insert(0,str(R/'critbench'))
from tasks.task_schema import load_task
from evaluation.evaluator import evaluate

def module(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def put(d,path,v):
 ps=path.split('.')
 for p in ps[:-1]:d=d.setdefault(p,{})
 d[ps[-1]]=copy.deepcopy(v)

def score(task,ans,state):
 r=evaluate(task,json.dumps(ans),ied_state=state,transcript=[])
 return {'score':r.score,'success':r.success,'details':[{'type':x.check_type,'passed':x.passed,'actual':x.actual,'details':x.details} for x in r.details]}

results=[]
for p in sorted((R/'critbench/tasksv2/vm').glob('*.yaml')):
 task=load_task(p);a={};initial={};target={}
 for f in task.evaluation.fields:
  labs=task.evaluation.labels
  if f['check']=='live_state':
   put(initial,f['state_path'],labs[f['baseline_label']]);put(target,f['state_path'],labs[f['label']])
  else:put(a,f['path'],labs[f['label']])
 rec={'id':task.id,'oracle_answer':a,'no_transcript_initial_state':score(task,a,initial),'no_transcript_target_state':score(task,a,target),'note':'Supplying target state exercises oracle only; it does not demonstrate runtime state forgery. Before-values are copied labels, not actual observed reads.'}
 if task.id=='vm_protection_setting_read':
  bad=copy.deepcopy(a);bad['reading']['object_reference']=bad['reading']['object_reference'].replace('$SP$','$MX$');rec['wrong_explicit_FC']=score(task,bad,target)
 if task.id=='vm_iec104_point_inventory':
  bad=copy.deepcopy(a);bad['common_address']=True;rec['boolean_in_integer_CA']=score(task,bad,target)
 if task.id=='vm_mms_model_discovery':
  fixed=copy.deepcopy(a);fixed['model'].append({'logical_device':'simpleIOGenericIO','logical_node':'LPHD1','data_objects':['PhyHealth']});rec['source_complete_LPHD1_answer']=score(task,fixed,{})
 if task.id in ('vm_mms_indication_force','vm_mms_protection_desensitise'):
  bad=copy.deepcopy(a);bad['written_value']='WRONG';bad['object_reference']='nonexistent/WRONG';rec['wrong_report_fields_target_state']=score(task,bad,target)
 if task.id=='vm_coordinated_dual_protocol':rec['read_order_unchecked']='No action/read event timestamps supplied; copied initial values plus target snapshot still pass.'
 # Out-of-population item should reduce Jaccard score.
 for f in task.evaluation.fields:
  if f['check'] in ('relation','set'):
   bad=copy.deepcopy(a);v=bad
   for k in f['path'].split('.'):v=v[k]
   v.append({'logical_device':'fabricated','logical_node':'fabricated','data_objects':[]} if f['check']=='relation' else 'fabricated')
   rec['extra_entry']=score(task,bad,target);break
 results.append(rec)
hw=module(R/'critbench/tasksv2/hardware/truth.py','audit_hw_truth');pending=[]
for p in sorted((R/'critbench/tasksv2/hardware').glob('*.yaml')):
 tid=p.stem
 try:hw.TRUTH[tid]();status='unexpected baseline available'
 except hw.BaselineMissing as e:status=str(e)
 pending.append({'id':tid,'baseline_result':status,'performed':'Read-only truth extractor called; no baseline invented, no task scored.'})
# Exercise capture functions with in-memory mocked rows, not physical packets.
cap=module(R/'critbench/tasksv2/hardware/capture_baseline.py','audit_hw_capture')
class Failed:
 stdout='';stderr='permission denied';returncode=1
cap.subprocess.run=lambda *a,**kw:Failed()
empty=cap.capture('NOT_A_REAL_INTERFACE',1)
# Demonstrate first lexicographic source selection among two announced clocks.
row1={'eth.src':'00:00:00:00:00:01','ptp.v2.an.grandmasterclockidentity':'clock-A','ptp.v2.an.priority1':'255','ptp.v2.an.localstepsremoved':'9','ptp.v2.domainnumber':'0'}
row2={'eth.src':'00:00:00:00:00:02','ptp.v2.an.grandmasterclockidentity':'clock-B','ptp.v2.an.priority1':'1','ptp.v2.an.localstepsremoved':'0','ptp.v2.domainnumber':'0'}
cap._tshark=lambda interface,fil,spec,seconds:[row2,row1] if fil.startswith('ptp') else []
ptp=cap.capture('NOT_A_REAL_INTERFACE',1)
out={'vm':results,'hardware':pending,'capture_checker_tests':{'failed_tshark_becomes_empty_snapshot':empty,'two_announcers_selected':ptp['ptp_grandmaster'],'note':'Mocked return objects/rows only; not lab labels. Selecting sorted source is not an actual grandmaster-selection calculation.'}}
(B/'dynamic_probe_results.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'vm':len(results),'hardware_pending':len(pending),'initial_full':[r['id'] for r in results if r['no_transcript_initial_state']['success']],'target_full':[r['id'] for r in results if r['no_transcript_target_state']['success']],'source_complete_model_score':next(r['source_complete_LPHD1_answer']['score'] for r in results if 'source_complete_LPHD1_answer' in r)},indent=2))
