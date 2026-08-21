'use client';

import React from 'react';
import { ChatMessage } from '@/lib/types';
import { RetrievalStrip } from './RetrievalStrip';

interface MessageItemProps {
  message: ChatMessage;
}

export const MessageItem: React.FC<MessageItemProps> = ({ message }) => {
  const isUser = message.role === 'user';
  const textLower = (message.text || '').toLowerCase();
  const isFallback =
    !isUser &&
    !message.isError &&
    (message.sources?.length === 0 ||
      textLower.includes("don't have information") ||
      textLower.includes("cannot find information") ||
      textLower.includes("no information found"));

  const isCloud = message.provider === 'cloud';
  const modelName = message.model || (isCloud ? 'llama-3.3-70b-versatile' : 'llama3.2');
  const isMissingApiKeyError =
    message.isError &&
    message.errorMessage &&
    (message.errorMessage.includes('GROQ_API_KEY') ||
      message.errorMessage.toLowerCase().includes('groq api key not configured') ||
      message.errorMessage.toLowerCase().includes('invalid groq api key'));

  return (
    <div
      className={`flex w-full ${
        isUser ? 'justify-end' : 'justify-start'
      } transition-opacity duration-200`}
    >
      <div
        className={`w-full ${
          isUser
            ? 'bg-card border border-moss/20 rounded-lg p-4 ml-auto max-w-2xl text-ink shadow-2xs'
            : 'bg-card border border-moss/20 rounded-lg p-6 text-ink shadow-2xs'
        }`}
      >
        {/* Header / Role tag & Provenance */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className={`font-mono text-[10.5px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded ${
                isUser
                  ? 'bg-paper text-stone border border-moss/10'
                  : 'bg-pine/10 text-pine border border-pine/20'
              }`}
            >
              {isUser ? 'You' : 'Brain Archive'}
            </span>

            {/* Provider Provenance Badge */}
            {!isUser && !message.isError && (
              <span
                className={`font-mono text-[10.5px] px-2 py-0.5 rounded border flex items-center gap-1 ${
                  isCloud
                    ? 'bg-paper text-moss border-moss/30 font-medium'
                    : 'bg-paper text-stone border-moss/15'
                }`}
              >
                <span>{isCloud ? '☁️ Groq Cloud' : '⚡ Local Ollama'}</span>
                <span className="text-[9px] text-stone/80">({modelName})</span>
              </span>
            )}

            {isFallback && (
              <span className="font-mono text-[10.5px] text-stone bg-paper px-2 py-0.5 rounded border border-moss/15">
                No Context Found
              </span>
            )}
          </div>

          <span className="font-mono text-[10.5px] text-stone flex-shrink-0">
            {new Date(message.timestamp).toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        </div>

        {/* Message Body */}
        {message.isError ? (
          <div className="p-4 bg-paper border border-moss/20 rounded-md text-ink text-sm font-sans space-y-2.5">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-amber-600" />
              <p className="font-semibold text-xs font-mono uppercase tracking-wide text-ink">
                {isMissingApiKeyError ? 'Cloud Fallback Not Configured' : 'Query Notice'}
              </p>
            </div>

            <p className="text-xs text-stone leading-relaxed">
              {message.errorMessage || message.text}
            </p>

            {isMissingApiKeyError && (
              <div className="pt-2 border-t border-moss/15 flex items-center justify-between font-mono text-[11px]">
                <span className="text-stone">Get a free key:</span>
                <a
                  href="https://console.groq.com/keys"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-pine font-semibold underline hover:text-pine/80"
                >
                  console.groq.com/keys ↗
                </a>
              </div>
            )}
          </div>
        ) : (
          <div className="text-sm leading-relaxed whitespace-pre-wrap font-sans text-ink space-y-2">
            {message.text}
          </div>
        )}

        {/* Signature Evidence Trail */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <RetrievalStrip sources={message.sources} />
        )}
      </div>
    </div>
  );
};
