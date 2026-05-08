from realm.rng import make_rng


def test_rng_deterministic_per_tick_and_purpose() -> None:
    a = make_rng(10, "survey_noise")
    b = make_rng(10, "survey_noise")
    assert a.random() == b.random()
    assert a.random() == b.random()


def test_different_purpose_splits_stream() -> None:
    a = make_rng(5, "a")
    b = make_rng(5, "b")
    assert a.random() != b.random()
