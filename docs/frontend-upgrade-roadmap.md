# Frontend Upgrade Roadmap

## Week 1
- Install the core upgrade libraries.
- Add a shared query client provider.
- Move API access into one client module.
- Add Zod schemas for auth and dashboard responses.

## Week 2
- Refactor login and registration into React Hook Form.
- Add reusable error, loading, and empty-state components.
- Replace page-level fetch calls with query hooks.

## Week 3
- Convert dashboard cards and list pages to query-driven views.
- Add accessible UI primitives for dialogs, selects, tabs, and menus.
- Introduce consistent table, badge, and card styles.

## Week 4
- Add subtle motion, toasts, and top-level error boundaries.
- Review keyboard navigation and screen reader behavior.
- Clean up route-level components so they stay thin.

## Done When
- API calls are centralized.
- Forms validate consistently.
- Shared UI is reused across pages.
- Loading and error states are uniform.
- The app survives refresh, retry, and navigation without losing state unexpectedly.
