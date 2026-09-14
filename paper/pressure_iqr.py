import os

import numpy as np
import pandas as pd

def _env(name):
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f'Set {name}; see README (Data access).')
    return value

haalsi = pd.read_csv(
    _env('HTN_HAALSI_TAB'),
    sep='\t', usecols=['c_bs_mean_sys', 'c_bs_mean_dia'], low_memory=False)
h = haalsi.dropna()
h['pp'] = h['c_bs_mean_sys'] - h['c_bs_mean_dia']

elsa = pd.read_csv(
    os.path.join(_env('HTN_ELSA_TAB_DIR'), 'wave_8_elsa_nurse_data_eul_v1.tab'),
    sep='\t', usecols=['bprespc', 'sysval', 'diaval'], low_memory=False)
valid = (elsa['bprespc'] == 1) & (elsa['sysval'] > 0) & (elsa['diaval'] > 0)
e = elsa.loc[valid].copy()
e['pp'] = e['sysval'] - e['diaval']

for name, df, s, d in (('HAALSI', h, 'c_bs_mean_sys', 'c_bs_mean_dia'),
                       ('ELSA', e, 'sysval', 'diaval')):
    for col, label in ((s, 'SBP'), (d, 'DBP'), ('pp', 'PP')):
        q1, q3 = np.nanpercentile(df[col], [25, 75])
        print(f"{name} {label}: median {np.nanmedian(df[col]):.1f}, "
              f"IQR {q1:.1f}--{q3:.1f}")
