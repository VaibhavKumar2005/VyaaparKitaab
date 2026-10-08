# Frontend Upgrade Summary

The frontend is ready for a production-style upgrade, but the work should happen in layers rather than as a full rewrite.

## The Short Version
- Keep the current routing structure.
- Add a typed API client and query layer.
- Move forms to React Hook Form and Zod.
- Standardize loading, error, and empty states.
- Add accessible UI primitives before visual polish.

## The Practical Priority Order
1. Data layer
2. Forms
3. Shared components
4. Dashboard and list refactors
5. Motion, polish, and accessibility

## What Not To Do
- Do not scatter fetch logic through pages.
- Do not build one-off form handling per screen.
- Do not validate API payloads in multiple places.
- Do not add design libraries before the core data layer exists.

## Copy-First Rule
Start with one form and one dashboard screen. If those two are clean, the rest of the app can follow the same pattern with much less risk.
