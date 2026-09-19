#!/usr/bin/env python3
"""Focused sodium/volume diagnostic for the intermediate matched pair.

All run traces are private. The optional fourfold concentration run preserves
concentration*rate (drug mass input) and is a dose-encoding sensitivity; Pulse
revision 99e2d50 does not model carrier fluid addition.
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
PULSE=Path(os.environ.get('PULSE_ROOT','/tmp/pulse-checkpoint-restart'))
BIN=Path(os.environ.get('PULSE_BIN','/tmp/pulse-checkpoint-install/bin'))
OUT=ROOT/'results/pressure_matched_drug_response/private/hypernatremia_diagnostic_v2'
BASES=ROOT/'results/pressure_matched_routes_v2/private/cases'
STATE=ROOT/'results/stage2/private/cache/StandardMale_stage2_baseline.json'
CONFIG=ROOT/'config/pressure_matched_drug_response_v1.json'
R,C=1.715,.595


def get_engine(route, case):
    os.environ['PULSE_ROOT']=str(PULSE);os.environ['PULSE_BIN']=str(BIN)
    sys.path.insert(0,str(ROOT/'scripts'))
    import run_stage6_bounds as stage6
    from pulse.cdm.engine import SEDataRequestManager,SEDataRequest
    from pulse.cdm.patient import SEPatientConfiguration
    from pulse.cdm.patient_actions import SECardiovascularMechanicsModification
    from pulse.cdm.scalars import (AmountPerVolumeUnit,MassPerVolumeUnit,OsmolalityUnit,
                                   VolumePerTimeUnit,VolumeUnit)
    from pulse.engine.PulseEngine import PulseEngine
    base=stage6.requests(stage6.pulse_symbols()).get_data_requests()
    extra=[
      SEDataRequest.create_physiology_request('BloodVolume',VolumeUnit.mL),
      SEDataRequest.create_physiology_request('UrineProductionRate',VolumePerTimeUnit.mL_Per_min),
      SEDataRequest.create_physiology_request('UrineOsmolality',OsmolalityUnit.mOsm_Per_kg),
      SEDataRequest.create_physiology_request('RenalPlasmaFlow',VolumePerTimeUnit.mL_Per_min),
      SEDataRequest.create_liquid_compartment_request('LeftUreter','InFlow',VolumePerTimeUnit.mL_Per_min),
      SEDataRequest.create_liquid_compartment_request('RightUreter','InFlow',VolumePerTimeUnit.mL_Per_min),
      SEDataRequest.create_liquid_compartment_substance_request('LeftUreter','Sodium','Concentration',MassPerVolumeUnit.mg_Per_mL),
      SEDataRequest.create_liquid_compartment_substance_request('RightUreter','Sodium','Concentration',MassPerVolumeUnit.mg_Per_mL),
      SEDataRequest.create_liquid_compartment_substance_request('Aorta','Sodium','Molarity',AmountPerVolumeUnit.mEq_Per_L),
      SEDataRequest.create_liquid_compartment_substance_request('Aorta','Sodium','Concentration',MassPerVolumeUnit.mg_Per_mL),
    ]
    requests=SEDataRequestManager(base+extra)
    engine=PulseEngine(data_root_dir=str(BIN));engine.log_to_console(False);engine.set_log_filename(str(case/'pulse.log'))
    if route=='direct':
      pc=SEPatientConfiguration();pc.set_data_root_dir(str(BIN));pc.set_patient_file(str(BASES/'direct_intermediate'/'patient.json'))
      if not engine.initialize_engine(pc,requests):raise RuntimeError('direct patient initialization failed')
    else:
      if not engine.serialize_from_file(str(STATE),requests):raise RuntimeError('could not load StandardMale checkpoint')
      action=SECardiovascularMechanicsModification();action.get_modifiers().get_systemic_resistance_multiplier().set_value(R);action.get_modifiers().get_arterial_compliance_multiplier().set_value(C)
      engine.process_action(action)
      if not engine.advance_time_s(.02):raise RuntimeError('Pulse stopped after mechanics modification')
    cols=stage6.COLUMNS+['blood_volume_mL','urine_production_mL_min','urine_osmolality_mOsm_kg','renal_plasma_flow_mL_min','left_ureter_flow_mL_min','right_ureter_flow_mL_min','left_ureter_sodium_mg_mL','right_ureter_sodium_mg_mL','aortic_sodium_mEq_L','aortic_sodium_mg_mL']
    return engine,cols


def run_one(route,phase,conc):
    case=OUT/f'intermediate_{route}_{phase}_c{conc:g}'
    case.mkdir(parents=True,exist_ok=True)
    engine,cols=get_engine(route,case)
    from pulse.cdm.patient_actions import SESubstanceInfusion
    from pulse.cdm.scalars import MassPerVolumeUnit,VolumePerTimeUnit,VolumeUnit
    cfg=json.loads(CONFIG.read_text())['drug_challenge']; rate=cfg['pulse_rate_mL_s']/conc
    rows=[];events={};
    def step(t,label):
      if not engine.advance_time_s(1.0):raise RuntimeError(f'Pulse stopped at {label} second {t}')
      active=engine.pull_active_events() or {}
      for name,value in active.items():
        if value and name not in events:events[name]=t
      vals=engine.pull_data().copy()
      row=dict(zip(cols,vals));row.update(elapsed_s=t,phase=label);rows.append(row)
      for key in ['blood_volume_mL','urine_production_mL_min','urine_osmolality_mOsm_kg','aortic_sodium_mEq_L','aortic_sodium_mg_mL','renal_plasma_flow_mL_min','left_ureter_flow_mL_min','right_ureter_flow_mL_min','left_ureter_sodium_mg_mL','right_ureter_sodium_mg_mL']:
        if pd.isna(row[key]):raise RuntimeError(f'diagnostic request {key} returned NaN before drug')
      return active
    for t in range(1,61):step(t,'predrug')
    f=pd.DataFrame(rows);base=f[(f.elapsed_s>=30)&(f.elapsed_s<60)]
    sodium_check=float(base.aortic_sodium_mEq_L.median())
    if not 135.0 <= sodium_check <= 150.0:raise RuntimeError(f'aortic sodium request mapping implausible: {sodium_check} mEq/L')
    if phase=='baseline':
      f.to_csv(case/'trace.csv.gz',index=False,compression='gzip')
      out={'route':route,'phase':phase,'concentration_ug_mL':None,'baseline_window':'30<=t<60','baseline':{k:float(base[k].median()) for k in ['systolic_mmHg','diastolic_mmHg','map_mmHg','aortic_sodium_mEq_L','aortic_sodium_mg_mL','blood_volume_mL','urine_production_mL_min','urine_osmolality_mOsm_kg','renal_plasma_flow_mL_min','left_ureter_flow_mL_min','right_ureter_flow_mL_min','left_ureter_sodium_mg_mL','right_ureter_sodium_mg_mL']},'events_first_observed_elapsed_s':events}
    else:
      gate=json.loads((OUT/'intermediate_baseline_gate.json').read_text())
      if not gate['pass']:raise RuntimeError(f'intermediate no-drug pressure gate failed: {gate}')
      prior=json.loads((OUT/f'intermediate_{route}_baseline_c1/summary.json').read_text())
      current={k:float(base[k].median()) for k in ['systolic_mmHg','diastolic_mmHg','aortic_sodium_mEq_L','blood_volume_mL','urine_production_mL_min','urine_osmolality_mOsm_kg','renal_plasma_flow_mL_min','left_ureter_flow_mL_min','right_ureter_flow_mL_min','left_ureter_sodium_mg_mL','right_ureter_sodium_mg_mL']}
      for k in ['systolic_mmHg','diastolic_mmHg']:
        if abs(current[k]-prior['baseline'][k])>.25:raise RuntimeError(f'{route} challenge {k} drifted >0.25 from screening baseline')
      inf=SESubstanceInfusion();inf.set_comment('Fixed-mass norepinephrine volume/concentration sensitivity');inf.set_substance('Norepinephrine');inf.get_concentration().set_value(conc,MassPerVolumeUnit.ug_Per_mL);inf.get_rate().set_value(rate,VolumePerTimeUnit.mL_Per_s);inf.get_volume().set_value(rate*(300+.02),VolumeUnit.mL);engine.process_action(inf)
      irr=False
      for t in range(61,661):
        active=step(t,'infusion' if t<=360 else 'post')
        irr |= 'IrreversibleState' in active
        if irr:break
      f=pd.DataFrame(rows);f.to_csv(case/'trace.csv.gz',index=False,compression='gzip')
      out={'route':route,'phase':phase,'concentration_ug_mL':conc,'rate_mL_s':rate,'mass_rate_ug_s':rate*conc,'nominal_volume_equivalent_mL':rate*300,'administered_mass_ug':rate*conc*300,'baseline_window':'30<=t<60','baseline':current,'events_first_observed_elapsed_s':events,'irreversible_state':irr,'full_660s_completed':len(f)==660,'sodium_min_mEq_L':float(f.aortic_sodium_mEq_L.min()),'sodium_max_mEq_L':float(f.aortic_sodium_mEq_L.max()),'sodium_at_60s_mEq_L':float(f.loc[f.elapsed_s==60,'aortic_sodium_mEq_L'].iloc[0]),'blood_volume_change_at_360_mL':float(f.loc[f.elapsed_s==360,'blood_volume_mL'].iloc[0]-current['blood_volume_mL']),'urine_rate_min_mL_min':float(f.urine_production_mL_min.min()),'urine_rate_max_mL_min':float(f.urine_production_mL_min.max()),'urine_osmolality_min_mOsm_kg':float(f.urine_osmolality_mOsm_kg.min()),'urine_osmolality_max_mOsm_kg':float(f.urine_osmolality_mOsm_kg.max()),'renal_plasma_flow_min_mL_min':float(f.renal_plasma_flow_mL_min.min()),'renal_plasma_flow_max_mL_min':float(f.renal_plasma_flow_mL_min.max()),'left_ureter_sodium_max_mg_mL':float(f.left_ureter_sodium_mg_mL.max()),'right_ureter_sodium_max_mg_mL':float(f.right_ureter_sodium_mg_mL.max()),'urinary_sodium_mass_rate_max_mg_min':float((f.left_ureter_flow_mL_min*f.left_ureter_sodium_mg_mL+f.right_ureter_flow_mL_min*f.right_ureter_sodium_mg_mL).max())}
    (case/'summary.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))


def launch(route,phase,conc):
    env=os.environ.copy();env['PULSE_ROOT']=str(PULSE);env['PULSE_BIN']=str(BIN)
    roots=['/tmp/pulse-checkpoint-install/python','/tmp/pulse-checkpoint-install/bin'];env['PYTHONPATH']=os.pathsep.join(roots+([env['PYTHONPATH']] if env.get('PYTHONPATH') else []));env['LD_LIBRARY_PATH']=str(BIN)+(os.pathsep+env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
    cmd=[sys.executable,str(Path(__file__).resolve()),'--child','--route',route,'--phase',phase,'--concentration',str(conc)]
    p=subprocess.run(cmd,text=True,capture_output=True,env=env)
    if p.returncode:raise RuntimeError(f'{route}/{phase}/c{conc} failed\n{p.stdout}\n{p.stderr}')
    return json.loads(p.stdout.strip().splitlines()[-1])


def main():
    OUT.mkdir(parents=True,exist_ok=True);a=argparse.ArgumentParser();a.add_argument('--child',action='store_true');a.add_argument('--route',choices=['direct','modifier']);a.add_argument('--phase',choices=['baseline','challenge']);a.add_argument('--concentration',type=float,default=1.0);a.add_argument('--baseline-only',action='store_true');a.add_argument('--challenges-only',action='store_true');x=a.parse_args()
    if x.child:run_one(x.route,x.phase,x.concentration);return
    pulse=subprocess.check_output(['git','-C',str(PULSE),'rev-parse','HEAD'],text=True).strip()
    if pulse!=json.loads(CONFIG.read_text())['pulse_revision']:raise RuntimeError(f'Pulse revision mismatch: {pulse}')
    if x.challenges_only:
      gate=json.loads((OUT/'intermediate_baseline_gate.json').read_text())
      if not gate['pass']:raise RuntimeError('existing no-drug pair gate failed')
    else:
      screen={}
      for route in ['direct','modifier']:
        print('no-drug diagnostic baseline:',route,flush=True);screen[route]=launch(route,'baseline',1.0)
      d,m=screen['direct']['baseline'],screen['modifier']['baseline']
      gate={'pulse_revision':pulse,'direct_modifier_sbp_difference_mmHg':d['systolic_mmHg']-m['systolic_mmHg'],'direct_modifier_dbp_difference_mmHg':d['diastolic_mmHg']-m['diastolic_mmHg'],'pass':abs(d['systolic_mmHg']-m['systolic_mmHg'])<=.25 and abs(d['diastolic_mmHg']-m['diastolic_mmHg'])<=.25,'direct_baseline':d,'modifier_baseline':m,'modifier_minus_direct_sodium_mEq_L':m['aortic_sodium_mEq_L']-d['aortic_sodium_mEq_L'],'modifier_minus_direct_blood_volume_mL':m['blood_volume_mL']-d['blood_volume_mL'],'modifier_minus_direct_urine_production_mL_min':m['urine_production_mL_min']-d['urine_production_mL_min']}
      (OUT/'intermediate_baseline_gate.json').write_text(json.dumps(gate,indent=2)+'\n');print(json.dumps(gate,indent=2),flush=True)
      if x.baseline_only:return
      if not gate['pass']:print('Pressure match failed; no diagnostic infusion runs executed.');return
    summaries=[]
    for conc in [1.0,4.0]:
      for route in ['direct','modifier']:
        print(f'challenge diagnostic: concentration={conc:g} µg/mL route={route}',flush=True);summaries.append(launch(route,'challenge',conc))
    (OUT/'diagnostic_summary.json').write_text(json.dumps(summaries,indent=2)+'\n')

if __name__=='__main__':main()
