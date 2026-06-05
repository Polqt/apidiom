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
      disable404Route: true,
      sidebar: [
        {
          label: 'Start Here',
          items: [
            { label: 'Intro', link: '/' },
            { label: 'Quickstart', slug: 'quickstart' },
          ],
        },
        {
          label: 'Using apidiom',
          items: [
            { label: 'Providers & Privacy', slug: 'providers-privacy' },
            { label: 'Unverified Fields', slug: 'unverified-fields' },
            { label: 'Web UI', slug: 'web-ui' },
            { label: 'Troubleshooting', slug: 'troubleshooting' },
          ],
        },
      ],
    }),
  ],
});
