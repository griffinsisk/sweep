from sweep.presets import PRESET_INDEX, PRESETS


def test_preset_keys_unique():
    assert len(PRESET_INDEX) == len(PRESETS)


def test_every_preset_has_a_query():
    for p in PRESETS:
        assert p.query.strip()
        assert p.key == p.key.lower()
