from generate_exercise_recovery_ensemble import (
    CONDITIONING_SIGMA_BPM,
    DELAYS_S,
    DURATIONS_S,
    INTENSITIES,
    candidate_specs,
)


def test_frozen_candidate_grid_is_72_equal_factorial_members():
    specs = candidate_specs()
    assert len(specs) == 72
    assert {item["exercise_intensity"] for item in specs} == set(INTENSITIES)
    assert {item["exercise_duration_s"] for item in specs} == set(DURATIONS_S)
    assert {item["cessation_to_recovery_origin_delay_s"] for item in specs} == set(DELAYS_S)
    assert len({item["candidate_id"] for item in specs}) == 72
    assert CONDITIONING_SIGMA_BPM == 10.0
