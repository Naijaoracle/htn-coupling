"""Compute cohort characteristics table + n-at-risk counts for the revisions."""
from pathlib import Path
import numpy as np
import pandas as pd

import os


def _env_dir(name):
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Set {name}; see README (Data access).")
    return Path(value)


HAALSI_TAB = _env_dir("HTN_HAALSI_TAB")
ELSA_TAB_DIR = _env_dir("HTN_ELSA_TAB_DIR")

def q50(x):
    return float(np.nanmedian(x))

def iqr(x):
    q1, q3 = np.nanpercentile(x, [25, 75])
    return float(q1), float(q3)

# HAALSI
haalsi = pd.read_csv(HAALSI_TAB,
                     sep="\t",
                     usecols=["rage", "rsex", "c_bs_mean_sys", "c_bs_mean_dia",
                              "c_bs_bmi"],
                     low_memory=False)
h = haalsi.dropna(subset=["c_bs_mean_sys", "c_bs_mean_dia"]).copy()
h["pp"] = h["c_bs_mean_sys"] - h["c_bs_mean_dia"]

# ELSA: nurse + harmonized join (as in stage 1)
nurse = pd.read_csv(ELSA_TAB_DIR / "wave_8_elsa_nurse_data_eul_v1.tab",
                    sep="\t",
                    usecols=["idauniq", "indsex", "bprespc", "sysval", "diaval"],
                    low_memory=False)
harm = pd.read_csv(ELSA_TAB_DIR / "gh_elsa_h.tab", sep="\t",
                   usecols=["idauniq", "r8agey", "r8mbmi"], low_memory=False)
harm["r8agey"] = pd.to_numeric(harm["r8agey"], errors="coerce")
harm["r8mbmi"] = pd.to_numeric(harm["r8mbmi"], errors="coerce")
e = nurse.merge(harm, on="idauniq", how="left", validate="one_to_one")
valid = (e["bprespc"] == 1) & (e["sysval"] > 0) & (e["diaval"] > 0)
e = e.loc[valid].copy()
e["pp"] = e["sysval"] - e["diaval"]

def row(name, df, age_c, sex_c, sbp_c, dbp_c, pp_c, bmi_c):
    n = len(df)
    a1, a3 = iqr(df[age_c])
    b1, b3 = iqr(df[bmi_c]) if bmi_c else (float("nan"), float("nan"))
    pct_f = 100 * (df[sex_c] == 2).mean()
    return {
        "cohort": name, "n": n,
        "age_median": round(q50(df[age_c]), 1),
        "age_iqr": f"{a1:.1f}--{a3:.1f}",
        "female_pct": round(pct_f, 1),
        "sbp_median": round(q50(df[sbp_c]), 1),
        "dbp_median": round(q50(df[dbp_c]), 1),
        "pp_median": round(q50(df[pp_c]), 1),
        "bmi_median": round(q50(df[bmi_c]), 1),
        "bmi_iqr": f"{b1:.1f}--{b3:.1f}",
    }

rows = [
    row("HAALSI Wave 1 (valid pressure)", h, "rage", "rsex",
        "c_bs_mean_sys", "c_bs_mean_dia", "pp", "c_bs_bmi"),
    row("ELSA Wave 8 (valid pressure)", e, "r8agey", "indsex",
        "sysval", "diaval", "pp", "r8mbmi"),
]
out = pd.DataFrame(rows)
print(out.to_string(index=False))
out.to_csv(Path(__file__).resolve().parent / "cohort_characteristics.csv",
           index=False)

# n-at-risk for Figure 4
ACUTE = _env_dir("HTN_RESULTS") / "stage5" / "private" / "acute"
import glob
ORDER = ["normotensive", "resistance_dominant", "compliance_dominant", "combined"]
LABEL = {"normotensive": "Norm", "resistance_dominant": "Res",
         "compliance_dominant": "Comp", "combined": "Comb"}
counts = {p: {} for p in ORDER}
files = sorted(glob.glob(str(ACUTE / "expanded_*__*.csv.gz")))
for f in files:
    name = Path(f).name.replace(".csv.gz", "").split("__")
    p = name[1]
    if p not in ORDER:
        continue
    d = pd.read_csv(f, usecols=["time_s"])
    last = float(d["time_s"].max())
    for t in (300, 600, 900):
        counts[p][t] = counts[p].get(t, 0) + (1 if last >= t else 0)
print("\nn active at 300/600/900 s:")
for p in ORDER:
    print(f"  {p:22s} " + " / ".join(f"{counts[p][t]}" for t in (300, 600, 900)))
