import pytest

from dune_tension import apa_naming


def test_compose_returns_canonical_form():
    assert apa_naming.compose("US", 1) == "APA-US-001"
    assert apa_naming.compose("UK", 152) == "APA-UK-152"
    assert apa_naming.compose("US", 12) == "APA-US-012"


@pytest.mark.parametrize("location", ["us", "uk", "DE", "", "USA"])
def test_compose_rejects_unknown_location(location):
    with pytest.raises(ValueError):
        apa_naming.compose(location, 1)


@pytest.mark.parametrize("number", [0, -1, 153, 1000])
def test_compose_rejects_out_of_range_number(number):
    with pytest.raises(ValueError):
        apa_naming.compose("US", number)


def test_parse_round_trips_for_every_canonical_name():
    for name in apa_naming.all_canonical_names():
        parsed = apa_naming.parse(name)
        assert parsed is not None
        location, number = parsed
        assert apa_naming.compose(location, number) == name


@pytest.mark.parametrize(
    "name",
    [
        "USAPA12",
        "UKAPA7",
        "APA-US-1",
        "APA-US-153",
        "APA-DE-001",
        "apa-us-001",
        "APA-US-001 ",
        " APA-US-001",
        "APA-US-001\n",
        "",
        "APA-US-00",
        "APA-US-0001",
    ],
)
def test_parse_rejects_malformed_input(name):
    assert apa_naming.parse(name) is None
    assert not apa_naming.is_canonical(name)


def test_all_canonical_names_has_304_unique_sorted_entries():
    names = apa_naming.all_canonical_names()
    assert len(names) == 304
    assert len(set(names)) == 304
    assert names == sorted(names)
