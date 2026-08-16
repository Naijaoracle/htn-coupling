"""Single source of unit conversions used by the Pulse-to-openBF bridge."""

MMHG_TO_PA = 133.322
ML_TO_M3 = 1e-6
MIN_TO_S = 60.0


def ml_per_s_to_m3_per_s(value):
    return value * ML_TO_M3


def m3_per_s_to_ml_per_s(value):
    return value / ML_TO_M3


def mmhg_to_pa(value):
    return value * MMHG_TO_PA


def pa_to_mmhg(value):
    return value / MMHG_TO_PA


def l_per_min_to_m3_per_s(value):
    return value * 1e-3 / MIN_TO_S


def mmhg_s_per_ml_to_pa_s_per_m3(value):
    return value * MMHG_TO_PA / ML_TO_M3


def pa_s_per_m3_to_mmhg_s_per_ml(value):
    return value / MMHG_TO_PA * ML_TO_M3
