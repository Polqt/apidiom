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
        SidebarSublist: './src/components/SidebarSublist.astro',
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
          label: 'Concepts',
          items: [
            { label: 'Providers & Privacy', slug: 'providers-privacy' },
            { label: 'Unverified Fields', slug: 'unverified-fields' },
          ],
        },
        {
          label: 'Reference',
          items: [
            { label: 'Web UI', slug: 'web-ui' },
            { label: 'MCP Server', slug: 'mcp-server' },
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
