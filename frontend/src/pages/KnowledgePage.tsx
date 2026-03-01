import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useKnowledgeList } from '../hooks/useKnowledge';
import KnowledgeCard from '../components/knowledge/KnowledgeCard';
import FilterBar from '../components/knowledge/FilterBar';

export default function KnowledgePage() {
  const [typeFilter, setTypeFilter] = useState('');
  const { data, isLoading, error } = useKnowledgeList({ type: typeFilter || undefined });
  const navigate = useNavigate();
  function logout() {
    localStorage.removeItem('token');
    navigate('/login');
  }

  return (
    <div className="flex flex-col h-screen">
      <header className="bg-gray-900 text-white px-6 py-3 flex items-center justify-between">
        <h1 className="text-lg font-semibold">Sense</h1>
        <nav className="flex gap-4 text-sm items-center">
          <Link to="/chat" className="text-gray-400 hover:text-white">Chat</Link>
          <Link to="/knowledge" className="text-white font-medium">Knowledge</Link>
          <Link to="/settings" className="text-gray-400 hover:text-white">Settings</Link>
          <button onClick={logout} className="text-gray-400 hover:text-white ml-2">Logout</button>
        </nav>
      </header>
      <main className="flex-1 overflow-y-auto bg-gray-50 p-6">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-semibold text-gray-900">Knowledge Feed</h2>
            <FilterBar type={typeFilter} onTypeChange={setTypeFilter} />
          </div>

          {isLoading && <p className="text-gray-400">Loading...</p>}
          {error && <p className="text-red-500">Failed to load knowledge objects.</p>}

          <div className="space-y-3">
            {data?.items?.map((ko) => (
              <KnowledgeCard
                key={ko.id}
                ko={ko}
                onClick={() => navigate(`/knowledge/${ko.id}`)}
              />
            ))}
            {data?.items?.length === 0 && !isLoading && (
              <p className="text-gray-400 text-center py-8">
                No knowledge objects captured yet. Connect Slack or GitHub to start.
              </p>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
