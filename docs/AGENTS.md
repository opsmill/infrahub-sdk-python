# Documentation agents

Docusaurus documentation following Diataxis framework.

## Commands

```bash
cd docs && npm install              # Install deps
cd docs && npm start                # Dev server at localhost:3000
cd docs && npm run build            # Build static site
cd docs && npm test                 # Run sidebar utility tests
uv run invoke docs                  # Build documentation website
uv run invoke docs-generate         # Regenerate all docs (infrahubctl CLI + Python SDK)
uv run invoke docs-validate         # Check that generated docs match committed files
```

## Structure

```text
docs/docs/
├── python-sdk/
│   ├── guides/      # How-to guides (task-oriented)
│   ├── topics/      # Explanations (concept-oriented)
│   └── reference/   # API reference (auto-generated)
└── infrahubctl/     # CLI docs (auto-generated)
```

## Sidebars

Sidebar navigation is dynamic: `sidebars-*.ts` files read the filesystem at build time via utility functions in `sidebar-utils.ts`.

- **infrahubctl**: all `.mdx` files are discovered automatically and sorted alphabetically.
- **python-sdk**: guides, topics, and reference sections preserve a defined display order; new files are appended alphabetically at the end.

No manual sidebar update is needed when adding a new `.mdx` file. However, to control the display order of a new page, add its doc ID to the ordered list in the corresponding `sidebars-*.ts` file.

## Adding documentation

1. Create MDX file in appropriate directory
2. Add frontmatter with `title`

## MDX pattern

Use Tabs for async/sync examples, callouts for notes:

```mdx
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

<Tabs>
  <TabItem value="async" label="Async">...</TabItem>
  <TabItem value="sync" label="Sync">...</TabItem>
</Tabs>

:::warning
Use callouts for important notes.
:::
```

## Boundaries

✅ **Always**

- Include both async/sync examples using Tabs
- Run `uv run invoke docs-validate` after code changes to verify generated docs are up to date

🚫 **Never**

- Edit `docs/infrahubctl/*.mdx` directly (regenerate with `uv run invoke docs-generate`)
- Edit `docs/python-sdk/reference/config.mdx` directly (regenerate with `uv run invoke docs-generate`)
- Edit `docs/python-sdk/reference/templating.mdx` directly (regenerate with `uv run invoke docs-generate`)
- Edit `docs/python-sdk/sdk_ref/**/*.mdx` directly (regenerate with `uv run invoke docs-generate`)
