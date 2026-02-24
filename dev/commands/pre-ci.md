Run a subset of fast CI checks locally. These are lightweight validations that catch common issues before pushing. Run all steps and report a summary at the end.

## Steps

1. **Format** Python code:
   ```bash
   uv run invoke format
   ```

2. **Lint** (YAML, Ruff, ty, mypy, markdownlint, vale):
   ```bash
   uv run invoke lint
   ```

3. **Python unit tests**:
   ```bash
   uv run pytest tests/unit/
   ```

4. **Docs unit tests** (vitest):
   ```bash
   (cd docs && npx --no-install vitest run)
   ```

5. **Validate generated documentation** (regenerate and check for drift):
   ```bash
   uv run invoke docs-validate
   ```

## Instructions

- Run each step in order using the Bash tool.
- If a step fails, continue with the remaining steps.
- At the end, print a summary table of all steps with pass/fail status.
- Do NOT commit or push anything.
