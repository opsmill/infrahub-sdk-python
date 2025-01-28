import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  infrahubctlSidebar: [
    {
      type: 'doc',
      id: 'infrahubctl',
      label: 'Infrahubctl CLI Tool',
    },
    {
      type: 'category',
      label: 'Commands',
      items: [
        'infrahubctl-branch',
        'infrahubctl-check',
        'infrahubctl-dump',
        'infrahubctl-generator',
        'infrahubctl-info',
        'infrahubctl-load',
        'infrahubctl-menu',
        'infrahubctl-object',
        'infrahubctl-protocols',
        'infrahubctl-render',
        'infrahubctl-repository',
        'infrahubctl-run',
        'infrahubctl-schema',
        'infrahubctl-transform',
        'infrahubctl-validate',
        'infrahubctl-version'
      ],
    },
  ],
};

export default sidebars;