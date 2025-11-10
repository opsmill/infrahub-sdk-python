import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';
import globalVars from './globalVars';
import path from 'path';

const config: Config = {
  title: 'Tools & SDKs for Infrahub',
  tagline: 'Tools & SDKs',
  favicon: 'img/favicon.ico',

  // Set the production url of your site here
  url: 'https://your-docusaurus-site.example.com',
  // Set the /<baseUrl>/ pathname under which your site is served
  // For GitHub pages deployment, it is often '/<projectName>/'
  baseUrl: '/',

  organizationName: 'opsmill',
  projectName: 'infrahub-sdk-python',
  onBrokenLinks: 'throw',
  onDuplicateRoutes: "throw",
  // Even if you don't use internationalization, you can use this field to set
  // useful metadata like html lang. For example, if your site is Chinese, you
  // may want to replace "en" with "zh-Hans".
  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      "classic",
      {
        docs: {
          // Please change this to your repo.
          // Remove this to remove the "edit this page" links.
          editUrl: "https://github.com/opsmill/infrahub-sdk-python/tree/stable/docs",
          path: 'docs/python-sdk',
          routeBasePath: 'python-sdk',
          sidebarPath: './sidebars-python-sdk.ts',
          sidebarCollapsed: true,
        },
        blog: false,
        theme: {
          customCss: "./src/css/custom.css",
        },
      } satisfies Preset.Options,
    ],
  ],
  plugins: [
    [
      '@docusaurus/plugin-content-docs',
      {
        id: 'infrahubctl',
        path: 'docs/infrahubctl',
        routeBasePath: 'infrahubctl',
        sidebarCollapsed: false,
        sidebarPath: './sidebars-infrahubctl.ts',
      },
    ],
  ],
  themeConfig: {
    // announcementBar: {
    //   content: 'Welcome to our brand new docs!',
    //   isCloseable: true,
    // },
    navbar: {
      logo: {
        alt: "Infrahub",
        src: "img/infrahub-hori.svg",
        srcDark: "img/infrahub-hori-dark.svg",
      },
      items: [
        {
          type: 'dropdown',
          position: 'left',
          label: 'Tools & SDKs',
          items: [
            {
              type: "docSidebar",
              sidebarId: "pythonSdkSidebar",
              label: "Python SDK",
            },
            {
              type: "docSidebar",
              sidebarId: "infrahubctlSidebar",
              label: "Infrahubctl",
              docsPluginId: "infrahubctl",
            },
          ],
        },
        // {
        //   type: "search",
        //   position: "right",
        // },
        {
          href: "https://github.com/opsmill/infrahub-sdk-python",
          position: "right",
          className: "header-github-link",
          "aria-label": "GitHub repository",
        },
      ],
    },
    footer: {
      copyright: `Copyright © ${new Date().getFullYear()} - <b>Infrahub</b> by OpsMill.`,
    },
    prism: {
      theme: prismThemes.oneDark,
      additionalLanguages: ["bash", "python", "markup-templating", "django", "json", "toml", "yaml"],
    },
  } satisfies Preset.ThemeConfig,

  markdown: {
    format: "mdx",
    preprocessor: ({ filePath, fileContent }) => {
      console.log(`Processing ${filePath}`);
      const transformedContent = fileContent.replace(/\$\(\s*(\w+)\s*\)/g, (match, variableName) => {
        if (variableName === 'base_url' && globalVars.base_url === 'RELATIVE') {
          return getDocsRelative(filePath);
        }
        return globalVars[variableName] || match;
      });
      return transformedContent;
    },
    hooks: {
      onBrokenMarkdownLinks: 'warn',
    },
  },
};

function getDocsRelative(filePath) {
  const rootDocsDir = path.join(process.cwd(), 'docs');
  const currentDir = path.dirname(filePath);
  const nestedDocsDir = path.join(rootDocsDir, 'docs');
  const relativePath = path.relative(currentDir, nestedDocsDir);
  const segments = relativePath.split(path.sep);
  return '../'.repeat(segments.length - 1);
}

export default config;
