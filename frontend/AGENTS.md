# Frontend — Intent

## Purpose
React 19 SPA for chat interface and knowledge dashboard.

## Scope
`frontend/` and all subdirectories.

## Entry Points
- `src/main.tsx` — React root, router setup
- `src/App.tsx` — Route definitions, layout

## Pages
- `ChatPage` → `ChatInterface` — investigative agent chat with reasoning toggle
- `KnowledgePage` → KO list with type filters, auto-refresh 5s
- `KnowledgeDetailPage` → full KO view + ContextPanel + VerificationPanel
- `SettingsPage` — placeholder (Phase 2)
- `LoginPage` — JWT authentication

## Contracts / Invariants
- API client: `lib/api.ts` — all backend calls go through this module
- Types: `lib/types.ts` — TypeScript interfaces matching backend responses
- Data hooks use TanStack Query with auto-refresh:
  - `useKnowledge()` — refetches every 5s
  - `useChat()` — SSE streaming from `/api/chat`
- Vite proxy config: `/api`, `/webhooks`, `/health` → `http://localhost:8000`

## Canonical Patterns
```typescript
// Data hook pattern
const { data, isLoading } = useQuery({
  queryKey: ['knowledge', filters],
  queryFn: () => api.getKnowledge(filters),
  refetchInterval: 5000,
});

// SSE streaming for chat
const response = await fetch('/api/chat', { method: 'POST', body: JSON.stringify({ question }) });
const reader = response.body.getReader();
```

## Anti-Patterns
- Direct `fetch()` calls bypassing `lib/api.ts`
- Hardcoded API URLs (use Vite proxy)
- Polling faster than 5s (causes unnecessary load)
- Adding state management libraries (TanStack Query is sufficient)

## Dependencies
- React 19, Vite 7, TailwindCSS 4, TanStack Query 5
- No test framework currently configured for frontend
- Build: `npm run build` (tsc + vite build)
- Lint: `npm run lint` (ESLint)
