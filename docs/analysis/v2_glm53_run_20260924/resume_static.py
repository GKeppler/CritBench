from pathlib import Path
import os,json,subprocess,datetime,threading,concurrent.futures
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2];CB=ROOT/'critbench'
manifest=json.loads((OUT/'manifest.json').read_text())
env=os.environ.copy();env['PYTHONPATH']=str(CB)
result={};lock=threading.Lock()
def run_family(family):
 cmd=list(manifest['commands'][family]);cmd[-1]+='-rerun'
 directory=CB/cmd[-1];directory.mkdir(parents=True,exist_ok=True)
 with lock:
  result[family]={'status':'running','started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':cmd,'PYTHONPATH':str(CB),'reason':'Initial launch failed importing tasksv2 before sample execution.','concurrency':'4 per family, concurrent with VM'}
  (OUT/'static_rerun_status.json').write_text(json.dumps(result,indent=2)+'\n')
 print('Starting corrected',family,flush=True)
 with (directory/'console.txt').open('w') as out:
  run=subprocess.run(cmd,cwd=CB,env=env,stdout=out,stderr=subprocess.STDOUT)
 with lock:
  result[family].update(status='finished',exit_code=run.returncode,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
  (OUT/'static_rerun_status.json').write_text(json.dumps(result,indent=2)+'\n')
 print('Finished corrected',family,run.returncode,flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 list(pool.map(run_family,['pcap','scl']))
