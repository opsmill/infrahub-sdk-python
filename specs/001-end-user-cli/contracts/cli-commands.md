# CLI Command Contracts

## Global Options

All commands accept:

- `--branch TEXT` — Target Infrahub branch (default: from config)
- `--config-file PATH` — Configuration file path (default: infrahubctl.toml)
- `--output [table|json|csv|yaml]` — Output format (default: table if TTY, json if piped)

## `infrahubctl get <kind> [identifier]`

**List mode** (no identifier):

- Input: kind (positional), --filter (repeatable), --limit INT, --offset INT
- Output: Table with columns for each attribute + relationship (display names)
- Exit 0: results found | Exit 80: no results (empty list) | Exit 1: invalid kind

**Detail mode** (with identifier):

- Input: kind (positional), identifier (positional — UUID or display name)
- Output: Key-value display of all attributes, relationships, metadata
- Exit 0: found | Exit 1: not found

**Filters**: `--filter name__value="spine01"` (repeatable)

## `infrahubctl create <kind>`

- Input: kind (positional), --set key=value (repeatable), --file PATH
- --set and --file are mutually exclusive
- Output: Confirmation with created object ID and display label
- Exit 0: created | Exit 1: validation error | Exit 1: server error

**File input**: JSON or YAML in Infrahub Object format
(`apiVersion: infrahub.app/v1`)

## `infrahubctl update <kind> <identifier>`

- Input: kind (positional), identifier (positional), --set key=value
  (repeatable), --file PATH
- --set and --file are mutually exclusive
- Output: Confirmation with old → new values for changed fields
- Exit 0: updated | Exit 1: not found | Exit 1: validation error

## `infrahubctl delete <kind> <identifier>`

- Input: kind (positional), identifier (positional), --yes (skip confirmation)
- Output: Confirmation prompt (unless --yes), then success message
- Exit 0: deleted | Exit 1: not found | Exit 1: dependency conflict

## `infrahubctl schema list`

- Input: --filter TEXT (substring match on kind name)
- Output: Table with columns: Namespace, Name, Kind, Description
- Exit 0: always (empty table if no matches)

## `infrahubctl schema show <kind>`

- Input: kind (positional)
- Output: Formatted display of:
  - Kind metadata (namespace, label, description, display_labels, HFID)
  - Attributes table (name, type, required, default, description)
  - Relationships table (name, peer kind, cardinality, optional)
- Exit 0: found | Exit 1: invalid kind
