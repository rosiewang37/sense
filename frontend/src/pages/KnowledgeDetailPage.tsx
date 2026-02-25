import { useParams, Link } from 'react-router-dom';
import { useKnowledgeDetail } from '../hooks/useKnowledge';
import VerificationPanel from '../components/knowledge/VerificationPanel';

export default function KnowledgeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: ko, isLoading, error } = useKnowledgeDetail(id || '');

  if (isLoading) return <div className="p-8 text-gray-400">Loading...</div>;
  if (error || !ko) return <div className="p-8 text-red-500">Knowledge object not found.</div>;

  return (
    <div className="flex flex-col h-screen">
      <header className="bg-gray-900 text-white px-6 py-3 flex items-center justify-between">
        <h1 className="text-lg font-semibold">Sense</h1>
        <nav className="flex gap-4 text-sm">
          <Link to="/chat" className="text-gray-400 hover:text-white">Chat</Link>
          <Link to="/knowledge" className="text-gray-400 hover:text-white">Knowledge</Link>
          <Link to="/settings" className="text-gray-400 hover:text-white">Settings</Link>
        </nav>
      </header>
      <main className="flex-1 overflow-y-auto bg-gray-50 p-6">
        <div className="max-w-3xl mx-auto">
          <Link to="/knowledge" className="text-sm text-gray-500 hover:text-gray-700 mb-4 inline-block">
            &larr; Back to Knowledge Feed
          </Link>

          <div className="bg-white rounded-lg shadow p-6 mb-6">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 font-medium">
                {ko.type}
              </span>
              <span className="text-xs text-gray-400">{Math.round(ko.confidence * 100)}% confidence</span>
              <span className={`text-xs px-2 py-0.5 rounded-full ${
                ko.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
              }`}>
                {ko.status}
              </span>
            </div>

            <h2 className="text-xl font-semibold text-gray-900 mb-2">{ko.title}</h2>
            {ko.summary && <p className="text-gray-600 mb-4">{ko.summary}</p>}

            {ko.detail && (
              <div className="space-y-3 mb-4">
                {ko.detail.statement && (
                  <div>
                    <h4 className="text-sm font-medium text-gray-700">Statement</h4>
                    <p className="text-sm text-gray-600">{ko.detail.statement as string}</p>
                  </div>
                )}
                {ko.detail.rationale && (
                  <div>
                    <h4 className="text-sm font-medium text-gray-700">Rationale</h4>
                    <p className="text-sm text-gray-600">{ko.detail.rationale as string}</p>
                  </div>
                )}
                {(ko.detail.expected_follow_ups as string[])?.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium text-gray-700">Expected Follow-ups</h4>
                    <ul className="list-disc list-inside text-sm text-gray-600">
                      {(ko.detail.expected_follow_ups as string[]).map((f, i) => (
                        <li key={i}>{f}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {ko.tags && ko.tags.length > 0 && (
              <div className="flex gap-1 flex-wrap">
                {ko.tags.map((tag) => (
                  <span key={tag} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Verification Panel */}
          <div className="bg-white rounded-lg shadow p-6">
            <VerificationPanel checks={ko.verification_checks || []} />
          </div>
        </div>
      </main>
    </div>
  );
}
