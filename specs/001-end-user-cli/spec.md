# Feature Specification: End-User CLI (`infrahubctl` CRUD commands)

**Feature Branch**: `001-end-user-cli`
**Created**: 2026-03-28
**Status**: Draft
**Input**: User description: "Add CRUD and schema discovery commands to `infrahubctl` for end users to query, create, and modify data in the Infrahub database."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Query Data from Infrahub (Priority: P1)

An end user wants to retrieve data from Infrahub to answer operational questions. They open a terminal, run a command specifying the type of object they want (e.g., devices, interfaces, IP addresses), and receive a formatted table of results. They can filter results by attribute values and choose output formats (table, JSON, CSV) depending on whether they are reading interactively or piping to another tool.

**Why this priority**: Reading data is the most fundamental operation. Without query capability, no other CRUD operations provide value. This is also the lowest-risk operation (read-only) and serves the widest audience.

**Independent Test**: Can be fully tested by querying any existing node type in an Infrahub instance and verifying correct output. Delivers immediate value for operational visibility.

**Acceptance Scenarios**:

1. **Given** a running Infrahub instance with data, **When** the user runs `infrahubctl get <kind>`, **Then** a formatted table of all objects of that kind is displayed with attribute columns and relationship columns (showing display names).
2. **Given** a running Infrahub instance, **When** the user runs `infrahubctl get <kind> --filter name__value="spine01"`, **Then** only objects matching the filter are returned.
3. **Given** a running Infrahub instance, **When** the user runs `infrahubctl get <kind> --output json`, **Then** the results are printed as valid JSON to stdout.
4. **Given** a running Infrahub instance, **When** the user runs `infrahubctl get <kind> --output yaml`, **Then** the results are printed in Infrahub Object YAML format (with `apiVersion: infrahub.app/v1`, `kind: Object`, `spec.kind`, and `spec.data` array), suitable for round-tripping back into `infrahubctl create --file`.
5. **Given** an Infrahub instance, **When** the user runs `infrahubctl get <kind> --branch develop`, **Then** data from the specified branch is returned.
6. **Given** an invalid kind name, **When** the user runs `infrahubctl get UnknownKind`, **Then** a clear error message is displayed listing available kinds or suggesting corrections.
7. **Given** an existing object, **When** the user runs `infrahubctl get <kind> <identifier>`, **Then** a detailed view is displayed showing all attributes, relationships, and metadata for that single object.

---

### User Story 2 - Create New Objects (Priority: P2)

An end user needs to add new infrastructure data to Infrahub. They run a command specifying the object kind and its attribute values, and the system creates the object and confirms success. They can also create objects from a file (JSON or YAML) for batch operations.

**Why this priority**: After querying, creation is the next most common operation. Users need to populate Infrahub with data. This is a natural progression from read to write.

**Independent Test**: Can be tested by creating an object of any kind and then querying it back to verify it exists with correct attributes.

**Acceptance Scenarios**:

1. **Given** a running Infrahub instance, **When** the user runs `infrahubctl create <kind> --set name="spine03" --set description="New spine switch"`, **Then** the object is created and a confirmation with the object ID is displayed.
2. **Given** a YAML file with object definitions, **When** the user runs `infrahubctl create <kind> --file objects.yaml`, **Then** all objects in the file are created and a summary of results (created count, errors) is displayed.
3. **Given** invalid attribute or relationship names, **When** the user runs `infrahubctl create <kind> --set invalid_field="value"`, **Then** a clear validation error is displayed indicating which fields are invalid and what the valid attributes and relationships are.

---

### User Story 3 - Modify Existing Objects (Priority: P3)

An end user needs to update attributes on existing infrastructure objects. They identify the object by kind and name (or ID), specify the attributes to change, and the system applies the update and confirms.

**Why this priority**: Modification completes the core CRUD workflow. Users who can query and create also need to update existing records as infrastructure changes.

**Independent Test**: Can be tested by modifying an attribute on an existing object and querying it back to verify the change persists.

**Acceptance Scenarios**:

1. **Given** an existing object, **When** the user runs `infrahubctl update <kind> <identifier> --set description="Updated description"`, **Then** the object is updated and a confirmation is displayed showing old and new values.
2. **Given** an existing object, **When** the user runs `infrahubctl update <kind> <identifier> --file updates.yaml`, **Then** the object is updated from the file contents.
3. **Given** a non-existent object identifier, **When** the user runs `infrahubctl update <kind> nonexistent`, **Then** a clear error message indicates the object was not found.

---

### User Story 4 - Delete Objects (Priority: P4)

An end user needs to remove obsolete infrastructure data from Infrahub. They specify the object to delete by kind and identifier, confirm the deletion, and the system removes it.

**Why this priority**: Deletion is the least frequent CRUD operation and the most dangerous. It completes the full lifecycle but is lower priority than the core read/create/update loop.

**Independent Test**: Can be tested by creating an object, deleting it, and confirming it no longer appears in query results.

**Acceptance Scenarios**:

1. **Given** an existing object, **When** the user runs `infrahubctl delete <kind> <identifier>`, **Then** a confirmation prompt is shown, and upon confirmation the object is deleted with a success message.
2. **Given** an existing object, **When** the user runs `infrahubctl delete <kind> <identifier> --yes`, **Then** the object is deleted without a confirmation prompt.
3. **Given** an object with dependencies, **When** the user attempts to delete it, **Then** a clear error message explains what depends on it and how to resolve the conflict.

---

### User Story 5 - Discover Available Schema (Priority: P5)

An end user unfamiliar with the data model wants to explore what kinds of objects exist in Infrahub and what attributes each kind has. They run a command to list available kinds and inspect their schema.

**Why this priority**: Schema discovery supports all other operations. Without knowing what kinds and attributes exist, users cannot effectively query, create, or update. However, this is a supporting operation, not a core data operation.

**Independent Test**: Can be tested by listing schema kinds and inspecting a known kind's attributes against the actual schema definition.

**Acceptance Scenarios**:

1. **Given** a running Infrahub instance, **When** the user runs `infrahubctl schema list`, **Then** a table of all available kinds is displayed with their namespace, name, and description.
2. **Given** a valid kind name, **When** the user runs `infrahubctl schema show <kind>`, **Then** the kind's attributes, relationships, and constraints are displayed in a readable format.
3. **Given** a partial kind name, **When** the user runs `infrahubctl schema list --filter "Network"`, **Then** only kinds matching the filter are shown.

---

### Edge Cases

- What happens when the Infrahub server is unreachable? Clear connection error with the configured server address shown.
- What happens when the API token is missing or expired? Authentication error with instructions on how to configure credentials.
- What happens when the user queries a kind with thousands of objects? Results are paginated with a default limit and the user is informed of total count.
- What happens when a create/update operation partially fails in batch mode? A detailed report shows which objects succeeded and which failed, with per-object error messages.
- What happens when the user provides attributes in the wrong format? Validation error specifying expected format for each attribute.

## Clarifications

### Session 2026-03-28

- Q: How should users specify relationships in create/update commands? → A: Unified `--set` flag for both attributes and relationships (e.g., `--set name="x" --set site="my-site"`).
- Q: Should there be a single-object detail view? → A: `infrahubctl get <kind> <identifier>` shows a detail view with all attributes, relationships, and metadata.
- Q: How should relationships appear in list/table output? → A: Show as columns with their display name (e.g., site column shows "my-site"). Full relationship detail in detail view only.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide CRUD and schema discovery commands within `infrahubctl`.
- **FR-002**: The system MUST support querying objects by kind with `infrahubctl get <kind>` (list view) and `infrahubctl get <kind> <identifier>` (detail view showing all attributes, relationships, and metadata).
- **FR-003**: The system MUST support filtering query results by attribute values.
- **FR-004**: The system MUST support multiple output formats: human-readable table (default), JSON, CSV, and Infrahub Object YAML (`--output yaml`). The YAML format MUST use the Infrahub spec object structure (`apiVersion: infrahub.app/v1`, `kind: Object`, with `spec.kind` and `spec.data` fields), matching the format used by `infrahubctl create --file`.
- **FR-005**: The system MUST support creating objects with `infrahubctl create <kind>` using inline `--set` flags (for both attributes and relationships) or file input.
- **FR-006**: The system MUST support updating objects with `infrahubctl update <kind> <identifier>` using inline `--set` flags (for both attributes and relationships) or file input.
- **FR-007**: The system MUST support deleting objects with `infrahubctl delete <kind> <identifier>` with confirmation.
- **FR-008**: The system MUST support schema discovery with `infrahubctl schema list` and `infrahubctl schema show <kind>`.
- **FR-009**: The system MUST support specifying a target branch for all operations via `--branch`.
- **FR-010**: The system MUST reuse the existing SDK configuration mechanism (server address, API token) from `infrahubctl.toml` or environment variables.
- **FR-011**: The system MUST display clear, actionable error messages for all failure modes (connection, authentication, validation, not found).
- **FR-012**: The system MUST paginate large result sets with configurable page size via `--limit` and `--offset`.
- **FR-013**: The system MUST support batch operations from file input (JSON or YAML) for create and update commands.
- **FR-014**: The system MUST provide a `--yes` flag to skip confirmation prompts for destructive operations.
- **FR-015**: All new code MUST have unit tests covering public functions and integration tests covering Infrahub server interactions, consistent with the project's test discipline standards.

### Key Entities

- **Kind**: A type definition in the Infrahub schema (e.g., InfraDevice, IpamIPAddress). Has a namespace, name, attributes, and relationships.
- **Node**: An instance of a Kind stored in Infrahub. Has an ID, attribute values, and relationship connections.
- **Attribute**: A named property on a Kind with a type, optional constraints, and a value on each Node.
- **Relationship**: A typed connection between two Nodes, defined in the schema with cardinality and direction.

## Assumptions

- The `infrahub` command shares the same configuration file and environment variables as `infrahubctl` (no separate config needed).
- Object identifiers in update/delete commands accept either the object's display name or its UUID.
- The default output format for interactive terminals is a human-readable table; when stdout is piped, JSON is used automatically.
- Batch file input supports both JSON and YAML formats with the same schema.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can query any object kind and receive formatted results within 5 seconds for datasets under 1000 objects.
- **SC-002**: Users can create a single object in under 3 commands (configure once, then one create command).
- **SC-003**: 90% of first-time users can successfully query data without consulting documentation beyond `--help`.
- **SC-004**: All error messages include a suggested corrective action (not just a failure description).
- **SC-005**: The CLI supports all CRUD operations and schema discovery as a single installable command alongside `infrahubctl`.
