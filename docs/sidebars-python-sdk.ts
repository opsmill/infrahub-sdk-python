import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  pythonSdkSidebar: [
    {
      type: 'category',
      label: 'Python SDK docs',
      link: {
        type: 'doc',
        id: 'introduction',
      },
      items: [
        {
          type: 'category',
          label: 'Guides',
          items: [
            'guides/installation',
            'guides/client',
            'guides/query_data',
            'guides/create_update_delete',
            'guides/branches',
            'guides/store',
            'guides/tracking',
            'guides/batch',
            'guides/object-storage',
            'guides/resource-manager',
          ],
        },
        {
          type: 'category',
          label: 'Topics',
          items: [
            'topics/tracking',
          ],
        },
        {
          type: 'category',
          label: 'Reference',
          items: [
            'reference/config',
            'reference/templating',
          ],
        },
      ],
    },
  ],
};

export default sidebars;