import type { VerificationCheck } from '../../lib/types';

const STATUS_ICON: Record<string, string> = {
  verified: 'text-green-500',
  missing: 'text-red-500',
  unknown: 'text-gray-400',
};

const STATUS_SYMBOL: Record<string, string> = {
  verified: '\u2713',
  missing: '\u2717',
  unknown: '?',
};

export default function VerificationPanel({ checks }: { checks: VerificationCheck[] }) {
  if (checks.length === 0) {
    return <p className="text-sm text-gray-400">No verification checks yet.</p>;
  }

  return (
    <div className="space-y-3">
      <h3 className="font-medium text-gray-900">Verification Status</h3>
      {checks.map((check) => (
        <div key={check.id} className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg">
          <span className={`text-lg font-bold ${STATUS_ICON[check.status]}`}>
            {STATUS_SYMBOL[check.status]}
          </span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-gray-900">{check.description}</p>
            {check.evidence && (
              <p className="text-xs text-gray-500 mt-1">Evidence: {check.evidence}</p>
            )}
            {check.suggestion && (
              <p className="text-xs text-amber-600 mt-1">Suggestion: {check.suggestion}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
