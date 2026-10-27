`infrahubctl schema export` now gets the export from the Infrahub server (`GET /api/schema/export`), so the exported files load into another instance without editing. Two new options:

- `--mode brief|full`: `brief`, the default, leaves out every value that Infrahub derives again on load, such as labels and order weights. `full` writes them, so loading the export into an instance that already has the schema overwrites those values.
- `--single-file`: writes every namespace to one `schema.yml` instead of one file per namespace.

Each exported file records the Infrahub release that produced it in `infrahub_version`. `infrahubctl schema load` and `infrahubctl schema check` accept this field and ignore it.
