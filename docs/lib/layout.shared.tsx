import type { BaseLayoutProps } from 'fumadocs-ui/layouts/shared';

export function baseOptions(): BaseLayoutProps {
  return {
    nav: {
      title: 'Mercatorgraph Docs',
    },
    links: [
      {
        text: 'GitHub',
        url: 'https://github.com/dimsmaul/mercatorgraph',
        external: true,
      },
    ],
  };
}
