export interface KnowledgeObject {
  id: string;
  type: 'decision' | 'change' | 'approval' | 'blocker' | 'context';
  title: string;
  summary: string | null;
  detail: Record<string, unknown> | null;
  participants: Array<{ email: string; name?: string }> | null;
  tags: string[] | null;
  confidence: number;
  status: string;
  detected_at: string;
  occurred_at: string | null;
  project_id: string | null;
  verification_checks?: VerificationCheck[];
}

export interface VerificationCheck {
  id: string;
  knowledge_id: string;
  description: string;
  status: 'verified' | 'missing' | 'unknown';
  evidence: string | null;
  suggestion: string | null;
  checked_at: string;
}

export interface ChatMessage {
  type: 'text' | 'agent_step';
  content?: string;
  tool?: string;
  status?: string;
  result_preview?: string;
}

export interface User {
  id: string;
  email: string;
  name: string | null;
}
