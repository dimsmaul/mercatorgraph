import { defineConfig, defineDocs } from 'fumadocs-mdx/config';
import { pageSchema, metaSchema } from 'fumadocs-core/source/schema';
import { z } from 'zod';

// extend the default page frontmatter with graph metadata written by ckdocs
export const docs = defineDocs({
  dir: 'content/docs',
  docs: {
    schema: pageSchema.extend({
      project: z.string().optional(),
      cluster: z.string().nullable().optional(),
      confidence: z.string().nullable().optional(),
      graph_version: z.string().optional(),
      tags: z.array(z.string()).optional(),
    }),
  },
  meta: {
    schema: metaSchema,
  },
});

export default defineConfig();
