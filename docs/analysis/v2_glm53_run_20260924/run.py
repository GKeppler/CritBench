"""Run the three frozen v2 families; never load or record credential values."""
from pathlib import Path
import datetime,hashlib,json,subprocess,time
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
CB=ROOT/'critbench'
RUN='v2-glm53-nohint-20260924'
families={'pcap':'critbench_pcap_v2','scl':'critbench_scl_v2','vm':'critbench_iec61850_v2'}
commands={f:['inspect','eval',f'inspect_critbench/evals.py@{task}','--model','openrouter/z-ai/glm-5.3-flash','--max-sandboxes','4','--max-samples','4','--no-fail-on-error','--max-retries','3','--display','none','--log-dir',f'logs/{RUN}/{f}'] for f,task in families.items()}
paths=set()
for folder in ['tasksv2','evaluation','inspect_critbench','tasks']:
 for p in (CB/folder).rglob('*'):
  if p.is_file() and p.suffix in {'.py','.yaml','.json','.pcap','.pcapng','.scd','.cid'} and '__pycache__' not in str(p):paths.add(p)
manifest={'start_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'commands':commands,'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'inspect_version':subprocess.check_output(['inspect','--version'],text=True).strip(),'images':subprocess.check_output(['docker','image','inspect','critbench-agent:latest','critbench-ied:latest','--format','{{.RepoTags}} {{.Id}}'],text=True).strip(),'input_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)},'hint':'h0','epochs':1,'sample_retries':0,'notes':'Existing family defaults; no task/scorer changes during runs. API retries limited to 3.'}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
status={}
for family,cmd in commands.items():
 logdir=CB/'logs'/RUN/family;logdir.mkdir(parents=True,exist_ok=True)
 status[family]={'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'running'}
 (OUT/'status.json').write_text(json.dumps(status,indent=2)+'\n')
 print('Starting',family,flush=True)
 with (logdir/'console.txt').open('w') as console:
  result=subprocess.run(cmd,cwd=CB,stdout=console,stderr=subprocess.STDOUT)
 status[family].update(status='finished',exit_code=result.returncode,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
 (OUT/'status.json').write_text(json.dumps(status,indent=2)+'\n')
 print('Finished',family,'exit',result.returncode,flush=True)
manifest['end_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
manifest['changed_inputs']=[p for p,h in manifest['input_sha256'].items() if not (ROOT/p).exists() or hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
