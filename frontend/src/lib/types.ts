export interface KnowledgeEventContextMessage {
  user_name: string;
  text: string;
  ts: string;
}

export interface KnowledgeEventAttachment {
  id: string;
  name: string;
  filetype?: string;
  mimetype?: string;
  url_private?: string;
  permalink?: string;
}

export interface KnowledgeEventMetadata {
  channel?: string | null;
  thread_ts?: string | null;
  file_ids?: string[];
  actor_display_name?: string;
  context_messages?: KnowledgeEventContextMessage[];
  attachments?: KnowledgeEventAttachment[];
  [key: string]: unknown;
}

export interface KnowledgeSourceEvent {
  id: string;
  source: string;
  source_id: string;
  event_type: string;
  actor_name: string | null;
  content: string | null;
  occurred_at: string;
  relationship: string | null;
  relevance: number | null;
  metadata: KnowledgeEventMetadata | null;
}

export interface KnowledgeObject {
  id: string;
  type: 'decision' | 'change' | 'approval' | 'blocker' | 'context';
  title: string;
  summary: string | null;
  detail: Record<string, unknown> | null;
  participants: Array<{ email: string; name?: string; role?: string }> | null;
  tags: string[] | null;
  confidence: number;
  status: string;
  detected_at: string;
  occurred_at: string | null;
  project_id: string | null;
  source_events?: KnowledgeSourceEvent[];
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
