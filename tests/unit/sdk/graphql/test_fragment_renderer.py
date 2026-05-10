"""Unit tests for fragment rendering functions in infrahub_sdk.graphql.query_renderer."""

from __future__ import annotations

import pytest
from graphql import parse

from infrahub_sdk.exceptions import (
    CircularFragmentError,
    DuplicateFragmentError,
    FragmentNotFoundError,
    QuerySyntaxError,
)
from infrahub_sdk.graphql.query_renderer import (
    build_fragment_index,
    collect_required_fragments,
    render_query_with_fragments,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FRAG_INTERFACE = """
fragment interfaceFragment on InterfaceL3 {
  id
  name { value }
}
"""

FRAG_DEVICE = """
fragment deviceFragment on InfraDevice {
  id
  interfaces {
    edges {
      node {
        ...interfaceFragment
      }
    }
  }
}
"""

FRAG_PORT = """
fragment portFragment on InterfaceL2 {
  id
  enabled { value }
}
"""

QUERY_USE_INTERFACE = """
query Q {
  Devices {
    edges {
      node {
        ...interfaceFragment
      }
    }
  }
}
"""

QUERY_NO_SPREADS = """
query Q {
  Devices {
    edges {
      node {
        id
        name { value }
      }
    }
  }
}
"""

QUERY_USE_DEVICE = """
query Q {
  Devices {
    edges {
      node {
        ...deviceFragment
      }
    }
  }
}
"""

QUERY_USE_BOTH = """
query Q {
  Devices {
    edges {
      node {
        ...interfaceFragment
        ...deviceFragment
      }
    }
  }
}
"""

QUERY_USE_INTERFACE_TWICE = """
query Q {
  A: Devices {
    edges {
      node {
        ...interfaceFragment
      }
    }
  }
  B: Devices {
    edges {
      node {
        ...interfaceFragment
      }
    }
  }
}
"""

QUERY_MISSING_FRAGMENT = """
query Q {
  Devices {
    edges {
      node {
        ...undeclaredFragment
      }
    }
  }
}
"""


# ---------------------------------------------------------------------------
# build_fragment_index tests
# ---------------------------------------------------------------------------


def test_build_fragment_index_invalid_syntax_raises() -> None:
    with pytest.raises(QuerySyntaxError):
        build_fragment_index(["this is not @@ valid graphql"])


def test_build_fragment_index_single_file() -> None:
    index = build_fragment_index([FRAG_INTERFACE])
    assert "interfaceFragment" in index


def test_build_fragment_index_skips_non_fragment_definitions() -> None:
    # A file that mixes an operation definition with a fragment definition —
    # the operation is not a FragmentDefinitionNode and must be skipped.
    mixed = "query Q { id }\nfragment mixedFragment on T { id }"
    index = build_fragment_index([mixed])
    assert "mixedFragment" in index
    assert len(index) == 1


def test_build_fragment_index_multiple_files() -> None:
    index = build_fragment_index([FRAG_INTERFACE, FRAG_DEVICE])
    assert "interfaceFragment" in index
    assert "deviceFragment" in index


def test_build_fragment_index_duplicate_same_name_two_files() -> None:
    with pytest.raises(DuplicateFragmentError) as exc_info:
        build_fragment_index([FRAG_INTERFACE, FRAG_INTERFACE])
    assert exc_info.value.fragment_name == "interfaceFragment"


def test_build_fragment_index_duplicate_same_name_within_file() -> None:
    combined = FRAG_INTERFACE + FRAG_INTERFACE
    with pytest.raises(DuplicateFragmentError) as exc_info:
        build_fragment_index([combined])
    assert exc_info.value.fragment_name == "interfaceFragment"


# ---------------------------------------------------------------------------
# collect_required_fragments tests
# ---------------------------------------------------------------------------


def test_collect_required_fragments_direct_single() -> None:
    index = build_fragment_index([FRAG_INTERFACE])
    doc = parse(QUERY_USE_INTERFACE)
    required = collect_required_fragments(doc, index)
    assert required == ["interfaceFragment"]


def test_collect_required_fragments_transitive() -> None:
    """DeviceFragment spreads interfaceFragment — both must be collected."""
    index = build_fragment_index([FRAG_INTERFACE, FRAG_DEVICE])
    doc = parse(QUERY_USE_DEVICE)
    required = collect_required_fragments(doc, index)
    assert "deviceFragment" in required
    assert "interfaceFragment" in required
    # interfaceFragment must appear before deviceFragment (dependency first)
    assert required.index("interfaceFragment") < required.index("deviceFragment")


def test_collect_required_fragments_deduplication() -> None:
    """Fragment used twice in query must appear only once in output."""
    index = build_fragment_index([FRAG_INTERFACE])
    doc = parse(QUERY_USE_INTERFACE_TWICE)
    required = collect_required_fragments(doc, index)
    assert required.count("interfaceFragment") == 1


def test_collect_required_fragments_missing_raises() -> None:
    index = build_fragment_index([FRAG_INTERFACE])
    doc = parse(QUERY_MISSING_FRAGMENT)
    with pytest.raises(FragmentNotFoundError) as exc_info:
        collect_required_fragments(doc, index)
    assert exc_info.value.fragment_name == "undeclaredFragment"


def test_collect_required_fragments_circular_raises() -> None:
    frag_a = "fragment FragA on Foo { ...FragB }"
    frag_b = "fragment FragB on Foo { ...FragA }"
    query = "query Q { foo { ...FragA } }"
    index = build_fragment_index([frag_a, frag_b])
    doc = parse(query)
    with pytest.raises(CircularFragmentError) as exc_info:
        collect_required_fragments(doc, index)
    assert "FragA" in exc_info.value.cycle
    assert "FragB" in exc_info.value.cycle


# ---------------------------------------------------------------------------
# render_query_with_fragments tests
# ---------------------------------------------------------------------------


def test_render_no_fragment_files_raises_when_spreads_present() -> None:
    with pytest.raises(FragmentNotFoundError):
        render_query_with_fragments(QUERY_USE_INTERFACE, [])


def test_render_no_spreads_returns_unchanged() -> None:
    result = render_query_with_fragments(QUERY_NO_SPREADS, [FRAG_INTERFACE])
    # Content should be semantically equivalent (re-printed by graphql-core)
    assert "interfaceFragment" not in result


def test_render_single_spread_from_one_file() -> None:
    result = render_query_with_fragments(QUERY_USE_INTERFACE, [FRAG_INTERFACE])
    assert "fragment interfaceFragment" in result
    assert "fragment deviceFragment" not in result


def test_render_spreads_across_two_files() -> None:
    result = render_query_with_fragments(QUERY_USE_BOTH, [FRAG_INTERFACE, FRAG_DEVICE])
    assert "fragment interfaceFragment" in result
    assert "fragment deviceFragment" in result


def test_render_transitive_dependency_included() -> None:
    """Query uses ...deviceFragment only; interfaceFragment must be inlined transitively."""
    result = render_query_with_fragments(QUERY_USE_DEVICE, [FRAG_INTERFACE, FRAG_DEVICE])
    assert "fragment deviceFragment" in result
    assert "fragment interfaceFragment" in result


def test_render_surplus_fragment_excluded() -> None:
    """PortFragment is not referenced — it must not appear in output."""
    result = render_query_with_fragments(QUERY_USE_INTERFACE, [FRAG_INTERFACE, FRAG_PORT])
    assert "fragment interfaceFragment" in result
    assert "fragment portFragment" not in result


def test_render_deduplication_definition_appears_once() -> None:
    """Fragment spread twice in query; definition must appear exactly once."""
    result = render_query_with_fragments(QUERY_USE_INTERFACE_TWICE, [FRAG_INTERFACE])
    assert result.count("fragment interfaceFragment") == 1


def test_render_missing_fragment_raises() -> None:
    with pytest.raises(FragmentNotFoundError) as exc_info:
        render_query_with_fragments(QUERY_MISSING_FRAGMENT, [FRAG_INTERFACE])
    assert exc_info.value.fragment_name == "undeclaredFragment"


def test_render_duplicate_fragment_raises() -> None:
    with pytest.raises(DuplicateFragmentError):
        render_query_with_fragments(QUERY_USE_INTERFACE, [FRAG_INTERFACE, FRAG_INTERFACE])


def test_render_circular_fragment_raises() -> None:
    frag_a = "fragment FragA on Foo { ...FragB }"
    frag_b = "fragment FragB on Foo { ...FragA }"
    query = "query Q { foo { ...FragA } }"
    with pytest.raises(CircularFragmentError):
        render_query_with_fragments(query, [frag_a, frag_b])


def test_render_invalid_query_syntax_raises() -> None:
    with pytest.raises(QuerySyntaxError):
        render_query_with_fragments("this is not @@ valid graphql", [])


def test_render_invalid_fragment_file_syntax_raises() -> None:
    with pytest.raises(QuerySyntaxError):
        render_query_with_fragments(QUERY_USE_INTERFACE, ["this is not @@ valid graphql"])


# ---------------------------------------------------------------------------
# Inline (query-local) fragment tests
# ---------------------------------------------------------------------------

QUERY_WITH_INLINE_FRAGMENT = """
query Q {
  Devices {
    edges {
      node {
        ...deviceFields
      }
    }
  }
}

fragment deviceFields on InfraDevice {
  id
  name { value }
}
"""


def test_collect_required_fragments_inline_fragment_not_raised() -> None:
    """A fragment defined inside the query document must not raise FragmentNotFoundError."""
    doc = parse(QUERY_WITH_INLINE_FRAGMENT)
    # Empty index — no external fragment files
    required = collect_required_fragments(doc, {})
    # The inline fragment is self-contained; nothing needs to be appended from external files
    assert required == []


def test_render_inline_fragment_not_raised() -> None:
    """render_query_with_fragments must not raise when the query already defines its own fragment."""
    result = render_query_with_fragments(QUERY_WITH_INLINE_FRAGMENT, [])
    assert "fragment deviceFields" in result
