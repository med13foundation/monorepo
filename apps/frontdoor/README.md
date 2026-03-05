# Artana.bio Front Door Website

Public-facing marketing and onboarding website for Artana.bio.

## Local development

```bash
cd apps/frontdoor
npm ci
npm run dev
```

Default local URL: `http://localhost:3010`

## Scripts

- `npm run dev` - start development server
- `npm run build` - production build
- `npm run start` - run production server
- `npm run lint` - lint checks
- `npm run type-check` - TypeScript checks
- `npm run test` - unit tests

## Environment variables

Copy `.env.example` to `.env.local` and set values:

- `NEXT_PUBLIC_API_BASE_URL`
- `NEXT_PUBLIC_ADMIN_URL`
- `NEXT_PUBLIC_DOCS_URL`
- `NEXT_PUBLIC_SITE_URL`
- `NEXT_PUBLIC_GA_MEASUREMENT_ID` (optional)
- `CONTACT_FORM_ENDPOINT` (server-only)

## Service boundaries

- This app must not import runtime code from `src/web`.
- Backend communication is HTTP-only.
- No PHI collection in public forms.
