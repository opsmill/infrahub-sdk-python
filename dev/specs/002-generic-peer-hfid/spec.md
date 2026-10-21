# Feature Specification: Reference generic peers by HFID in object files

**Feature Branch**: `atg/strict-waves-stop` (no ticket branch created)

**Created**: 2026-10-19

**Status**: Draft

**Input**: User description: "When I'm using object files and there is a parent interface or a peer relationship that is a generic (and the generic doesn't define the HFID but the nodes below that do specify the HFID), we need some way of being able to specify that." Example: `InterfacesSubInterface.parent_interface` has peer `InterfacesSupportsSubintf` and `InterfacesTunnelInterface.source_interface` has peer `InterfacesSupportsTunnels`. Neither generic defines a human-friendly ID (HFID). The nodes that inherit from them (`InterfacesPhysicalInterface`, `InterfacesPortChannelInterface`) define the HFID `[device, name]`. The object file gives `parent_interface: [router1, Gi0/0/3]`, and the load fails because the peer kind has no HFID.

## Problem

A schema designer can point a relationship at a generic so that several node kinds can be the peer. For example, both physical interfaces and port-channels can be the parent of a sub-interface. When the generic has no HFID, an object file cannot reference an existing peer by its HFID, even though every node kind that inherits from the generic defines one.

Today the schema designer has two workarounds, and both change the data model only to suit the loader:

- Point the relationship at one node kind, for example `InterfacesPhysicalInterface`. This removes the ability to use a port-channel as a parent or a tunnel source.
- Add an HFID to the generic. This forces every attribute and relationship in the HFID (here `name` and `device`) onto the generic as well.

This feature lets the object file author reference a peer of a generic relationship by the HFID of a node kind that inherits from the generic, without changing the schema.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reference a generic peer by naming its kind and HFID (Priority: P1)

A network automation engineer loads sub-interfaces and tunnel interfaces from object files. Each sub-interface references its parent interface, which already exists. The engineer states the node kind of the parent and its HFID in the object file, and the load links each sub-interface to the correct parent.

Example of the object file content:

```yaml
- name: Gi0/0/3.10
  device: router1
  parent_interface:
    kind: InterfacesPhysicalInterface
    hfid: [router1, Gi0/0/3]
- name: Po1.20
  device: router1
  parent_interface:
    kind: InterfacesPortChannelInterface
    hfid: [router1, Po1]
```

**Why this priority**: This is the smallest change that removes the need to alter the schema. It is unambiguous, because the author states exactly which node kind to look up, and it keeps port-channels usable as parents.

**Independent Test**: Load a schema in which a relationship points to a generic without an HFID and two node kinds that inherit from it define HFIDs. Create one node of each kind. Load an object file that references each by kind and HFID. Verify that each new node is linked to the expected peer.

**Acceptance Scenarios**:

1. **Given** a physical interface `router1 / Gi0/0/3` exists, **When** the engineer loads a sub-interface whose `parent_interface` gives kind `InterfacesPhysicalInterface` and HFID `[router1, Gi0/0/3]`, **Then** the sub-interface is created and its parent is that physical interface.
2. **Given** a port-channel `router1 / Po1` exists, **When** the engineer loads a sub-interface whose `parent_interface` gives kind `InterfacesPortChannelInterface` and HFID `[router1, Po1]`, **Then** the sub-interface is created and its parent is that port-channel.
3. **Given** the same object file, **When** the engineer validates it without loading, **Then** validation passes.
4. **Given** a relationship of cardinality many to a generic, **When** the engineer gives a list of references that each name a kind and an HFID, **Then** every listed peer is linked.

---

### User Story 2 - Reference a generic peer by HFID alone (Priority: P2)

The engineer writes only the HFID, as in the original example (`source_interface: [router1, Gi0/0/3]`), without naming the kind. The load finds the single existing node, among the node kinds that inherit from the generic, whose HFID matches, and links it.

**Why this priority**: This keeps object files short and matches how the engineer already writes references to non-generic peers. It depends on a lookup across several node kinds, so it carries more risk than User Story 1.

**Independent Test**: With the same schema and data as User Story 1, load an object file that gives only `[router1, Gi0/0/3]`. Verify that the peer is the physical interface. Then create a port-channel with the same device and name and verify that the load reports an ambiguous reference.

**Acceptance Scenarios**:

1. **Given** exactly one node among the inheriting kinds has HFID `[router2, Gi0/0/3]`, **When** the engineer loads a tunnel interface with `source_interface: [router2, Gi0/0/3]`, **Then** the tunnel interface is linked to that node.
2. **Given** two nodes of different inheriting kinds both have HFID `[router1, X]`, **When** the engineer loads a reference `[router1, X]` without a kind, **Then** the load fails and the error message names the matching kinds and tells the engineer to state the kind.
3. **Given** no inheriting node has HFID `[router9, Gi0/0/3]`, **When** the engineer loads that reference, **Then** the load fails and the error message names the relationship, the generic and the HFID that was not found.

---

### User Story 3 - Clear errors when a reference cannot be resolved (Priority: P3)

When the engineer makes a mistake in a reference to a generic peer, the error message says what is wrong and how to fix it, before any data is written.

**Why this priority**: Without this, the engineer views a server-side error that does not mention generics or HFIDs and cannot tell which line of the file is wrong.

**Independent Test**: Load object files with each mistake listed below and check the message.

**Acceptance Scenarios**:

1. **Given** a reference names a kind that does not inherit from the relationship's generic, **When** the engineer validates the file, **Then** validation fails and names the kind, the generic and the object's position in the file. A missing or ambiguous peer is reported when the file is loaded, not during validation.
2. **Given** a reference names a kind that has no HFID, **When** the engineer validates the file, **Then** validation fails and says that the kind has no HFID.
3. **Given** a reference gives an HFID with a different number of parts than the kind's HFID, **When** the engineer validates the file, **Then** validation fails and states the expected parts.

---

### Edge Cases

- The generic itself defines an HFID: the current behavior does not change.
- A reference uses a single string instead of a list for a kind whose HFID has one part: it is treated the same as a one-item list, as for non-generic peers today.
- A reference gives a node ID (UUID) instead of an HFID: the current behavior does not change.
- Only some kinds that inherit from the generic define an HFID: lookup by HFID alone (User Story 2) considers only those kinds; naming a kind without an HFID is an error (User Story 3, scenario 2).
- The referenced peer is created earlier in the same object file or in an earlier file of the same load: it can be referenced, as non-generic peers can be today.
- A nested object (`kind` plus `data`) is given instead of a reference: the current behavior for creating related nodes does not change.
- The load runs against a branch other than the default branch: the lookup uses that branch.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: An object file MUST accept a reference to an existing peer that gives both the peer's node kind and its HFID, for relationships of cardinality one and cardinality many.
- **FR-002**: When a reference names a kind, the loader MUST check that the kind is the relationship's peer kind or inherits from it, and MUST reject the reference otherwise.
- **FR-003**: When a reference names a kind, the loader MUST use that kind's HFID definition to interpret the reference, including turning a single string into a one-part HFID.
- **FR-004**: When the relationship's peer is a generic without an HFID and a reference gives only an HFID, the loader MUST search the kinds that inherit from the generic and define an HFID, and link the single node that matches.
- **FR-005**: When more than one node matches under FR-004, the loader MUST stop and report the matching kinds and the reference, and MUST NOT pick one.
- **FR-006**: When no node matches a reference, the loader MUST report the relationship, the peer kind, the HFID and the object's position in the file.
- **FR-007**: Validation without loading (the `validate` command) MUST report the errors that the schema alone can detect: a kind that is not allowed (FR-002), a kind without an HFID, and an HFID with the wrong number of parts. It writes no data. A missing or ambiguous peer (FR-005, FR-006) is reported at load time, because the peer can be created earlier in the same load.
- **FR-008**: Object files that are valid today MUST load with the same result after this change.
- **FR-009**: The behavior MUST be the same through `infrahubctl object load`, `infrahubctl object validate` and the Python object file API. The object file API is asynchronous only today, so this change adds no synchronous version.
- **FR-010**: The object file documentation MUST describe the new reference form with an example of a relationship to a generic.

### Key Entities

- **Generic peer relationship**: A relationship whose peer is a generic, for example `parent_interface` with peer `InterfacesSupportsSubintf`. The generic may or may not define an HFID.
- **Inheriting node kind**: A node kind that inherits from the generic, for example `InterfacesPhysicalInterface`. It may define its own HFID, for example `[device__hostname__value, name__value]`.
- **Peer reference**: The value in the object file that identifies an existing peer: an HFID, an HFID with a kind, or a node ID.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The sub-interface and tunnel interface object files from the example load without changing `schemas/interfaces/interfaces.yml`, and port-channels stay valid parents and tunnel sources.
- **SC-002**: 100% of the existing object file tests pass without changes to their input files.
- **SC-003**: Each error case in User Story 2 and User Story 3 produces a message that names the relationship, the reference and the object's position, so the engineer can fix the file without reading server logs.
- **SC-004**: The engineer can reference a generic peer by adding at most one line (`kind:`) per reference, compared with a reference to a non-generic peer.

## Assumptions

- The Infrahub server can resolve a related node from a kind plus an HFID when the relationship's peer is a generic (confirmed: `RelatedNodeInput.kind` in the server, see `research.md`). The SDK already sends `kind` with `hfid` when both are set on a related node.
- The reference form with a kind uses the keys `kind` and `hfid`, to match the `kind` key already used for nested objects of a generic peer. The exact key names can change during planning.
- Lookup by HFID alone (User Story 2) needs one query per inheriting kind that defines an HFID. The number of such kinds per generic is small (fewer than 10 in known schemas), so the extra queries are acceptable.
- Changes to the Infrahub server, such as letting a generic inherit an HFID from its nodes, are out of scope.
- The schema changes described as Option 1 and Option 2 in the input remain available to schema designers; this feature removes the need for them but does not prevent them.
