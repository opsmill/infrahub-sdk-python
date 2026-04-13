from dataclasses import dataclass
from enum import Flag, auto


class ExecutionContext(Flag):
    CORE = auto()
    WORKER = auto()
    LOCAL = auto()
    ALL = CORE | WORKER | LOCAL


@dataclass
class FilterDefinition:
    name: str
    allowed_contexts: ExecutionContext
    source: str

    @property
    def trusted(self) -> bool:
        """Backward compatibility: trusted means allowed in all contexts."""
        return self.allowed_contexts == ExecutionContext.ALL


BUILTIN_FILTERS = [
    FilterDefinition(name="abs", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="attr", allowed_contexts=ExecutionContext.WORKER, source="jinja2"),
    FilterDefinition(name="batch", allowed_contexts=ExecutionContext.WORKER, source="jinja2"),
    FilterDefinition(name="capitalize", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="center", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="count", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="d", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="default", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="dictsort", allowed_contexts=ExecutionContext.WORKER, source="jinja2"),
    FilterDefinition(name="e", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="escape", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="filesizeformat", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="first", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="float", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="forceescape", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="format", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="groupby", allowed_contexts=ExecutionContext.WORKER, source="jinja2"),
    FilterDefinition(name="indent", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="int", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="items", allowed_contexts=ExecutionContext.WORKER, source="jinja2"),
    FilterDefinition(name="join", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="last", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="length", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="list", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="lower", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="map", allowed_contexts=ExecutionContext.WORKER, source="jinja2"),
    FilterDefinition(name="max", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="min", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="pprint", allowed_contexts=ExecutionContext.WORKER, source="jinja2"),
    FilterDefinition(name="random", allowed_contexts=ExecutionContext.WORKER, source="jinja2"),
    FilterDefinition(name="reject", allowed_contexts=ExecutionContext.WORKER, source="jinja2"),
    FilterDefinition(name="rejectattr", allowed_contexts=ExecutionContext.WORKER, source="jinja2"),
    FilterDefinition(name="replace", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="reverse", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="round", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="safe", allowed_contexts=ExecutionContext.WORKER, source="jinja2"),
    FilterDefinition(name="select", allowed_contexts=ExecutionContext.WORKER, source="jinja2"),
    FilterDefinition(name="selectattr", allowed_contexts=ExecutionContext.WORKER, source="jinja2"),
    FilterDefinition(name="slice", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="sort", allowed_contexts=ExecutionContext.WORKER, source="jinja2"),
    FilterDefinition(name="string", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="striptags", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="sum", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="title", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="tojson", allowed_contexts=ExecutionContext.WORKER, source="jinja2"),
    FilterDefinition(name="trim", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="truncate", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="unique", allowed_contexts=ExecutionContext.WORKER, source="jinja2"),
    FilterDefinition(name="upper", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="urlencode", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="urlize", allowed_contexts=ExecutionContext.WORKER, source="jinja2"),
    FilterDefinition(name="wordcount", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="wordwrap", allowed_contexts=ExecutionContext.ALL, source="jinja2"),
    FilterDefinition(name="xmlattr", allowed_contexts=ExecutionContext.WORKER, source="jinja2"),
]


NETUTILS_FILTERS = [
    FilterDefinition(name="abbreviated_interface_name", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="abbreviated_interface_name_list", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="asn_to_int", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="bits_to_name", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="bytes_to_name", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="canonical_interface_name", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="canonical_interface_name_list", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="cidr_to_netmask", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="cidr_to_netmaskv6", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="clean_config", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="compare_version_loose", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="compare_version_strict", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="config_compliance", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="config_section_not_parsed", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="delimiter_change", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="diff_network_config", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="feature_compliance", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="find_unordered_cfg_lines", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="fqdn_to_ip", allowed_contexts=ExecutionContext.LOCAL, source="netutils"),
    FilterDefinition(name="get_all_host", allowed_contexts=ExecutionContext.LOCAL, source="netutils"),
    FilterDefinition(name="get_broadcast_address", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="get_first_usable", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="get_ips_sorted", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="get_nist_urls", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="get_nist_vendor_platform_urls", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="get_oui", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="get_peer_ip", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="get_range_ips", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="get_upgrade_path", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="get_usable_range", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="hash_data", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="int_to_asdot", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="interface_range_compress", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="interface_range_expansion", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="ip_addition", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="ip_subtract", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="ip_to_bin", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="ip_to_hex", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="ipaddress_address", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="ipaddress_interface", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="ipaddress_network", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="is_classful", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="is_fqdn_resolvable", allowed_contexts=ExecutionContext.LOCAL, source="netutils"),
    FilterDefinition(name="is_ip", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="is_ip_range", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="is_ip_within", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="is_netmask", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="is_network", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="is_reversible_wildcardmask", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="is_valid_mac", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="longest_prefix_match", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="mac_normalize", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="mac_to_format", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="mac_to_int", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="mac_type", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="name_to_bits", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="name_to_bytes", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="name_to_name", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="netmask_to_cidr", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="netmask_to_wildcardmask", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="normalise_delimiter_caret_c", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="paloalto_panos_brace_to_set", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="paloalto_panos_clean_newlines", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="regex_findall", allowed_contexts=ExecutionContext.LOCAL, source="netutils"),
    FilterDefinition(name="regex_match", allowed_contexts=ExecutionContext.LOCAL, source="netutils"),
    FilterDefinition(name="regex_search", allowed_contexts=ExecutionContext.LOCAL, source="netutils"),
    FilterDefinition(name="regex_split", allowed_contexts=ExecutionContext.LOCAL, source="netutils"),
    FilterDefinition(name="regex_sub", allowed_contexts=ExecutionContext.LOCAL, source="netutils"),
    FilterDefinition(name="sanitize_config", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="section_config", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="sort_interface_list", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="split_interface", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="uptime_seconds_to_string", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="uptime_string_to_seconds", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="version_metadata", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="vlanconfig_to_list", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="vlanlist_to_config", allowed_contexts=ExecutionContext.ALL, source="netutils"),
    FilterDefinition(name="wildcardmask_to_netmask", allowed_contexts=ExecutionContext.ALL, source="netutils"),
]


INFRAHUB_FILTERS = [
    FilterDefinition(name="artifact_content", allowed_contexts=ExecutionContext.WORKER, source="infrahub"),
    FilterDefinition(name="file_object_content", allowed_contexts=ExecutionContext.WORKER, source="infrahub"),
    FilterDefinition(name="file_object_content_by_hfid", allowed_contexts=ExecutionContext.WORKER, source="infrahub"),
    FilterDefinition(name="file_object_content_by_id", allowed_contexts=ExecutionContext.WORKER, source="infrahub"),
    FilterDefinition(name="from_json", allowed_contexts=ExecutionContext.ALL, source="infrahub"),
    FilterDefinition(name="from_yaml", allowed_contexts=ExecutionContext.ALL, source="infrahub"),
]


AVAILABLE_FILTERS = BUILTIN_FILTERS + NETUTILS_FILTERS + INFRAHUB_FILTERS
