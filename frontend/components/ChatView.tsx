'use client';

import React, { useState, useRef, useEffect } from 'react';
import { ChatMessage } from '@/lib/types';
import { postQuery, ApiError } from '@/lib/api';
import { MessageItem } from './MessageItem';
import { ErrorBanner } from './ErrorBanner';

interface ChatViewProps {
  onIndexedFilesCountChange?: () => void;
  activeSessionId?: string | null;
  onSessionCreated?: (sessionId: string) => void;
  onSessionsUpdated?: () => void;
}

const SAMPLE_QUESTIONS = [
  'Explain how a modern compiler processes the statement through all compilation phases in CAT-1.',
  'How many ports at end devices and total cables are needed for 5 devices in a Full Mesh Topology?',
  'What is the architecture and role of ChromaDB in this local RAG system?',
];

export const ChatView: React.FC<ChatViewProps> = ({
  onIndexedFilesCountChange,
  activeSessionId = null,
  onSessionCreated,
  onSessionsUpdated,
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputQuestion, setInputQuestion] = useState('');
  const [provider, setProvider] = useState<'local' | 'cloud'>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('brain_llm_provider');
      if (saved === 'cloud' || saved === 'local') return saved;
    }
    return 'cloud';
  });

  const handleProviderChange = (p: 'local' | 'cloud') => {
    setProvider(p);
    if (typeof window !== 'undefined') {
      localStorage.setItem('brain_llm_provider', p);
    }
  };
  const [isLoading, setIsLoading] = useState(false);
  const [generalError, setGeneralError] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // Load session messages when activeSessionId changes
  useEffect(() => {
    let isCancelled = false;

    const loadSessionHistory = async () => {
      if (!activeSessionId) {
        setMessages([]);
        return;
      }

      try {
        const { fetchSession } = await import('@/lib/api');
        const sessionData = await fetchSession(activeSessionId);
        if (!isCancelled && sessionData && sessionData.messages) {
          const formattedMessages: ChatMessage[] = sessionData.messages.map((m) => ({
            id: m.id,
            role: m.role,
            text: m.content,
            sources: m.sources,
            provider: m.provider,
            model: m.model,
            timestamp: m.created_at * 1000,
          }));
          setMessages(formattedMessages);
        }
      } catch (err: unknown) {
        if (!isCancelled) {
          console.error('Failed to load session history:', err);
        }
      }
    };

    loadSessionHistory();

    return () => {
      isCancelled = true;
    };
  }, [activeSessionId]);

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  const handleSubmit = async (questionToAsk?: string) => {
    const query = (questionToAsk || inputQuestion).trim();
    if (!query || isLoading) return;

    setGeneralError(null);
    setInputQuestion('');

    const targetSessionId =
      activeSessionId ||
      (typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID()
        : `session-${Date.now()}`);

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      text: query,
      timestamp: Date.now(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    try {
      const response = await postQuery(query, undefined, undefined, provider, targetSessionId);

      const assistantMessage: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        text: response.answer,
        sources: response.sources,
        provider: response.provider || provider,
        model: response.model,
        timestamp: Date.now(),
      };

      setMessages((prev) => [...prev, assistantMessage]);

      if (!activeSessionId && onSessionCreated) {
        onSessionCreated(response.session_id || targetSessionId);
      }
      if (onSessionsUpdated) {
        onSessionsUpdated();
      }
    } catch (err: unknown) {
      const isApiError = err instanceof ApiError;
      const errorMsg = isApiError
        ? err.message
        : 'An unexpected error occurred while querying the brain.';

      const errorMessage: ChatMessage = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        text: 'Failed to retrieve answer from knowledge base.',
        provider: provider,
        timestamp: Date.now(),
        isError: true,
        errorMessage: errorMsg,
      };

      setMessages((prev) => [...prev, errorMessage]);

      if (isApiError && err.isNetworkError) {
        setGeneralError(err.message);
      }
    } finally {
      setIsLoading(false);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  };


  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full min-h-0 bg-paper relative">
      {/* Scrollable Message Thread */}
      <div className="flex-1 min-h-0 overflow-y-auto px-8 py-8">
        <div className="max-w-5xl mx-auto w-full space-y-6">
          {generalError && (
            <ErrorBanner
              message={generalError}
              onRetry={() => setGeneralError(null)}
            />
          )}

          {messages.length === 0 ? (
            <div className="min-h-[450px] flex flex-col items-center justify-center text-center px-4 max-w-3xl mx-auto space-y-7">
              <div className="space-y-2.5">
                <h2 className="font-serif text-3xl text-ink font-semibold tracking-tight">
                  Personal Knowledge Archive
                </h2>
                <p className="text-sm text-stone max-w-lg mx-auto font-sans leading-relaxed">
                  Ask natural language questions across your indexed documents. Answers are strictly grounded in retrieved vector chunks with exact citations.
                </p>
              </div>

              <div className="w-full space-y-2.5 pt-2">
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-1.5 h-1.5 rounded-full bg-pine" />
                  <span className="font-mono text-[11px] uppercase tracking-wider text-moss font-semibold">
                    Suggested Exploration Queries
                  </span>
                </div>
                <div className="grid grid-cols-1 gap-2.5">
                  {SAMPLE_QUESTIONS.map((q, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleSubmit(q)}
                      className="w-full text-left p-3.5 rounded-lg bg-card border border-moss/20 hover:border-pine hover:bg-card/90 transition-all duration-150 text-xs text-ink font-sans flex items-center justify-between group shadow-2xs cursor-pointer"
                    >
                      <span className="font-medium mr-3 leading-relaxed">{q}</span>
                      <span className="font-mono text-[11px] text-stone group-hover:text-pine px-2 py-0.5 rounded bg-paper border border-moss/15 flex-shrink-0 transition-colors">
                        Ask ↵
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            messages.map((msg) => <MessageItem key={msg.id} message={msg} />)
          )}

          {/* Loading Indicator */}
          {isLoading && (
            <div className="flex justify-start">
              <div className="bg-card border border-moss/20 rounded-lg p-4.5 max-w-lg shadow-2xs space-y-2">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-pine animate-pulse" />
                  <span className="font-mono text-xs text-pine font-semibold uppercase tracking-wider">
                    {provider === 'cloud'
                      ? 'Retrieving Chunks & Synthesizing via Groq Cloud...'
                      : 'Retrieving Chunks & Synthesizing via Local Ollama...'}
                  </span>
                </div>
                <p className="font-sans text-xs text-stone">
                  {provider === 'cloud'
                    ? 'Searching local ChromaDB vectors and generating grounded response via Groq llama-3.3-70b...'
                    : 'Searching local ChromaDB vectors and generating grounded response via local Ollama...'}
                </p>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Pinned Bottom Input Bar */}
      <div className="border-t border-moss/20 bg-card p-4 px-8">
        <div className="max-w-5xl mx-auto space-y-3">
          {/* Provider Selection Controls */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="font-mono text-[11px] uppercase tracking-wider text-stone font-medium">
                Synthesis Engine:
              </span>
              <div className="inline-flex rounded-md p-0.5 bg-paper border border-moss/20 font-mono text-[11px]">
                <button
                  type="button"
                  onClick={() => handleProviderChange('local')}
                  className={`px-3 py-1 rounded transition-colors cursor-pointer flex items-center gap-1.5 ${
                    provider === 'local'
                      ? 'bg-card text-pine font-bold border border-moss/20 shadow-2xs'
                      : 'text-stone hover:text-ink'
                  }`}
                >
                  <span>⚡</span>
                  <span>Local (Ollama)</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleProviderChange('cloud')}
                  className={`px-3 py-1 rounded transition-colors cursor-pointer flex items-center gap-1.5 ${
                    provider === 'cloud'
                      ? 'bg-card text-pine font-bold border border-moss/20 shadow-2xs'
                      : 'text-stone hover:text-ink'
                  }`}
                >
                  <span>☁️</span>
                  <span>Cloud (Groq)</span>
                </button>
              </div>
            </div>

            <span className="font-mono text-[11px] text-stone">
              {provider === 'cloud'
                ? '☁️ Groq llama-3.3-70b-versatile (Free Cloud Tier)'
                : '🔒 100% Local In-Process Retrieval'}
            </span>
          </div>

          {/* Form Input Bar */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSubmit();
            }}
            className="flex items-center gap-3"
          >
            <input
              ref={inputRef}
              type="text"
              value={inputQuestion}
              onChange={(e) => setInputQuestion(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                provider === 'cloud'
                  ? 'Ask a question (synthesizing via Groq Cloud)...'
                  : 'Ask a question (synthesizing via Local Ollama)...'
              }
              disabled={isLoading}
              className="flex-1 bg-paper border border-moss/25 focus:border-pine focus:outline-none rounded-md px-4 py-2.5 text-sm text-ink placeholder:text-stone font-sans transition-colors disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={isLoading || !inputQuestion.trim()}
              className="px-5 py-2.5 bg-pine hover:bg-pine/90 disabled:opacity-40 disabled:cursor-not-allowed text-white font-mono text-xs font-semibold rounded-md transition-colors flex items-center gap-1.5 shadow-xs cursor-pointer"
            >
              <span>Ask</span>
              <span className="text-[10px]">↵</span>
            </button>
          </form>

          <div className="flex items-center justify-between text-[11px] font-mono text-stone">
            <span>Grounded in local ChromaDB vectors</span>
            <span>{provider === 'cloud' ? 'Requires GROQ_API_KEY in .env' : 'Zero cloud telemetry'}</span>
          </div>
        </div>
      </div>
    </div>
  );
};
