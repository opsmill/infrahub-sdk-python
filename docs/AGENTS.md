# docs/AGENTS.md

Docusaurus documentation following Diataxis framework.

## Commands

```bash
cd docs && npm install              # Install deps
cd docs && npm start                # Dev server at localhost:3000
cd docs && npm run build            # Build static site
uv run invoke docs                  # Generate auto-docs
uv run invoke docs-validate         # Validate docs are current
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

## Adding Documentation

1. Create MDX file in appropriate directory
2. Add frontmatter with `title`
3. Update `sidebars-*.ts` for navigation

## MDX Pattern

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
- Run `uv run invoke docs-validate` after code changes

🚫 **Never**

- Edit `docs/infrahubctl/*.mdx` directly (regenerate with `uv run invoke generate-infrahubctl`)
- Edit `docs/python-sdk/reference/config.mdx` directly (regenerate with `uv run invoke generate-sdk`)
