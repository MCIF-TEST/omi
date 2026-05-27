# @omisphere/shared

Shared TypeScript types between `apps/web` and `apps/api`.

**Phase 1 status:** placeholder. Types live inline in `apps/web/lib/api.ts`.

**Phase 1.5 plan:** generate `types.ts` from the FastAPI OpenAPI schema via
`openapi-typescript` so the two services can't drift.
