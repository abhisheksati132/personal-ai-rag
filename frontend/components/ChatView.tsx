'use client';

import React, { useState, useRef, useEffect } from 'react';
import { ChatMessage } from '@/lib/types';
import { postQuery, ApiError } from '@/lib/api';
import { MessageItem } from './MessageItem';
import { ErrorBanner } from './ErrorBanner';

interface ChatViewProps {
  onIndexedFilesCountChange?: () => void;
}

const SAMPLE_QUESTIONS = [
  'Explain how a modern compiler processes the statement through all compilation phases in CAT-1.',
  'How many ports at end devices and total cables are needed for 5 devices in a Full Mesh Topology?',
  'What is the architecture and role of ChromaDB in this local RAG system?',
];

export const ChatView: React.FC<ChatViewProps> = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputQuestion, setInputQuestion] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [generalError, setGeneralError] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  const handleSubmit = async (questionToAsk?: string) => {
    const query = (questionToAsk || inputQuestion).trim();
    if (!query || isLoading) return;

    setGeneralError(null);
    setInputQuestion('');

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      text: query,
      timestamp: Date.now(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    try {
      const response = await postQuery(query);

      const assistantMessage: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        text: response.answer,
        sources: response.sources,
        timestamp: Date.now(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err: unknown) {
      const isApiError = err instanceof ApiError;
      const errorMsg = isApiError
        ? err.message
        : 'An unexpected error occurred while querying the brain.';

      const errorMessage: ChatMessage = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        text: 'Failed to retrieve answer from knowledge base.',
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
    <div className="flex flex-col h-full bg-paper relative">

      {/* Scrollable Message Thread */}
      <div className="flex-1 overflow-y-auto px-8 py-8">
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
                  Ask natural language questions across your indexed course materials and documents. Answers are strictly grounded in retrieved vector chunks with exact citations.
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
                    Retrieving Chunks & Synthesizing...
                  </span>
                </div>
                <p className="font-sans text-xs text-stone">
                  Searching local ChromaDB vectors and evaluating similarity thresholds...
                </p>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Pinned Bottom Input Bar */}
      <div className="border-t border-moss/20 bg-card p-4 px-8">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSubmit();
          }}
          className="max-w-5xl mx-auto flex items-center gap-3"
        >
          <input
            ref={inputRef}
            type="text"
            value={inputQuestion}
            onChange={(e) => setInputQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question across your indexed documents..."
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
        <div className="max-w-5xl mx-auto mt-2 flex items-center justify-between text-[11px] font-mono text-stone">
          <span>Grounded in local ChromaDB vectors</span>
          <span>Zero cloud telemetry</span>
        </div>
      </div>
    </div>
  );
};

