"""Extract completed Inspect logs without changing or rescoring experiments."""
from pathlib import Path
import sys,json,csv,math,hashlib
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'critbench'))
from inspect_ai.log import read_eval_log
from inspect_critbench.v2_metrics import summarize
BASE=ROOT/'critbench/logs/v2-glm53-nohint-20260924'
records=[];runs=[]
for family,dirname in [('vm','vm'),('pcap','pcap-rerun'),('scl','scl-rerun')]:
 for path in sorted((BASE/dirname).glob('*.eval')):
  log=read_eval_log(path)
  runs.append({'family':family,'path':str(path.relative_to(ROOT)),'status':log.status,'stats':log.stats.model_dump(mode='json'),'config':log.eval.config.model_dump(mode='json'),'task_args':log.eval.task_args,'results':log.results.model_dump(mode='json') if log.results else None,'error':log.error.message if log.error else None})
  for sample in log.samples or []:
   scores=sample.scores or {};score=next(iter(scores.values())) if scores else None
   metadata=score.metadata or {} if score else {}
   tools=[{'name':call.function,'arguments':call.arguments} for message in sample.messages for call in (getattr(message,'tool_calls',None) or [])]
   failures=[d for d in metadata.get('details',metadata.get('checks',[])) if not d.get('passed')]
   record={'id':sample.id,'family':family,'log':str(path.relative_to(ROOT)),'score':score.value if score else None,'success':bool(metadata.get('success')) if score else None,'floor_control':sample.metadata.get('floor_control',False),'fixture_ids':sample.metadata.get('fixture_ids',[]),'error':sample.error.message if sample.error else None,'limit':sample.limit.model_dump(mode='json') if sample.limit else None,'turn_count':sample.turn_count,'total_time':sample.total_time,'working_time':sample.working_time,'model_usage':{m:u.model_dump(mode='json') for m,u in (sample.model_usage or {}).items()},'tool_calls':tools,'answer':sample.output.completion,'explanation':score.explanation if score else None,'score_metadata':metadata,'failed_checks':failures}
   records.append(record)
summary={}
for family in ['pcap','scl','vm']:
 rr=[r for r in records if r['family']==family];valid=[r for r in rr if r['score'] is not None]
 summary[family]={'recorded':len(rr),'scored':len(valid),'full_success':sum(bool(r['success']) for r in valid),'errors':sum(bool(r['error']) for r in rr),'limits':sum(bool(r['limit']) for r in rr),'metrics_scored_only':summarize(valid) if valid else None}
manifest=json.loads((OUT/'manifest.json').read_text())
changed=[p for p,h in manifest['input_sha256'].items() if not (ROOT/p).exists() or hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
(OUT/'results.json').write_text(json.dumps({'summary':summary,'runs':runs,'samples':records,'changed_inputs':changed},indent=2,default=str)+'\n')
with (OUT/'task_results.csv').open('w') as f:
 writer=csv.DictWriter(f,fieldnames=['id','family','score','success','floor_control','error','limit','turn_count','total_time']);writer.writeheader();writer.writerows({k:r[k] for k in writer.fieldnames} for r in records)
print(json.dumps(summary,indent=2));print('Changed benchmark inputs:',changed)
