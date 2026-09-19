#!/usr/bin/env python3
"""Run the prelocked norepinephrine challenge on pressure-matched Pulse states.

Per-run trajectories and logs remain in the ignored results/private tree.
The paired gate is evaluated on fresh no-drug runs before any challenged run starts.
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PULSE = Path(os.environ.get('PULSE_ROOT', '/tmp/pulse-checkpoint-restart'))
BIN = Path(os.environ.get('PULSE_BIN', '/tmp/pulse-checkpoint-install/bin'))
OUT = ROOT / 'results/pressure_matched_drug_response/private/paired_runs_v1'
BASES = ROOT / 'results/pressure_matched_routes_v2/private/cases'
STATE = ROOT / 'results/stage2/private/cache/StandardMale_stage2_baseline.json'
CONFIG = ROOT / 'config/pressure_matched_drug_response_v1.json'
TARGETS = {
    'mild': (1.300, .715),
    'intermediate': (1.715, .595),
    'higher': (1.985, .460),
}
METRICS = ['systolic_mmHg','diastolic_mmHg','map_mmHg','heart_rate_per_min',
           'cardiac_output_L_min','svr_mmHg_s_mL','LeftKidneyVasculature_inflow_mL_min',
           'RightKidneyVasculature_inflow_mL_min','BrainVasculature_inflow_mL_min',
           'baroreceptor_heart_rate_scale','baroreceptor_heart_elastance_scale',
           'baroreceptor_resistance_scale','baroreceptor_compliance_scale']


def init_engine(target, route, case):
    os.environ['PULSE_ROOT'] = str(PULSE)
    os.environ['PULSE_BIN'] = str(BIN)
    sys.path.insert(0, str(ROOT / 'scripts'))
    import run_stage6_bounds as stage6
    from pulse.cdm.patient import SEPatientConfiguration
    from pulse.cdm.patient_actions import SECardiovascularMechanicsModification
    from pulse.engine.PulseEngine import PulseEngine
    s = stage6.pulse_symbols()
    engine = PulseEngine(data_root_dir=str(BIN))
    engine.log_to_console(False)
    engine.set_log_filename(str(case / 'pulse.log'))
    if route == 'direct':
        patient = BASES / f'direct_{target}' / 'patient.json'
        pc = SEPatientConfiguration()
        pc.set_data_root_dir(str(BIN))
        pc.set_patient_file(str(patient))
        if not engine.initialize_engine(pc, stage6.requests(s)):
            raise RuntimeError(f'direct patient initialization failed: {patient}')
    else:
        if not engine.serialize_from_file(str(STATE), stage6.requests(s)):
            raise RuntimeError('could not load stock StandardMale checkpoint')
        r, c = TARGETS[target]
        action = SECardiovascularMechanicsModification()
        action.get_modifiers().get_systemic_resistance_multiplier().set_value(r)
        action.get_modifiers().get_arterial_compliance_multiplier().set_value(c)
        engine.process_action(action)
        if not engine.advance_time_s(.02):
            raise RuntimeError('Pulse stopped after mechanics modification')
    return engine, stage6


def run_child(target, route, phase):
    case = OUT / f'{target}_{route}_{phase}'
    case.mkdir(parents=True, exist_ok=True)
    engine, stage6 = init_engine(target, route, case)
    from pulse.cdm.patient_actions import SESubstanceInfusion
    from pulse.cdm.scalars import MassPerVolumeUnit, VolumePerTimeUnit, VolumeUnit
    rows, events = [], set()
    def advance_one(elapsed, phase_name):
        if not engine.advance_time_s(1.0):
            raise RuntimeError(f'Pulse stopped at {phase_name} {elapsed}s')
        active = engine.pull_active_events() or {}
        events.update(active.keys())
        row = dict(zip(stage6.COLUMNS, engine.pull_data().copy()))
        row.update(elapsed_s=elapsed, phase=phase_name)
        rows.append(row)
        return active
    for elapsed in range(1, 61):
        advance_one(elapsed, 'predrug')
    frame = pd.DataFrame(rows)
    base = frame[(frame.elapsed_s >= 30) & (frame.elapsed_s < 60)]
    med = {m: float(base[m].median()) for m in METRICS}
    st = frame[frame.elapsed_s > 48]
    bins=[]
    for i in range(4):
        part = st[(st.elapsed_s > 48 + 3*i) & (st.elapsed_s <= 51 + 3*i)]
        bins.append({m: float(part[m].median()) for m in ['systolic_mmHg','diastolic_mmHg']})
    stationarity = {m: max(x[m] for x in bins)-min(x[m] for x in bins)
                    for m in ['systolic_mmHg','diastolic_mmHg']}
    stationarity_pass = all(v <= .25 for v in stationarity.values())
    result = {'target':target,'route':route,'phase':phase,'baseline':med,
              'stationarity_ranges_mmHg':stationarity,'stationarity_pass':stationarity_pass,
              'active_events_predrug':sorted(events)}
    if phase == 'baseline':
        frame.to_csv(case/'baseline_trace.csv.gz',index=False,compression='gzip')
        result['preinfusion_completed']=True
    else:
        gate = json.loads((OUT/'paired_baseline_gate.json').read_text())
        pair = gate['pairs'][target]
        if not pair['pass']:
            raise RuntimeError(f'pair baseline gate failed before infusion: {pair}')
        if not stationarity_pass:
            raise RuntimeError('challenge-run pre-infusion state failed stationarity gate')
        peer = pair['screen_baselines']['modifier' if route=='direct' else 'direct']
        for m in ['systolic_mmHg','diastolic_mmHg']:
            if abs(med[m]-peer[m]) > .25:
                raise RuntimeError(f'challenge-run {m} missed peer baseline by >0.25 mmHg')
        cfg=json.loads(CONFIG.read_text())['drug_challenge']
        infusion=SESubstanceInfusion()
        infusion.set_comment('Predeclared pressure-matched drug response challenge')
        infusion.set_substance(cfg['substance'])
        infusion.get_concentration().set_value(cfg['concentration_ug_mL'],MassPerVolumeUnit.ug_Per_mL)
        infusion.get_rate().set_value(cfg['pulse_rate_mL_s'],VolumePerTimeUnit.mL_Per_s)
        infusion.get_volume().set_value(cfg['reservoir_volume_mL'],VolumeUnit.mL)
        engine.process_action(infusion)
        irreversible=False
        for elapsed in range(61,361):
            active=advance_one(elapsed,'infusion'); irreversible |= 'IrreversibleState' in active
            if irreversible: break
        infusion_completed = not irreversible and len(frame)+len(rows)-60 >= 360
        if infusion_completed:
            for elapsed in range(361,661):
                active=advance_one(elapsed,'post'); irreversible |= 'IrreversibleState' in active
                if irreversible: break
        allframe=pd.DataFrame(rows)
        allframe.to_csv(case/'challenge_trace.csv.gz',index=False,compression='gzip')
        result.update({'infusion_completed':infusion_completed,'post_observation_completed':not irreversible and len(rows)>=660,
          'irreversible_state':irreversible,'active_events':sorted(events),
          'dose_ug_kg_min':cfg['dose_ug_kg_min'],'concentration_ug_mL':cfg['concentration_ug_mL'],
          'rate_mL_s':cfg['pulse_rate_mL_s'],'infusion_duration_s':cfg['infusion_duration_s'],
          'administered_mass_ug':cfg['administered_mass_ug']})
        # Response metrics are 10-second rolling medians against the final 30s predrug median.
        trace=allframe
        for m in METRICS:
            roll=trace[m].rolling(10,min_periods=10).median()
            delta=roll-med[m]
            result.setdefault('response',{})[m]={'max_delta':float(delta.max()),'min_delta':float(delta.min()),
              'max_abs_delta':float(delta.abs().max()),'end_of_infusion_delta':float(delta[trace.elapsed_s==360].iloc[-1]) if (trace.elapsed_s==360).any() else None,
              'end_of_post_delta':float(delta[trace.elapsed_s==660].iloc[-1]) if (trace.elapsed_s==660).any() else None}
    (case/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


def launch(target,route,phase):
    cmd=[sys.executable,str(Path(__file__).resolve()),'--child','--target',target,'--route',route,'--phase',phase]
    env=os.environ.copy(); env['PULSE_ROOT']=str(PULSE); env['PULSE_BIN']=str(BIN)
    pyroots=['/tmp/pulse-checkpoint-install/python','/tmp/pulse-checkpoint-install/bin']
    env['PYTHONPATH']=os.pathsep.join(pyroots + ([env['PYTHONPATH']] if env.get('PYTHONPATH') else []))
    env['LD_LIBRARY_PATH']=str(BIN) + (os.pathsep + env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
    p=subprocess.run(cmd,text=True,capture_output=True,env=env)
    if p.returncode:
        raise RuntimeError(f'{target}/{route}/{phase} failed\n{p.stdout}\n{p.stderr}')
    return json.loads(p.stdout.strip().splitlines()[-1])


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    ap=argparse.ArgumentParser(); ap.add_argument('--child',action='store_true'); ap.add_argument('--target'); ap.add_argument('--route'); ap.add_argument('--phase'); a=ap.parse_args()
    if a.child:
        run_child(a.target,a.route,a.phase); return
    pulse_sha=subprocess.check_output(['git','-C',str(PULSE),'rev-parse','HEAD'],text=True).strip()
    if pulse_sha != json.loads(CONFIG.read_text())['pulse_revision']:
        raise RuntimeError(f'Pulse SHA mismatch: {pulse_sha}')
    screened={}
    for target in TARGETS:
        screened[target]={}
        for route in ['direct','modifier']:
            print(f'Baseline screen: {target} {route}',flush=True)
            screened[target][route]=launch(target,route,'baseline')
    pairs={}
    for target, states in screened.items():
        d,m=states['direct'],states['modifier']
        ds=d['baseline']['systolic_mmHg']-m['baseline']['systolic_mmHg']
        dd=d['baseline']['diastolic_mmHg']-m['baseline']['diastolic_mmHg']
        pairs[target]={'direct_modifier_sbp_difference_mmHg':ds,'direct_modifier_dbp_difference_mmHg':dd,
          'stationarity_pass':d['stationarity_pass'] and m['stationarity_pass'],
          'screen_baselines':{'direct':d['baseline'],'modifier':m['baseline']},
          'pass':abs(ds)<=.25 and abs(dd)<=.25 and d['stationarity_pass'] and m['stationarity_pass']}
    gate={'pulse_revision':pulse_sha,'stage0_sha256':json.loads(CONFIG.read_text())['stage0_sha256'],
          'baseline_window':'30 <= elapsed_s < 60','pairs':pairs,'all_pairs_pass':all(p['pass'] for p in pairs.values())}
    (OUT/'paired_baseline_gate.json').write_text(json.dumps(gate,indent=2)+'\n')
    print(json.dumps(gate,indent=2),flush=True)
    if not gate['all_pairs_pass']:
        print('At least one pair failed; no drug challenges were run.',flush=True); return
    summaries=[]
    for target in TARGETS:
        for route in ['direct','modifier']:
            print(f'Drug challenge: {target} {route}',flush=True)
            summaries.append(launch(target,route,'challenge'))
    (OUT/'paired_run_summaries.json').write_text(json.dumps(summaries,indent=2)+'\n')

if __name__=='__main__':
    main()
