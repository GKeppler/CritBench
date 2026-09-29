#!/usr/bin/env python3
"""Read-only offline PCAP v2 audit. Writes only this audit directory."""
import sys,json,copy,subprocess,collections,xml.etree.ElementTree as ET,importlib.util
from pathlib import Path
import yaml
from jinja2 import Environment,StrictUndefined
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'critbench'))
from tasks.task_schema import load_task,template_vars
from evaluation.evaluator import evaluate
spec=importlib.util.spec_from_file_location('v',ROOT/'critbench/tasksv2/validate.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
labels=json.loads((ROOT/'critbench/tasksv2/pcap/labels.json').read_text()); results=[]
for p in sorted((ROOT/'critbench/tasksv2/pcap').glob('*.yaml')):
 t=load_task(p);correct=v.correct_answer(t,labels[t.id]); f=t.evaluation.fields[0];key=f['path']; x=correct[key]
 probes={'correct':correct,'equivalent':v._vary(correct),'empty':'','prompt_echo':'\n'.join(Environment(undefined=StrictUndefined).from_string(z).render(**template_vars(t)) for z in [t.system_prompt,t.objective]),'omission':dict(correct,**{key:v._omit(x)}),'fabrication':dict(correct,**{key:v._fabricate(x)})}
 if isinstance(x,list) and len(x)>1 and isinstance(x[0],dict):
  a=copy.deepcopy(correct); names=list(a[key][0]); field=next((n for n in names if a[key][0].get(n)!=a[key][1].get(n)),names[0]);a[key][0][field],a[key][1][field]=a[key][1][field],a[key][0][field];probes['swapped_association']=a
 if isinstance(x,dict):
  a=copy.deepcopy(correct);ks=list(a[key]);a[key][ks[0]],a[key][ks[1]]=a[key][ks[1]],a[key][ks[0]];probes['swapped_association']=a
 a=copy.deepcopy(correct)
 def nums(z):
  if isinstance(z,dict):return {k:nums(w) for k,w in z.items()}
  if isinstance(z,list):return [nums(w) for w in z]
  if isinstance(z,str) and z.isdigit():return int(z)
  return z
 probes['numeric_string_types']=nums(a)
 if t.id=='pcap_redundancy_nodes':
  a=copy.deepcopy(correct);a['nodes'][0]['publishes_process_data']=False;probes['wrong_process_data_binding']=a
 if t.id=='pcap_time_source_dependency':
  a=copy.deepcopy(correct);a['grandmaster']['clock_identity']='0xec4670fffe0aafaf';probes['wrong_clock_identity_one_bit']=a
 if t.id=='pcap_mms_endpoints':
  a=copy.deepcopy(correct);a['association']['server_port']=102.00000000000001;probes['fractional_port']=a
 res={}
 for name,ans in probes.items():
  s=ans if isinstance(ans,str) else json.dumps(ans);r=evaluate(t,s,transcript=[]);res[name]={'success':r.success,'score':r.score,'answer':ans}
 results.append({'id':t.id,'tests':res})
(OUT/'pcap_probe_results.json').write_text(json.dumps(results,indent=2)+'\n')
# Independent fixture examination; use all occurrence values, frame IDs and timestamps.
def rows(file,filter,fields):
 cmd=['tshark','-n','-r',str(ROOT/'critbench/tasks/pcaps'/file),'-Y',filter,'-T','fields']
 for f in fields:cmd+=['-e',f]
 return [dict(zip(fields,l.split('\t'))) for l in subprocess.run(cmd,capture_output=True,text=True,check=True).stdout.splitlines()]
gf=['frame.number','frame.time_relative','eth.src','eth.dst','goose.appid','goose.gocbRef','goose.datSet','goose.goID','goose.confRev','goose.stNum','goose.timeAllowedtoLive'];g=rows('goose_breaker_trip.pcap','goose',gf)
sf=['frame.number','frame.time_relative','eth.src','eth.dst','sv.appid','sv.svID','sv.confRev','sv.noASDU','sv.smpSynch'];s=rows('goose_breaker_trip.pcap','sv',sf)
unique=lambda rr,ff: [dict(zip(ff,r)) for r in sorted(set(tuple(x.get(f,'') for f in ff) for x in rr))]
prev={};changes=[]
for r in g:
 k=r['goose.gocbRef']; st=r['goose.stNum']
 if k in prev and prev[k]!=st:changes.append(dict(r,from_st_num=prev[k]))
 prev[k]=st
sprev={};schanges=[]
for r in s:
 sid=r['sv.svID'].split(',')[0];val=r['sv.smpSynch'].split(',')[0]
 if sid in sprev and sprev[sid]!=val:schanges.append(dict(r,from_smp_synch=sprev[sid]))
 sprev[sid]=val
sup=rows('goose_breaker_trip.pcap','hsr_prp_supervision',['eth.src'])
ptp=rows('goose_breaker_trip.pcap','ptp.v2.messagetype==0x0b',['frame.number','eth.src','ptp.v2.an.grandmasterclockidentity','ptp.v2.an.priority1','ptp.v2.an.localstepsremoved','ptp.v2.domainnumber'])
m=rows('MMS_Traffic_09-02-2024_12-58.pcapng','mms',['frame.number','ip.src','ip.dst','tcp.srcport','tcp.dstport','mms.domainId','mms.itemId'])
rate=rows('Trip_Samples_Values_all_devices_240430.pcapng','sv',sf);per=collections.defaultdict(list)
for r in rate:per[r['sv.svID'].split(',')[0]].append(r)
rates={}
for sid,rr in per.items():
 span=float(rr[-1]['frame.time_relative'])-float(rr[0]['frame.time_relative']);ns={int(x['sv.noASDU']) for x in rr};n=next(iter(ns));rates[sid]={'frames':len(rr),'noASDU_values':sorted(ns),'duration':span,'endpoint_interval_sample_rate':(len(rr)-1)*n/span,'rounded_rate':round((len(rr)-1)*n/span/100)*100}
scd=ET.parse(ROOT/'critbench/tasks/scd/KASTEL_Lab_Siemens.scd').getroot();ns={'s':'http://www.iec.ch/61850/2003/SCL'}
truth={'goose_metadata':unique(g,gf[2:]),'goose_events':changes,'sv_metadata':unique(s,sf[2:]),'sv_transitions':schanges,'supervision_sources':unique(sup,['eth.src']),'ptp_announcements':unique(ptp,list(ptp[0])[1:]),'ptp_first_frame':ptp[0]['frame.number'],'mms_domains':sorted({d for r in m for d in r['mms.domainId'].split(',') if d}),'mms_endpoints':unique(m,['ip.src','ip.dst','tcp.srcport','tcp.dstport']),'mms_rcb_attributes':sorted({a for r in m for a in r['mms.itemId'].split(',') if '$BR$' in a or '$RP$' in a}),'sv_rates':rates,'scd_ieds':sorted(x.get('name') for x in scd.findall('.//s:IED',ns)),'scd_smv_ids':sorted({x.get('smvID') for x in scd.findall('.//s:SampledValueControl',ns)})}
(OUT/'pcap_independent_truth.json').write_text(json.dumps(truth,indent=2)+'\n')
print('Done',len(results),'tasks;',sum(r['tests']['correct']['success'] for r in results),'correct passes')
