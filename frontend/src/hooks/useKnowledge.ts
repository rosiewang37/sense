import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';
import type { KnowledgeObject } from '../lib/types';

interface KnowledgeListResponse {
  items: KnowledgeObject[];
  total: number;
  offset: number;
  limit: number;
}

export function useKnowledgeList(filters?: {
  type?: string;
  status?: string;
  project_id?: string;
}) {
  const params = new URLSearchParams();
  if (filters?.type) params.set('type', filters.type);
  if (filters?.status) params.set('status', filters.status);
  if (filters?.project_id) params.set('project_id', filters.project_id);
  const qs = params.toString();

  return useQuery({
    queryKey: ['knowledge', qs],
    queryFn: () => api.get<KnowledgeListResponse>(`/knowledge${qs ? `?${qs}` : ''}`),
    // Auto-refresh every 5 seconds so new KOs appear quickly during testing.
    // TODO: Increase to 30s+ in production to reduce server load.
    refetchInterval: 5_000,
  });
}

export function useKnowledgeDetail(id: string) {
  return useQuery({
    queryKey: ['knowledge', id],
    queryFn: () => api.get<KnowledgeObject>(`/knowledge/${id}`),
    enabled: !!id,
  });
}
