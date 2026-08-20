'use client';

import React from 'react';

interface ErrorBannerProps {
  message: string;
  onRetry?: () => void;
}

export const ErrorBanner: React.FC<ErrorBannerProps> = ({ message, onRetry }) => {
  return (
    <div className="bg-red-50 border border-red-200 rounded-md p-3.5 flex items-center justify-between gap-3 text-red-900 shadow-xs mb-4">
      <div className="flex items-center gap-2.5 min-w-0">
        <span className="w-2 h-2 rounded-full bg-red-500 flex-shrink-0 animate-pulse" />
        <p className="text-xs font-mono truncate">{message}</p>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="flex-shrink-0 px-3 py-1 bg-white hover:bg-red-50 border border-red-300 rounded font-mono text-xs font-medium text-red-700 transition-colors cursor-pointer"
        >
          Retry
        </button>
      )}
    </div>
  );
};
