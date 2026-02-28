import { Link, useNavigate } from 'react-router-dom';
import ChatInterface from '../components/chat/ChatInterface';
import type { ChatState } from '../hooks/useChat';

interface ChatPageProps {
  chatState: ChatState;
  setChatState: React.Dispatch<React.SetStateAction<ChatState>>;
}

export default function ChatPage({ chatState, setChatState }: ChatPageProps) {
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
          <Link to="/chat" className="text-white font-medium">Chat</Link>
          <Link to="/knowledge" className="text-gray-400 hover:text-white">Knowledge</Link>
          <Link to="/settings" className="text-gray-400 hover:text-white">Settings</Link>
          <button onClick={logout} className="text-gray-400 hover:text-white ml-2">Logout</button>
        </nav>
      </header>
      <main className="flex-1 overflow-hidden bg-gray-50">
        <ChatInterface chatState={chatState} setChatState={setChatState} />
      </main>
    </div>
  );
}
