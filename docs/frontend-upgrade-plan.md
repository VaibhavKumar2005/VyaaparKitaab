# Frontend Upgrade Plan

## Goal
Turn the current Vite + React frontend into a production-ready UI layer with predictable data fetching, typed API boundaries, accessible components, and a cleaner folder structure.

## Current Baseline
The app is already a solid foundation:
- React 19 with React Router
- Existing auth token flow and refresh endpoint
- Page-based routing for landing, auth, dashboard, invoices, customers, and products
- Basic data visualization via Recharts and 3D visualization via Three.js

What is still missing is the production layer around it:
- No dedicated query/cache layer
- No schema-validated API contracts
- No reusable form validation system
- No shared UI primitives or design tokens
- No standardized error, loading, and empty states

## Recommended Library Stack
Use these libraries as the upgrade baseline:
- `@tanstack/react-query` for caching, retries, refetch control, and background updates
- `axios` for a dedicated API client with token injection and refresh handling
- `react-hook-form` for fast form state and validation wiring
- `zod` for runtime validation and type-safe schemas
- `@hookform/resolvers` to connect Zod to React Hook Form
- `sonner` for lightweight toast notifications
- `framer-motion` for restrained page and component transitions
- `lucide-react` for a consistent icon set
- `@radix-ui/react-*` for accessible primitives like dialog, select, tabs, popover, dropdown menu, and tooltip
- `clsx` and `tailwind-merge` for class composition if utility classes remain part of the styling approach

## Architecture Pattern
Adopt a layered client structure:

- `lib/` for API clients, token helpers, and low-level utilities
- `schemas/` for Zod validation and API response definitions
- `hooks/` for query and mutation hooks
- `components/ui/` for reusable primitives
- `components/forms/` for form-specific components
- `pages/` for route-level screens only
- `features/` for domain-specific workflows when a page grows too large

This keeps route components thin and pushes business logic into hooks and feature modules.

## Production Patterns To Standardize
1. Server-state should live in TanStack Query, not local component state.
2. Form validation should happen through React Hook Form plus Zod, not ad hoc `useState` wiring.
3. API responses should be validated once at the boundary, then treated as trusted inside the app.
4. Shared UI primitives should be accessible by default, not hand-built per page.
5. Loading, error, and empty states should be first-class components.
6. Token refresh should happen in one central client, not scattered across pages.

## Suggested Folder Structure
```text
frontend/src/
  app/
    providers/
    routes/
  components/
    ui/
    forms/
    layout/
  features/
    auth/
    dashboard/
    invoices/
    customers/
    products/
  hooks/
  lib/
  schemas/
  styles/
  pages/
```

## Implementation Order
### Phase 1: Data Layer
- Add a query client provider
- Replace raw fetch usage with a single API client
- Move auth token refresh logic into the client boundary
- Add typed schemas for login, registration, invoices, and dashboard data

### Phase 2: Forms
- Replace page-level form state with React Hook Form
- Add reusable input, select, checkbox, and error components
- Validate login and registration flows with Zod
- Add submission states and toast feedback

### Phase 3: Dashboard and Lists
- Convert dashboard cards, lists, and charts to query-driven views
- Add loading skeletons and empty states
- Move filters and search into URL or query state where appropriate
- Introduce optimistic updates for safe mutations

### Phase 4: UI System
- Add Radix-based dialogs, tabs, and dropdowns
- Create a small design system around spacing, color, borders, and elevation
- Standardize table, badge, and card patterns

### Phase 5: Polish
- Add motion only where it improves perceived quality
- Add keyboard and screen-reader checks
- Add error boundaries and top-level fallback screens
- Add simple analytics or logging hooks if needed

## Files To Create First
- `frontend/src/lib/apiClient.ts`
- `frontend/src/lib/queryClient.ts`
- `frontend/src/schemas/auth.ts`
- `frontend/src/schemas/invoice.ts`
- `frontend/src/hooks/useAuthMutation.ts`
- `frontend/src/hooks/useDashboardQuery.ts`
- `frontend/src/components/forms/LoginForm.tsx`
- `frontend/src/components/ui/LoadingState.tsx`
- `frontend/src/components/ui/ErrorState.tsx`

## Risks To Avoid
- Do not spread fetch logic across pages.
- Do not duplicate token refresh code.
- Do not use local component state for server data that should be cached.
- Do not introduce too many libraries at once without shared abstractions.
- Do not refactor styling and behavior in the same pass if it will make debugging harder.

## Success Criteria
The upgrade is on track when:
- API calls are typed and centralized
- Forms have consistent validation and error handling
- Dashboard and list pages reuse query hooks
- Loading and empty states are uniform
- Routing remains simple and page components stay small
- The app feels stable under refresh, retry, and navigation
