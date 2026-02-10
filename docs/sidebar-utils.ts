export function getCommandItems(files: string[], indexFile: string = 'infrahubctl.mdx'): string[] {
  return files
    .filter(file => file.endsWith('.mdx') && file !== indexFile)
    .map(file => file.replace('.mdx', ''))
    .sort();
}
