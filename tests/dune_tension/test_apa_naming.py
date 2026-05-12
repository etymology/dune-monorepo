from hypothesis import given, strategies as st
import pytest

from dune_tension import apa_naming


_canonical_locations = st.sampled_from(apa_naming.LOCATIONS)
_canonical_numbers = st.integers(min_value=1, max_value=152)


@given(location=_canonical_locations, number=_canonical_numbers)
def test_compose_round_trips_through_parse(location, number):
    name = apa_naming.compose(location, number)
    assert name == f"APA-{location}-{number:03d}"
    assert apa_naming.parse(name) == (location, number)
    assert apa_naming.is_canonical(name)


@given(
    location=st.text().filter(lambda s: s not in apa_naming.LOCATIONS),
    number=_canonical_numbers,
)
def test_compose_rejects_unknown_location(location, number):
    with pytest.raises(ValueError):
        apa_naming.compose(location, number)


@given(
    location=_canonical_locations,
    number=st.integers().filter(lambda n: n not in apa_naming.NUMBERS),
)
def test_compose_rejects_out_of_range_number(location, number):
    with pytest.raises(ValueError):
        apa_naming.compose(location, number)


@given(name=st.text())
def test_parse_agrees_with_is_canonical(name):
    assert (apa_naming.parse(name) is not None) == apa_naming.is_canonical(name)


@pytest.mark.parametrize(
    "name",
    [
        "APA-DE-001",
        "apa-us-001",
        "APA-US-001 ",
        "APA-US-0001",
        "APA-US-153",
    ],
)
def test_parse_rejects_known_malformed_examples(name):
    assert apa_naming.parse(name) is None


def test_all_canonical_names_is_sorted_unique_and_complete():
    names = apa_naming.all_canonical_names()
    expected = len(apa_naming.LOCATIONS) * len(apa_naming.NUMBERS)
    assert len(names) == expected
    assert len(set(names)) == expected
    assert names == sorted(names)
    for name in names:
        assert apa_naming.is_canonical(name)
