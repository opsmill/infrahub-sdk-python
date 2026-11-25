from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from itertools import chain
from typing import Any


class DependencyCycleExistsError(Exception):
    def __init__(self, cycles: Iterable[Sequence[str]], *args: tuple[Any]) -> None:
        self.cycles = cycles
        super().__init__(*args)

    def get_cycle_strings(self) -> list[str]:
        return [" --> ".join([str(node) for node in cycle]) for cycle in self.cycles]

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.get_cycle_strings()})"


def topological_sort(dependency_dict: Mapping[str, Iterable[str]]) -> list[set[str]]:
    if not dependency_dict:
        return []

    missing_dependent_keys = set(chain(*dependency_dict.values())) - set(dependency_dict.keys())

    dependency_dict_to_sort = {k: set(v) for k, v in dependency_dict.items()}
    dependency_dict_to_sort.update({missing_key: set() for missing_key in missing_dependent_keys})

    ordered = []
    while len(dependency_dict_to_sort) > 0:
        nondependant_nodes = {key for key, dependencies in dependency_dict_to_sort.items() if len(dependencies) == 0}
        dependency_dict_to_sort = {
            k: v - nondependant_nodes for k, v in dependency_dict_to_sort.items() if k not in nondependant_nodes
        }
        ordered.append(nondependant_nodes)

        if len(nondependant_nodes) == 0 and len(dependency_dict_to_sort) != 0:
            cycles = get_cycles(dependency_dict_to_sort)
            raise DependencyCycleExistsError(cycles=cycles)
    return ordered


def get_cycles(dependency_dict: Mapping[str, Iterable[str]]) -> list[list[str]]:
    if not dependency_dict:
        return []

    dict_to_check = {**dependency_dict}
    cycles = []

    while dict_to_check:
        start_path = list(dict_to_check.keys())[:1]
        cycles += _get_cycles(dependency_dict=dict_to_check, path=start_path)
    return cycles


def _get_cycles(dependency_dict: dict[str, Iterable[str]], path: list[str]) -> list[list[str]]:
    try:
        next_nodes = dependency_dict.pop(path[-1])
    except KeyError:
        return []
    cycles = []
    for next_node in next_nodes:
        if next_node in path:
            cycles.append([*path[path.index(next_node) :], next_node])
        else:
            next_cycles = _get_cycles(dependency_dict, [*path, next_node])
            if next_cycles:
                cycles += next_cycles
    return cycles


def strongly_connected_components(graph: Mapping[str, set[str]], order: Sequence[str]) -> list[list[str]]:
    """Group the keys of `graph` into components where every key can reach every other one (Tarjan).

    Keys and components follow `order`, so the result does not depend on set iteration order.
    """
    position = {key: index for index, key in enumerate(order)}
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []

    def visit(key: str) -> None:
        index[key] = low[key] = len(index)
        stack.append(key)
        on_stack.add(key)
        for peer in sorted(graph[key], key=position.__getitem__):
            if peer not in index:
                visit(peer)
                low[key] = min(low[key], low[peer])
            elif peer in on_stack:
                low[key] = min(low[key], index[peer])
        if low[key] == index[key]:
            component: list[str] = []
            while True:
                member = stack.pop()
                on_stack.discard(member)
                component.append(member)
                if member == key:
                    break
            components.append(sorted(component, key=position.__getitem__))

    for key in order:
        if key not in index:
            visit(key)
    return components


def dependents_first(dependencies: Mapping[str, set[str]], order: Sequence[str]) -> list[str] | None:
    """Sort the keys of `dependencies` so each key comes before the keys it depends on.

    Keys with no dependency between them keep their place in `order`. Returns None on a cycle.
    """
    position = {key: index for index, key in enumerate(order)}
    try:
        levels = topological_sort(dependencies)
    except DependencyCycleExistsError:
        return None
    return [key for level in reversed(levels) for key in sorted(level, key=position.__getitem__)]
