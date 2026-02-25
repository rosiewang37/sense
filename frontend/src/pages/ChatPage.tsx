import { Link } from 'react-router-dom';
import ChatInterface from '../components/chat/ChatInterface';

export default function ChatPage() {
  return (
    <div className="flex flex-col h-screen">
      <header className="bg-gray-900 text-white px-6 py-3 flex items-center justify-between">
        <h1 className="text-lg font-semibold">Sense</h1>
        <nav className="flex gap-4 text-sm">
          <Link to="/chat" className="text-white font-medium">Chat</Link>
          <Link to="/knowledge" className="text-gray-400 hover:text-white">Knowledge</Link>
          <Link to="/settings" className="text-gray-400 hover:text-white">Settings</Link>
        </nav>
      </header>
      <main className="flex-1 overflow-hidden bg-gray-50">
        <ChatInterface />
      </main>
    </div>
  );
}
