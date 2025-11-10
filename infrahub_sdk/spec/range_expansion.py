import itertools
import re

MATCH_PATTERN = r"(\[[\w,-]*[-,][\w,-]*\])"


def _escape_brackets(s: str) -> str:
    return s.replace("\\[", "__LBRACK__").replace("\\]", "__RBRACK__")


def _unescape_brackets(s: str) -> str:
    return s.replace("__LBRACK__", "[").replace("__RBRACK__", "]")


def _char_range_expand(char_range_str: str) -> list[str]:
    """Expands a string of numbers or single-character letters."""
    expanded_values: list[str] = []
    # Special case: if no dash and no comma, and multiple characters, error if not all alphanumeric
    if "," not in char_range_str and "-" not in char_range_str and len(char_range_str) > 1:
        if not char_range_str.isalnum():
            raise ValueError(f"Invalid non-alphanumeric range: [{char_range_str}]")
        return list(char_range_str)

    for value in char_range_str.split(","):
        if not value:
            # Malformed: empty part in comma-separated list
            return [f"[{char_range_str}]"]
        if "-" in value:
            start_char, end_char = value.split("-", 1)
            if not start_char or not end_char:
                expanded_values.append(f"[{char_range_str}]")
                return expanded_values
            # Check if it's a numeric range
            if start_char.isdigit() and end_char.isdigit():
                start_num = int(start_char)
                end_num = int(end_char)
                step = 1 if start_num <= end_num else -1
                expanded_values.extend(str(i) for i in range(start_num, end_num + step, step))
            # Check if it's an alphabetical range (single character)
            elif len(start_char) == 1 and len(end_char) == 1 and start_char.isalpha() and end_char.isalpha():
                start_ord = ord(start_char)
                end_ord = ord(end_char)
                step = 1 if start_ord <= end_ord else -1
                is_upper = start_char.isupper()
                for i in range(start_ord, end_ord + step, step):
                    char = chr(i)
                    expanded_values.append(char.upper() if is_upper else char)
            else:
                # Mixed or unsupported range type, append as-is
                expanded_values.append(value)
        else:
            # If the value is a single character or valid alphanumeric string, append
            if not value.isalnum():
                raise ValueError(f"Invalid non-alphanumeric value: [{value}]")
            expanded_values.append(value)
    return expanded_values


def _extract_constants(pattern: str, re_compiled: re.Pattern) -> tuple[list[int], list[list[str]]]:
    cartesian_list = []
    interface_constant = [0]
    for match in re_compiled.finditer(pattern):
        interface_constant.append(match.start())
        interface_constant.append(match.end())
        cartesian_list.append(_char_range_expand(match.group()[1:-1]))
    return interface_constant, cartesian_list


def _expand_interfaces(pattern: str, interface_constant: list[int], cartesian_list: list[list[str]]) -> list[str]:
    def _pairwise(lst: list[int]) -> list[tuple[int, int]]:
        it = iter(lst)
        return list(zip(it, it))

    if interface_constant[-1] < len(pattern):
        interface_constant.append(len(pattern))
    interface_constant_out = _pairwise(interface_constant)
    expanded_interfaces = []
    for element in itertools.product(*cartesian_list):
        current_interface = ""
        for count, item in enumerate(interface_constant_out):
            current_interface += pattern[item[0] : item[1]]
            if count < len(element):
                current_interface += element[count]
        expanded_interfaces.append(_unescape_brackets(current_interface))
    return expanded_interfaces


def range_expansion(interface_pattern: str) -> list[str]:
    """Expand string pattern into a list of strings, supporting both
    number and single-character alphabet ranges. Heavily inspired by
    Netutils interface_range_expansion but adapted to support letters.

    Args:
        interface_pattern: The string pattern that will be parsed to create the list of interfaces.

    Returns:
        Contains the expanded list of interfaces.

    Examples:
        >>> from infrahub_sdk.spec.range_expansion import range_expansion
        >>> range_expansion("Device [A-C]")
        ['Device A', 'Device B', 'Device C']
        >>> range_expansion("FastEthernet[1-2]/0/[10-15]")
        ['FastEthernet1/0/10', 'FastEthernet1/0/11', 'FastEthernet1/0/12',
        'FastEthernet1/0/13', 'FastEthernet1/0/14', 'FastEthernet1/0/15',
        'FastEthernet2/0/10', 'FastEthernet2/0/11', 'FastEthernet2/0/12',
        'FastEthernet2/0/13', 'FastEthernet2/0/14', 'FastEthernet2/0/15']
        >>> range_expansion("GigabitEthernet[a-c]/0/1")
        ['GigabitEtherneta/0/1', 'GigabitEthernetb/0/1', 'GigabitEthernetc/0/1']
        >>> range_expansion("Eth[a,c,e]/0/1")
        ['Etha/0/1', 'Ethc/0/1', 'Ethe/0/1']
    """
    pattern_escaped = _escape_brackets(interface_pattern)
    re_compiled = re.compile(MATCH_PATTERN)
    if not re_compiled.search(pattern_escaped):
        return [_unescape_brackets(pattern_escaped)]
    interface_constant, cartesian_list = _extract_constants(pattern_escaped, re_compiled)
    return _expand_interfaces(pattern_escaped, interface_constant, cartesian_list)
