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
        {/* Header / Role tag */}
        <div className="flex items-center justify-between mb-2.5">
          <div className="flex items-center gap-2">
            <span
              className={`font-mono text-[10.5px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded ${
                isUser
                  ? 'bg-paper text-stone border border-moss/10'
                  : 'bg-pine/10 text-pine border border-pine/20'
              }`}
            >
              {isUser ? 'You' : 'Brain Archive'}
            </span>
            {isFallback && (
              <span className="font-mono text-[10.5px] text-stone bg-paper px-2 py-0.5 rounded border border-moss/15">
                No Context Found
              </span>
            )}
          </div>
          <span className="font-mono text-[10.5px] text-stone">
            {new Date(message.timestamp).toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        </div>


        {/* Message Body */}
        {message.isError ? (
          <div className="p-3 bg-red-50/80 border border-red-200 rounded text-red-800 text-sm font-sans">
            <p className="font-semibold text-xs mb-1 font-mono uppercase tracking-wide">
              Query Error
            </p>
            <p>{message.errorMessage || message.text}</p>
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
