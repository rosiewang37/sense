import type { ChatMessage } from '../../lib/types';

const TOOL_LABELS: Record<string, string> = {
  search_knowledge_base: 'Searching knowledge base',
  search_raw_events: 'Searching raw events',
  get_knowledge_detail: 'Getting knowledge details',
  get_verification_status: 'Checking verification status',
};

export default function AgentStep({ step }: { step: ChatMessage }) {
  const label = TOOL_LABELS[step.tool || ''] || step.tool || 'Processing';
  const isComplete = step.status === 'complete';

  return (
    <div className="flex items-center gap-2 text-sm text-gray-500 py-1">
      <span className={`w-2 h-2 rounded-full ${isComplete ? 'bg-green-400' : 'bg-yellow-400 animate-pulse'}`} />
      <span>{label}</span>
      {step.result_preview && (
        <span className="text-gray-400 truncate max-w-xs">— {step.result_preview}</span>
      )}
    </div>
  );
}
