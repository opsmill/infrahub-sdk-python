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
