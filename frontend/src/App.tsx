import { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ChatPage from './pages/ChatPage';
import KnowledgePage from './pages/KnowledgePage';
import LoginPage from './pages/LoginPage';
import KnowledgeDetailPage from './pages/KnowledgeDetailPage';
import SettingsPage from './pages/SettingsPage';
import { type ChatState, initialChatState } from './hooks/useChat';

const queryClient = new QueryClient();

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem('token');
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

export default function App() {
  // Chat state lives here so it survives navigation between pages
  const [chatState, setChatState] = useState<ChatState>(initialChatState);

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/chat"
            element={
              <RequireAuth>
                <ChatPage chatState={chatState} setChatState={setChatState} />
              </RequireAuth>
            }
          />
          <Route path="/knowledge" element={<RequireAuth><KnowledgePage /></RequireAuth>} />
          <Route path="/knowledge/:id" element={<RequireAuth><KnowledgeDetailPage /></RequireAuth>} />
          <Route path="/settings" element={<RequireAuth><SettingsPage /></RequireAuth>} />
          <Route path="/" element={<Navigate to="/login" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
