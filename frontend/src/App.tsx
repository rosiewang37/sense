import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ChatPage from './pages/ChatPage';
import KnowledgePage from './pages/KnowledgePage';
import LoginPage from './pages/LoginPage';
import KnowledgeDetailPage from './pages/KnowledgeDetailPage';
import SettingsPage from './pages/SettingsPage';

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/knowledge" element={<KnowledgePage />} />
          <Route path="/knowledge/:id" element={<KnowledgeDetailPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/" element={<Navigate to="/chat" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
