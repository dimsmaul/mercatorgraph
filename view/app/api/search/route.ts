import { source } from '@/lib/source';
import { createFromSource } from 'fumadocs-core/search/server';

// Built-in Orama search over all generated MDX -> cross-project search.
export const { GET } = createFromSource(source);
