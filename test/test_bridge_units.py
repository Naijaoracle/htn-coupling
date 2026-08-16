import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bridge_units as u


def test_flow_conversion_round_trip():
    assert math.isclose(u.m3_per_s_to_ml_per_s(u.ml_per_s_to_m3_per_s(97.25)), 97.25)


def test_pressure_conversion_reference():
    assert math.isclose(u.mmhg_to_pa(100.0), 13332.2)
    assert math.isclose(u.pa_to_mmhg(13332.2), 100.0)


def test_cardiac_output_conversion():
    assert math.isclose(u.l_per_min_to_m3_per_s(6.0), 1e-4)


def test_resistance_conversion_round_trip():
    value = 0.9394
    si = u.mmhg_s_per_ml_to_pa_s_per_m3(value)
    assert math.isclose(si, 125242686.8)
    assert math.isclose(u.pa_s_per_m3_to_mmhg_s_per_ml(si), value)
