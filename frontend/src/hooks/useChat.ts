import { useCallback, useEffect, useRef } from 'react';

export interface ChatStep {
  type: 'agent_step';
  tool: string;
  status: string;
  result_preview: string;
}

export interface ChatSource {
  type: string;
  id: string;
  label: string;
  detail: string;
}

export interface ChatMessage {
  id?: string;
  role: 'user' | 'assistant';
  content: string;
  steps?: ChatStep[];
  sources?: ChatSource[];
  created_at?: string;
}

export interface ChatState {
  messages: ChatMessage[];
  isLoading: boolean;
  historyLoaded: boolean;
}

export const initialChatState = (): ChatState => ({
  messages: [],
  isLoading: false,
  historyLoaded: false,
});

/**
 * useChat — manages conversation with the Sense investigative agent.
 *
 * State lives in the parent (App) so it survives navigation between pages.
 * - Loads history from the backend on first use.
 * - Streams new responses from /api/chat.
 */
export function useChat(
  state: ChatState,
  setState: React.Dispatch<React.SetStateAction<ChatState>>,
) {
  const loadingRef = useRef(false);

  // Load chat history once on first mount
  useEffect(() => {
    if (state.historyLoaded || loadingRef.current) return;
    loadingRef.current = true;

    (async () => {
      try {
        const token = localStorage.getItem('token');
        const res = await fetch('/api/chat/history', {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) return;
        const history: ChatMessage[] = await res.json();
        setState(prev => ({
          ...prev,
          historyLoaded: true,
          messages: history.length > 0 ? history : prev.messages,
        }));
      } catch {
        setState(prev => ({ ...prev, historyLoaded: true }));
      }
    })();
  }, [state.historyLoaded, setState]);

  const sendMessage = useCallback(
    async (question: string, projectId?: string) => {
      if (state.isLoading) return;

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
        const steps: ChatStep[] = [];
        let sources: ChatSource[] = [];
        let answer = '';

        // Add assistant placeholder so UI shows "Investigating..." immediately
        setState(prev => ({
          ...prev,
          messages: [...prev.messages, { role: 'assistant', content: '', steps: [] }],
        }));

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          for (const line of chunk.split('\n').filter(Boolean)) {
            try {
              const event = JSON.parse(line);
              if (event.type === 'agent_step') {
                steps.push(event as ChatStep);
              } else if (event.type === 'text') {
                answer += event.content || '';
              } else if (event.type === 'sources') {
                sources = event.sources || [];
              }
            } catch {
              // skip malformed lines
            }
          }

          // Update the trailing assistant message in real time
          setState(prev => {
            const msgs = [...prev.messages];
            const last = msgs[msgs.length - 1];
            if (last?.role === 'assistant') {
              msgs[msgs.length - 1] = { ...last, content: answer, steps: [...steps], sources: sources.length > 0 ? [...sources] : undefined };
            }
            return { ...prev, messages: msgs };
          });
        }

        // Final state — mark loading done
        setState(prev => {
          const msgs = [...prev.messages];
          const last = msgs[msgs.length - 1];
          if (last?.role === 'assistant') {
            msgs[msgs.length - 1] = { role: 'assistant', content: answer, steps, sources: sources.length > 0 ? sources : undefined };
          }
          return { messages: msgs, isLoading: false, historyLoaded: prev.historyLoaded };
        });
      } catch {
        setState(prev => ({
          ...prev,
          isLoading: false,
          messages: [
            ...prev.messages,
            { role: 'assistant', content: 'Sorry, something went wrong.' },
          ],
        }));
      }
    },
    [state.isLoading, setState],
  );

  return { messages: state.messages, isLoading: state.isLoading, sendMessage };
}
