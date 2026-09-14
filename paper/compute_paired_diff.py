import csv
import os
import statistics as st
from pathlib import Path

_r = os.environ.get('HTN_RESULTS')
if not _r:
    raise SystemExit('Set HTN_RESULTS; see README (Data access).')
RESULTS = Path(_r)

rows = list(csv.DictReader(open(
    RESULTS / 'stage5_followup' / 'expanded_acute_fractional_endpoints.csv')))
norm = {r['body_id']: float(r['time_to_30pct_map_fall_s'])
        for r in rows if r['phenotype'] == 'normotensive'}
for p in ['resistance_dominant', 'compliance_dominant', 'combined']:
    d = [float(r['time_to_30pct_map_fall_s']) - norm[r['body_id']]
         for r in rows if r['phenotype'] == p]
    q = st.quantiles(d, n=4)
    print(p,
          'median', round(st.median(d), 1),
          'iqr', round(q[0], 1), 'to', round(q[2], 1),
          'range', round(min(d), 1), 'to', round(max(d), 1))
