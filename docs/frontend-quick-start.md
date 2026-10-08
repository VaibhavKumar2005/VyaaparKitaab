# Frontend Quick Start

1. Install the upgrade dependencies.
2. Create a shared query client and API client.
3. Replace one form with React Hook Form plus Zod.
4. Replace one dashboard page with a query-driven version.
5. Add toasts and a reusable error state.
6. Repeat the pattern page by page.

## First Copy-Paste Targets
- `frontend/src/lib/apiClient.ts`
- `frontend/src/lib/queryClient.ts`
- `frontend/src/components/forms/LoginForm.tsx`
- `frontend/src/components/ui/ErrorState.tsx`
- `frontend/src/components/ui/LoadingState.tsx`

## Recommended Install Command
```bash
cd frontend
npm install @tanstack/react-query axios react-hook-form zod @hookform/resolvers sonner framer-motion lucide-react @radix-ui/react-dialog @radix-ui/react-select @radix-ui/react-tabs
```
