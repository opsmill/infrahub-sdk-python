from infrahub_sdk.spec.range_expansion import range_expansion


def test_number_range_expansion() -> None:
    assert range_expansion("Device[1-3]") == ["Device1", "Device2", "Device3"]
    assert range_expansion("FastEthernet[1-2]/0/[10-12]") == [
        "FastEthernet1/0/10",
        "FastEthernet1/0/11",
        "FastEthernet1/0/12",
        "FastEthernet2/0/10",
        "FastEthernet2/0/11",
        "FastEthernet2/0/12",
    ]


def test_letter_range_expansion() -> None:
    assert range_expansion("Device [A-C]") == ["Device A", "Device B", "Device C"]
    assert range_expansion("GigabitEthernet[a-c]/0/1") == [
        "GigabitEtherneta/0/1",
        "GigabitEthernetb/0/1",
        "GigabitEthernetc/0/1",
    ]
    assert range_expansion("Eth[a,c,e]/0/1") == [
        "Etha/0/1",
        "Ethc/0/1",
        "Ethe/0/1",
    ]


def test_mixed_range_expansion() -> None:
    assert range_expansion("Device[1-2,A-C]") == [
        "Device1",
        "Device2",
        "DeviceA",
        "DeviceB",
        "DeviceC",
    ]
    assert range_expansion("Interface[1-2,a-c]/0/[10-11,x,z]") == [
        "Interface1/0/10",
        "Interface1/0/11",
        "Interface1/0/x",
        "Interface1/0/z",
        "Interface2/0/10",
        "Interface2/0/11",
        "Interface2/0/x",
        "Interface2/0/z",
        "Interfacea/0/10",
        "Interfacea/0/11",
        "Interfacea/0/x",
        "Interfacea/0/z",
        "Interfaceb/0/10",
        "Interfaceb/0/11",
        "Interfaceb/0/x",
        "Interfaceb/0/z",
        "Interfacec/0/10",
        "Interfacec/0/11",
        "Interfacec/0/x",
        "Interfacec/0/z",
    ]


def test_single_value_in_brackets() -> None:
    assert range_expansion("Device[5]") == ["Device[5]"]


def test_empty_brackets() -> None:
    assert range_expansion("Device[]") == ["Device[]"]


def test_no_brackets() -> None:
    assert range_expansion("Device1") == ["Device1"]


def test_malformed_ranges() -> None:
    assert range_expansion("Device[1-]") == ["Device[1-]"]
    assert range_expansion("Device[-3]") == ["Device[-3]"]
    assert range_expansion("Device[a-]") == ["Device[a-]"]
    assert range_expansion("Device[1-3,]") == ["Device[1-3,]"]


def test_duplicate_and_overlapping_values() -> None:
    assert range_expansion("Device[1,1,2]") == ["Device1", "Device1", "Device2"]


def test_descending_ranges() -> None:
    assert range_expansion("Device[3-1]") == ["Device3", "Device2", "Device1"]


def test_multiple_bracketed_ranges_in_a_row() -> None:
    assert range_expansion("Dev[A-B][1-2]") == ["DevA1", "DevA2", "DevB1", "DevB2"]


def test_non_alphanumeric_ranges() -> None:
    assert range_expansion("Port[!@#]") == ["Port[!@#]"]


def test_unicode_ranges() -> None:
    assert range_expansion("Dev[α-γ]") == ["Devα", "Devβ", "Devγ"]  # noqa: RUF001


def test_brackets_in_strings() -> None:
    assert range_expansion(r"Service Object [Circuit Provider, X]") == ["Service Object [Circuit Provider, X]"]


def test_words_in_brackets() -> None:
    assert range_expansion("Device[expansion]") == ["Device[expansion]"]
