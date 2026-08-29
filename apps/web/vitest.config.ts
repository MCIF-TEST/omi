import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

/**
 * The `@/` alias the app uses everywhere. Without it a test can only import modules that happen to
 * use relative paths, which quietly limits what is testable to whatever avoided the alias.
 */
export default defineConfig({
  resolve: {
    alias: { '@': fileURLToPath(new URL('.', import.meta.url)) },
  },
});
