"""Read-only independent XML extraction and production-grader probes for all19 SCL v2 tasks.
Run: python3 docs/bias_audit_v2/scl_checks.py . Does not import production truth.py.
"""
from pathlib import Path
import sys,json,copy,collections
import yaml
from lxml import etree as E
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'critbench'))
from tasks.task_schema import load_task
from evaluation.evaluator import evaluate
NS={'s':'http://www.iec.ch/61850/2003/SCL'}
F={p.name:E.parse(str(p)) for p in (ROOT/'critbench/tasks/scd').glob('*')}
S=F['KASTEL_Lab_Siemens.scd'];A=F['KASTEL_Lab_ABB.scd'];C=F['ABB_REL670.cid']
def q(e,x):return e.xpath(x,namespaces=NS)
def owner(e,tag,attr):return q(e,'ancestor::s:'+tag)[0].get(attr)
def ids(e):return owner(e,'IED','name'),owner(e,'LDevice','inst')
def refs(es):return list({(str(Path(e.getroottree().docinfo.URL).relative_to(ROOT)),e.sourceline):{'file':str(Path(e.getroottree().docinfo.URL).relative_to(ROOT)),'line':e.sourceline} for e in es}.values())
ADDR={}
for r in [S,A]:
 a=[]
 for e in q(r,'//s:Communication/s:SubNetwork/s:ConnectedAP/*[self::s:GSE or self::s:SMV]'):
  ps={p.get('type'):p.text for p in q(e,'s:Address/s:P')}
  a.append({'ied':e.getparent().get('iedName'),'ld':e.get('ldInst'),'control_block':e.get('cbName'),'kind':E.QName(e).localname,'subnetwork':owner(e,'SubNetwork','name'),'mac':ps.get('MAC-Address'),'appid':ps.get('APPID'),'vlan_id':ps.get('VLAN-ID'),'vlan_priority':ps.get('VLAN-PRIORITY'),'e':e})
 ADDR[r]=a
PUB=[]
for e in q(S,'//s:GSEControl|//s:SampledValueControl'):
 i,l=ids(e);matches=[a for a in ADDR[S] if (a['ied'],a['ld'],a['control_block'])==(i,l,e.get('name'))];assert len(matches)==1
 PUB.append({**matches[0],'ce':e,'dataset':e.get('datSet'),'conf_rev':e.get('confRev'),'go_id':e.get('appID'),'smv_id':e.get('smvID'),'smp_rate':e.get('smpRate'),'nof_asdu':e.get('nofASDU')})
EX=q(S,'//s:ExtRef');EQ=q(S,'//s:VoltageLevel[s:Voltage[@unit="V" and @multiplier="k" and text()="20"]]/s:Bay[s:ConductingEquipment[@type="CBR"]]/s:ConductingEquipment');assert EQ
CB=[e for e in EQ if e.get('type')=='CBR'];assert len(CB)==1
BIND=q(CB[0],'s:LNode')
def pick(d,ks):return {k:d[k] for k in ks.split()}
def derive(id):
 es=[]
 if id=='scl_ied_inventory':
  es=q(S,'//s:IED');d={'ieds':[{k:e.get(k,'') for k in ['name','manufacturer','type']} for e in es]}
 elif id=='scl_bay_primary_equipment':es=EQ;d={'bay':es[0].getparent().get('name'),'equipment':[dict(name=e.get('name'),type=e.get('type')) for e in es]}
 elif id=='scl_relay_ld_architecture':es=q(C,'//s:IED//s:LDevice');d={'logical_devices':[dict(ld=e.get('inst'),ln_count=len(q(e,'s:LN|s:LN0'))) for e in es]}
 elif id=='scl_protection_ln_inventory':
  es=q(C,'//s:IED//s:LDevice');vals=[]
  for e in es:
   cs=sorted({ln.get('lnClass') for ln in q(e,'s:LN|s:LN0') if ln.get('lnClass','').startswith('P')})
   if cs:vals.append(dict(ld=e.get('inst'),protection_classes=cs))
  d={'protection_lds':vals}
 elif id=='scl_goose_publication_map':
  pp=[p for p in PUB if p['kind']=='GSE'];es=[x for p in pp for x in [p['e'],p['ce']]];d={'publications':[pick(p,'ied ld control_block dataset conf_rev mac appid vlan_id') for p in pp]}
 elif id=='scl_sv_stream_config':
  pp=[p for p in PUB if p['kind']=='SMV'];assert len(pp)==1;p=pp[0];es=[p['e'],p['ce']];d={'stream':pick(p,'ied control_block smv_id dataset smp_rate nof_asdu mac appid vlan_id subnetwork')}
 elif id=='scl_subnetwork_attachment':
  es=q(S,'//s:SubNetwork/s:ConnectedAP/s:Address/s:P[@type="IP"]');d={'attachments':[dict(subnetwork=owner(e,'SubNetwork','name'),ied=owner(e,'ConnectedAP','iedName'),ip=e.text) for e in es]}
 elif id=='scl_multihomed_ieds':
  es=q(S,'//s:SubNetwork/s:ConnectedAP');net=collections.defaultdict(set)
  for e in es:net[e.get('iedName')].add(e.getparent().get('name'))
  d={'multihomed':[dict(ied=i,subnetworks=sorted(v)) for i,v in sorted(net.items()) if len(v)>1]}
 elif id=='scl_breaker_control_binding':es=[CB[0]]+BIND;d={'breaker':CB[0].get('name'),'controlling_nodes':[dict(ied=e.get('iedName'),ld=e.get('ldInst'),ln_class=e.get('lnClass'),prefix=e.get('prefix',''),ln_inst=e.get('lnInst','')) for e in BIND]}
 elif id=='scl_goose_subscription_graph':
  es=[e for e in EX if e.get('iedName')];counts=collections.Counter((owner(e,'IED','name'),e.get('iedName'),e.get('srcCBName',''),e.get('serviceType','')) for e in es);d={'subscriptions':[dict(subscriber=s,publisher=p,control_block=c,service=t,signal_count=n) for (s,p,c,t),n in sorted(counts.items())]}
 elif id=='scl_cross_file_ied_delta':
  es=q(S,'//s:IED')+q(A,'//s:IED');a={e.get('name') for e in q(S,'//s:IED')};b={e.get('name') for e in q(A,'//s:IED')};d={'only_in_file_a':sorted(a-b),'only_in_file_b':sorted(b-a),'in_both':sorted(a&b)}
 elif id=='scl_goose_addressing_conflicts':
  es=[a['e'] for a in ADDR[S] if a['kind']=='GSE'];out=[]
  for field in ['appid','mac']:
   gs=collections.defaultdict(list)
   for a in ADDR[S]:
    if a['kind']=='GSE':gs[a[field]].append('/'.join(a[k] for k in ['ied','ld','control_block']))
   for v,bs in sorted(gs.items()):
    if len(bs)>1:out.append(dict(field=field,value=v,control_blocks=sorted(bs)))
  d={'conflicts':out}
 elif id=='scl_unbound_subscriptions':
  es=[e for e in EX if not e.get('iedName')];c=collections.Counter(owner(e,'IED','name') for e in es);d={'unbound':[dict(ied=i,count=n) for i,n in sorted(c.items())]}
 elif id=='scl_unsegregated_streams':
  aa=[a for a in ADDR[S] if a['vlan_id']=='000'];es=[a['e'] for a in aa];d={'unsegregated':[pick(a,'ied ld control_block subnetwork') for a in aa]}
 elif id=='scl_cross_file_goose_delta':
  out=[]
  for a in ADDR[S]:
   for b in ADDR[A]:
    if all(a[k]==b[k] for k in ['ied','ld','control_block']):
     es += [a['e'],b['e']]
     for k in ['mac','appid','vlan_id','vlan_priority','subnetwork']:
      if a[k]!=b[k]:out.append(dict(ied=a['ied'],control_block=a['control_block'],attribute=k,file_a=a[k],file_b=b[k]))
  d={'divergences':out}
 elif id=='scl_setting_group_exposure':
  es=q(S,'//s:SettingControl[number(@numOfSGs)>1]');d={'switchable':[dict(ied=ids(e)[0],ld=ids(e)[1],num_of_sgs=int(e.get('numOfSGs'))) for e in es]}
 elif id=='scl_switchgear_control_surface':
  types={e.get('id'):e for e in q(S,'//s:LNodeType')};dots={e.get('id'):e for e in q(S,'//s:DOType')};direct=[];sbo=[]
  for ln in q(S,'//s:LN[@lnClass="XCBR" or @lnClass="XSWI" or @lnClass="CSWI"]'):
   for do in q(types[ln.get('lnType')],'s:DO'):
    val=q(ln,'s:DOI[@name="'+do.get('name')+'"]/s:DAI[@name="ctlModel"]/s:Val') or q(dots[do.get('type')],'s:DA[@name="ctlModel"]/s:Val')
    if val:
     es += [ln,do,val[0]];item=(*ids(ln),do.get('name'))
     if val[0].text.startswith('direct'):direct.append(item)
     if val[0].text.startswith('sbo'):sbo.append(item)
  d={'direct_operable_locations':[dict(ied=i,ld=l) for i,l in sorted({(i,l) for i,l,o in direct})],'direct_operable_data_objects':sorted({o for i,l,o in direct}),'select_before_operate_ieds':sorted({i for i,l,o in sbo})}
 elif id=='scl_goose_spoof_preconditions':
  # Locate actual trip data semantics, not production extractor's name suffix.
  es=[e for e in EX if owner(e,'IED','name')=='E01A103_' and e.get('lnClass')=='PTRC' and e.get('doName')=='Op'];src={(e.get('iedName'),e.get('srcLDInst'),e.get('srcCBName')) for e in es};assert len(src)==1
  p=next(p for p in PUB if (p['ied'],p['ld'],p['control_block']) in src);es += [p['e'],p['ce']];d={'target_publisher':p['ied'],'frame':dict(destination_mac=p['mac'],**pick(p,'appid vlan_id vlan_priority go_id dataset conf_rev'))}
 elif id=='scl_process_to_breaker_path':
  sv=[p for p in PUB if p['kind']=='SMV'];assert len(sv)==1;sv=sv[0]
  consumers=[e for e in EX if (e.get('iedName'),e.get('srcLDInst'),e.get('srcCBName'),e.get('serviceType'))==(sv['ied'],sv['ld'],sv['control_block'],'SMV')];iedset={owner(e,'IED','name') for e in consumers};assert len(iedset)==1;ied=next(iter(iedset));trip=[]
  for p in PUB:
   if p['ied']!=ied or p['kind']!='GSE':continue
   ds=q(p['ce'].getparent(),'s:DataSet[@name="'+p['dataset']+'"]');assert ds
   if q(ds[0],'s:FCDA[@lnClass="PTRC" and @doName="Op"]'):trip.append(p);es += [ds[0],p['ce']]
  # Check configured receiving trip inputs and their engineering binding.
  receivers=[e for e in EX if e.get('iedName')==ied and e.get('lnClass')=='PTRC' and e.get('doName')=='Op' and any(e.get('srcLDInst')==p['ld'] and e.get('srcCBName')==p['control_block'] for p in trip)]
  assert {owner(e,'IED','name') for e in receivers}&{e.get('iedName') for e in BIND}
  es += consumers+receivers+[sv['ce'],CB[0]]+BIND
  d={'chain':dict(merging_unit=sv['ied'],sv_control_block=sv['control_block'],protection_ied=ied,trip_control_block=sorted({p['control_block'] for p in trip}),trip_dataset=sorted({p['dataset'] for p in trip}),breaker=CB[0].get('name'),breaker_controlling_ieds=sorted({e.get('iedName') for e in BIND}))}
 else:raise AssertionError(id)
 return d,refs(es)
def reorder(x):
 if isinstance(x,dict):return {k:reorder(v) for k,v in reversed(list(x.items()))}
 if isinstance(x,list):return [reorder(v) for v in reversed(x)]
 return x
def mutate(x):
 if isinstance(x,dict):
  k=next(iter(x));x[k]=mutate(x[k]);return x
 if isinstance(x,list):x[0]=mutate(x[0]);return x
 return '__WRONG__'
RESULT=[]
for p in sorted((ROOT/'critbench/tasksv2/scl').glob('*.yaml')):
 raw=yaml.safe_load(p.read_text());t=load_task(p);ans,evidence=derive(raw['id']);first=raw['evaluation']['fields'][0]['path'];assert '.' not in first
 omitted=copy.deepcopy(ans)
 if isinstance(omitted[first],list):omitted[first].pop()
 elif isinstance(omitted[first],dict):omitted[first].pop(next(iter(omitted[first])))
 else:omitted.pop(first)
 fabricated=copy.deepcopy(ans)
 if isinstance(fabricated[first],list):fabricated[first].append(mutate(copy.deepcopy(fabricated[first][0])))
 elif isinstance(fabricated[first],dict):fabricated[first][next(iter(fabricated[first]))]='__WRONG__'
 else:fabricated[first]='__WRONG__'
 probes={'independent_xml_answer':ans,'equivalent_reordered':reorder(ans),'omitted_required':omitted,'fabricated_entity_or_wrong_value':fabricated,'prompt_echo':raw['system_prompt']+'\n'+raw['objective']+'\n'+raw['answer_schema'],'h2_only':raw['hints']['h2'],'empty':'','negated_wrapped_json':'The following answer is false; reject every stated fact:\n'+json.dumps(ans),'extra_top_level_contradiction':{**ans,'all_reported_facts_are_false':True}}
 if raw['id']=='scl_sv_stream_config':
  v=copy.deepcopy(ans);v['stream']['appid']='0x4000';probes['equivalent_hex_appid']=v
  v=copy.deepcopy(ans);v['stream']['appid']='0x0FA0';probes['wrong_hex_appid_same_decimal_digits']=v
 if raw['id']=='scl_breaker_control_binding':
  v=copy.deepcopy(ans);v['controlling_nodes'][0]['ln_inst']=True;probes['wrong_boolean_ln_instance']=v
 if raw['id']=='scl_goose_subscription_graph':
  v=copy.deepcopy(ans);v['subscriptions']=[r for r in v['subscriptions'] if not (r['subscriber']=='E03A103_' and r['publisher']=='E03A101_')]+[dict(subscriber='E03A103_',publisher='E03A101_',control_block='Control_DataSet',service='GOOSE',signal_count=n,src_ld=ld) for ld,n in [('UD1',4),('PROT',2)]];probes['distinct_source_ld_subscriptions']=v
 tests={}
 for name,obj in probes.items():
  text=json.dumps(obj) if isinstance(obj,dict) else obj;r=evaluate(t,text);tests[name]={'answer':obj,'success':r.success,'score':r.score,'details':[{'type':d.check_type,'passed':d.passed,'details':d.details} for d in r.details]}
 RESULT.append({'id':raw['id'],'path':str(p.relative_to(ROOT)),'independent_answer':ans,'fixture_evidence':evidence,'tests':tests})
(ROOT/'docs/bias_audit_v2/scl_check_results.json').write_text(json.dumps(RESULT,indent=2)+'\n')
print(json.dumps({'tasks':len(RESULT),'correct_failures':[r['id'] for r in RESULT if not r['tests']['independent_xml_answer']['success']],'omission_acceptances':[r['id'] for r in RESULT if r['tests']['omitted_required']['success']],'fabrication_acceptances':[r['id'] for r in RESULT if r['tests']['fabricated_entity_or_wrong_value']['success']],'negation_wrapper_passes':sum(r['tests']['negated_wrapped_json']['success'] for r in RESULT)},indent=2))
