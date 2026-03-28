# Quickstart: `infrahub` CLI

## Prerequisites

- Python 3.10+
- Infrahub SDK installed with CLI extras: `pip install infrahub-sdk[ctl]`
- A running Infrahub instance

## Configuration

The `infrahub` command uses the same configuration as `infrahubctl`.

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
infrahub schema list

# Filter by name
infrahub schema list --filter "Device"

# Show details for a specific kind
infrahub schema show InfraDevice
```

## Query Data

```bash
# List all devices
infrahub get InfraDevice

# Filter by attribute
infrahub get InfraDevice --filter name__value="spine01"

# Get a single device's full details
infrahub get InfraDevice spine01

# Output as JSON (for scripting)
infrahub get InfraDevice --output json

# Export as Infrahub Object YAML (round-trippable)
infrahub get InfraDevice --output yaml > devices.yaml

# Query a specific branch
infrahub get InfraDevice --branch develop

# Paginate results
infrahub get InfraDevice --limit 10 --offset 20
```

## Create Objects

```bash
# Create with inline flags
infrahub create InfraDevice \
  --set name="spine03" \
  --set description="New spine switch" \
  --set site="dc1"

# Create from a YAML file
infrahub create InfraDevice --file new-devices.yaml
```

## Update Objects

```bash
# Update an attribute
infrahub update InfraDevice spine03 \
  --set description="Updated spine switch"

# Update from file
infrahub update InfraDevice spine03 --file updates.yaml
```

## Delete Objects

```bash
# Delete with confirmation prompt
infrahub delete InfraDevice spine03

# Skip confirmation
infrahub delete InfraDevice spine03 --yes
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

1. `infrahub schema list` — confirms connection and authentication
2. `infrahub get <any-kind>` — confirms data access
3. `infrahub get <kind> --output yaml > test.yaml` then
   `infrahub create <kind> --file test.yaml` — confirms round-trip
