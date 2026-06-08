import { existsSync } from 'fs';
import { join } from 'path';

/**
 * Detects the base directory containing the docs content (python-sdk/, infrahubctl/, etc.).
 *
 * The sidebar files live in different locations depending on which repo they are in:
 *   - infrahub-sdk-python: docs/sidebars/ → content is at docs/docs/
 *   - infrahub-docs:       docs/           → content is at docs/docs-python-sdk/
 *
 * We detect the active layout by checking whether the SDK-repo content path exists.
 */
export function getDocsBaseDir(): string {
  const sdkRepoDocsDir = join(__dirname, '..', 'docs');
  if (existsSync(join(sdkRepoDocsDir, 'python-sdk'))) {
    return sdkRepoDocsDir;
  }
  return join(__dirname, 'docs-python-sdk');
}

export function getCommandItems(files: string[], indexFile: string = 'infrahubctl.mdx'): string[] {
  return files
    .filter(file => file.endsWith('.mdx') && file !== indexFile)
    .map(file => file.replace('.mdx', ''))
    .sort();
}

export function getItemsWithOrder(files: string[], orderedIds: string[], prefix: string = ''): string[] {
  const allIds = files
    .filter(file => file.endsWith('.mdx'))
    .map(file => {
      const base = file.replace('.mdx', '');
      return prefix ? `${prefix}/${base}` : base;
    });

  const existingIds = new Set(allIds);
  const ordered = orderedIds.filter(id => existingIds.has(id));

  const orderedSet = new Set(orderedIds);
  const remaining = allIds.filter(id => !orderedSet.has(id)).sort();

  return [...ordered, ...remaining];
}
