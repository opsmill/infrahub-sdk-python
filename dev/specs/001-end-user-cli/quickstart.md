# Quickstart: `infrahubctl` CLI

## Prerequisites

- Python 3.10+
- Infrahub SDK installed with CLI extras: `pip install infrahub-sdk[ctl]`
- A running Infrahub instance

## Configuration

These commands use the existing `infrahubctl` configuration.

Set via environment variables:

```bash
export INFRAHUB_ADDRESS="http://localhost:8000"
export INFRAHUB_API_TOKEN="your-api-token"
```

Or via `infrahubctl.toml`:

```toml
[infrahub]
server_address = "http://localhost:8000"
api_token = "your-api-token"
```

## Discover Your Schema

```bash
# List all available kinds
infrahubctl schema list

# Filter by name
infrahubctl schema list --filter "Device"

# Show details for a specific kind
infrahubctl schema show InfraDevice
```

## Query Data

```bash
# List all devices
infrahubctl get InfraDevice

# Filter by attribute
infrahubctl get InfraDevice --filter name__value="spine01"

# Get a single device's full details
infrahubctl get InfraDevice spine01

# Output as JSON (for scripting)
infrahubctl get InfraDevice --output json

# Export as Infrahub Object YAML (round-trippable)
infrahubctl get InfraDevice --output yaml > devices.yaml

# Query a specific branch
infrahubctl get InfraDevice --branch develop

# Paginate results
infrahubctl get InfraDevice --limit 10 --offset 20
```

## Create Objects

```bash
# Create with inline flags
infrahubctl create InfraDevice \
  --set name="spine03" \
  --set description="New spine switch" \
  --set site="dc1"

# Create from a YAML file
infrahubctl create InfraDevice --file new-devices.yaml
```

## Update Objects

```bash
# Update an attribute
infrahubctl update InfraDevice spine03 \
  --set description="Updated spine switch"

# Update from file
infrahubctl update InfraDevice spine03 --file updates.yaml
```

## Delete Objects

```bash
# Delete with confirmation prompt
infrahubctl delete InfraDevice spine03

# Skip confirmation
infrahubctl delete InfraDevice spine03 --yes
```

## Output Formats

| Format | Flag | Use Case |
| ------ | ---- | -------- |
| Table | `--output table` | Interactive terminal (default) |
| JSON | `--output json` | Scripting, piping (default when piped) |
| CSV | `--output csv` | Spreadsheet import, data analysis |
| YAML | `--output yaml` | Backup, round-trip with `--file` |

## Validation

To verify the CLI is working:

1. `infrahubctl schema list` — confirms connection and authentication
2. `infrahubctl get <any-kind>` — confirms data access
3. `infrahubctl get <kind> --output yaml > test.yaml` then
   `infrahubctl create <kind> --file test.yaml` — confirms round-trip
