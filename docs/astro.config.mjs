import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

const skipSitemapUntilSiteUrlExists = {
  name: '@astrojs/sitemap',
  hooks: {},
};

export default defineConfig({
  integrations: [
    skipSitemapUntilSiteUrlExists,
    starlight({
      title: 'apidiom',
      customCss: ['./src/styles/custom.css'],
      components: {
        Head: './src/components/Head.astro',
        SidebarSublist: './src/components/SidebarSublist.astro',
        ThemeSelect: './src/components/ThemeSelect.astro',
      },
      disable404Route: true,
      sidebar: [
        {
          label: 'Get Started',
          items: [
            { label: 'Quickstart', slug: 'quickstart' },
          ],
        },
        {
          label: 'Reference',
          items: [
            { label: 'MCP Server', slug: 'mcp-server' },
            { label: 'JSON Schema Export', slug: 'schema-export' },
          ],
        },
        {
          label: 'Troubleshooting',
          items: [
            { label: 'Troubleshooting', slug: 'troubleshooting' },
          ],
        },
      ],
    }),
  ],
});
