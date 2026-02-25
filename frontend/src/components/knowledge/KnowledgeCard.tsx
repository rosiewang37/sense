import type { KnowledgeObject } from '../../lib/types';

const TYPE_COLORS: Record<string, string> = {
  decision: 'bg-blue-100 text-blue-700',
  change: 'bg-green-100 text-green-700',
  approval: 'bg-purple-100 text-purple-700',
  blocker: 'bg-red-100 text-red-700',
  context: 'bg-gray-100 text-gray-700',
};

interface KnowledgeCardProps {
  ko: KnowledgeObject & { verification_summary?: { total: number; verified: number; missing: number } | null };
  onClick?: () => void;
}

export default function KnowledgeCard({ ko, onClick }: KnowledgeCardProps) {
  const typeColor = TYPE_COLORS[ko.type] || TYPE_COLORS.context;
  const vs = ko.verification_summary;

  let verificationBadge = null;
  if (vs && vs.total > 0) {
    if (vs.missing === 0) {
      verificationBadge = <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700">Verified</span>;
    } else if (vs.verified > 0) {
      verificationBadge = <span className="text-xs px-2 py-0.5 rounded-full bg-yellow-100 text-yellow-700">Partial</span>;
    } else {
      verificationBadge = <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-700">Missing</span>;
    }
  }

  return (
    <div
      onClick={onClick}
      className="bg-white border rounded-lg p-4 hover:shadow-md transition-shadow cursor-pointer"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${typeColor}`}>
              {ko.type}
            </span>
            {verificationBadge}
            <span className="text-xs text-gray-400">
              {Math.round(ko.confidence * 100)}% confidence
            </span>
          </div>
          <h3 className="font-medium text-gray-900 truncate">{ko.title}</h3>
          {ko.summary && (
            <p className="text-sm text-gray-500 mt-1 line-clamp-2">{ko.summary}</p>
          )}
        </div>
      </div>
      {ko.tags && ko.tags.length > 0 && (
        <div className="flex gap-1 mt-2 flex-wrap">
          {ko.tags.map((tag) => (
            <span key={tag} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
              {tag}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
