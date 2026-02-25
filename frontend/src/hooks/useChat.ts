import { useState, useCallback } from 'react';
import type { ChatMessage } from '../lib/types';

interface ChatState {
  messages: Array<{ role: 'user' | 'assistant'; content: string; steps?: ChatMessage[] }>;
  isLoading: boolean;
}

export function useChat() {
  const [state, setState] = useState<ChatState>({ messages: [], isLoading: false });

  const sendMessage = useCallback(async (question: string, projectId?: string) => {
    setState(prev => ({
      ...prev,
      isLoading: true,
      messages: [...prev.messages, { role: 'user', content: question }],
    }));

    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ question, project_id: projectId }),
      });

      if (!res.ok) throw new Error('Chat request failed');

      const reader = res.body?.getReader();
      if (!reader) return;

      const decoder = new TextDecoder();
      const steps: ChatMessage[] = [];
      let answer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n').filter(Boolean);

        for (const line of lines) {
          try {
            const event: ChatMessage = JSON.parse(line);
            if (event.type === 'agent_step') {
              steps.push(event);
            } else if (event.type === 'text') {
              answer += event.content || '';
            }
          } catch {
            // Skip malformed lines
          }
        }

        // Update in real-time
        setState(prev => {
          const msgs = [...prev.messages];
          const lastIdx = msgs.length - 1;
          if (lastIdx >= 0 && msgs[lastIdx].role === 'assistant') {
            msgs[lastIdx] = { role: 'assistant', content: answer, steps: [...steps] };
          } else {
            msgs.push({ role: 'assistant', content: answer, steps: [...steps] });
          }
          return { ...prev, messages: msgs };
        });
      }

      // Final update
      setState(prev => {
        const msgs = [...prev.messages];
        const lastIdx = msgs.length - 1;
        if (lastIdx >= 0 && msgs[lastIdx].role === 'assistant') {
          msgs[lastIdx] = { role: 'assistant', content: answer, steps };
        }
        return { messages: msgs, isLoading: false };
      });
    } catch (err) {
      setState(prev => ({
        ...prev,
        isLoading: false,
        messages: [...prev.messages, { role: 'assistant', content: 'Sorry, something went wrong.' }],
      }));
    }
  }, []);

  return { ...state, sendMessage };
}
