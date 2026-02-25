import { useState } from 'react';
import { useChat } from '../../hooks/useChat';
import AgentStep from './AgentStep';

export default function ChatInterface() {
  const { messages, isLoading, sendMessage } = useChat();
  const [input, setInput] = useState('');
  const [showReasoning, setShowReasoning] = useState(true);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || isLoading) return;
    sendMessage(input.trim());
    setInput('');
  }

  return (
    <div className="flex flex-col h-full">
      {/* Reasoning toggle */}
      <div className="px-4 py-2 border-b flex items-center justify-between bg-white">
        <span className="text-sm text-gray-500">Agent Reasoning</span>
        <button
          onClick={() => setShowReasoning(!showReasoning)}
          className={`text-sm px-3 py-1 rounded-full ${
            showReasoning ? 'bg-gray-900 text-white' : 'bg-gray-200 text-gray-600'
          }`}
        >
          {showReasoning ? 'ON' : 'OFF'}
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-400 mt-20">
            <p className="text-lg font-medium">Ask Sense anything</p>
            <p className="text-sm mt-2">Try: "Why did we switch motor suppliers?"</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-2xl rounded-lg px-4 py-3 ${
                msg.role === 'user'
                  ? 'bg-gray-900 text-white'
                  : 'bg-white border shadow-sm'
              }`}
            >
              {/* Agent reasoning steps */}
              {msg.role === 'assistant' && showReasoning && msg.steps && msg.steps.length > 0 && (
                <div className="mb-3 pb-3 border-b border-gray-100">
                  {msg.steps.map((step, j) => (
                    <AgentStep key={j} step={step} />
                  ))}
                </div>
              )}
              {/* Message content */}
              <div className="whitespace-pre-wrap">{msg.content}</div>
            </div>
          </div>
        ))}
        {isLoading && messages[messages.length - 1]?.role === 'user' && (
          <div className="flex justify-start">
            <div className="bg-white border shadow-sm rounded-lg px-4 py-3 text-gray-400">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 bg-yellow-400 rounded-full animate-pulse" />
                Investigating...
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="p-4 border-t bg-white">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about your project history..."
            className="flex-1 px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-gray-900"
            disabled={isLoading}
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="px-6 py-2 bg-gray-900 text-white rounded-lg hover:bg-gray-800 disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </form>
    </div>
  );
}
