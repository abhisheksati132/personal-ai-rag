'use client';

import React from 'react';

interface SidebarProps {
  activeTab: 'ask' | 'files';
  onTabChange: (tab: 'ask' | 'files') => void;
  fileCount: number;
  isOnline: boolean;
  ollamaConnected: boolean;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onTabChange,
  fileCount,
  isOnline,
  ollamaConnected,
}) => {
  return (
    <aside className="w-64 flex-shrink-0 bg-card border-r border-moss/20 flex flex-col justify-between p-5 select-none z-10">
      {/* Brand & Nav */}
      <div className="space-y-6">
        {/* App Title */}
        <div className="space-y-1">
          <h1 className="font-serif text-2xl font-bold tracking-tight text-ink">
            BRAIN
          </h1>
          <p className="font-mono text-[10px] text-stone tracking-widest uppercase">
            Personal AI Archive
          </p>
        </div>

        {/* Navigation */}
        <nav className="space-y-1.5 font-mono text-xs">
          <button
            onClick={() => onTabChange('ask')}
            className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-md transition-colors cursor-pointer text-left ${
              activeTab === 'ask'
                ? 'bg-paper text-pine font-semibold border border-moss/20 shadow-2xs'
                : 'text-stone hover:text-ink hover:bg-paper/50'
            }`}
          >
            <span className="uppercase tracking-wider">Ask</span>
            {activeTab === 'ask' && (
              <span className="w-1.5 h-1.5 rounded-full bg-pine" />
            )}
          </button>

          <button
            onClick={() => onTabChange('files')}
            className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-md transition-colors cursor-pointer text-left ${
              activeTab === 'files'
                ? 'bg-paper text-pine font-semibold border border-moss/20 shadow-2xs'
                : 'text-stone hover:text-ink hover:bg-paper/50'
            }`}
          >
            <span className="uppercase tracking-wider">Files</span>
            <span
              className={`font-mono text-[11px] px-2 py-0.5 rounded ${
                activeTab === 'files'
                  ? 'bg-pine/10 text-pine font-bold'
                  : 'bg-paper text-stone border border-moss/15'
              }`}
            >
              {fileCount}
            </span>
          </button>
        </nav>
      </div>

      {/* System Status Footer */}
      <div className="pt-5 border-t border-moss/15 space-y-2">
        <div className="bg-paper/80 border border-moss/20 rounded-md p-3.5 space-y-2.5">
          <div className="flex items-center justify-between font-mono text-xs">
            <span className="text-stone font-medium text-left whitespace-nowrap select-none">
              Backend API
            </span>
            <div className="flex items-center gap-1.5 flex-shrink-0">
              <span
                className={`w-2 h-2 rounded-full ${
                  isOnline ? 'bg-emerald-600' : 'bg-red-500 animate-pulse'
                }`}
              />
              <span className={`text-xs font-semibold ${isOnline ? 'text-moss' : 'text-red-600'}`}>
                {isOnline ? '8000' : 'Offline'}
              </span>
            </div>
          </div>

          <div className="flex items-center justify-between font-mono text-xs">
            <span className="text-stone font-medium text-left whitespace-nowrap select-none">
              Ollama LLM
            </span>
            <div className="flex items-center gap-1.5 flex-shrink-0">
              <span
                className={`w-2 h-2 rounded-full ${
                  ollamaConnected
                    ? 'bg-emerald-600'
                    : isOnline
                    ? 'bg-amber-500'
                    : 'bg-stone/50'
                }`}
              />
              <span
                className={`text-xs font-semibold ${
                  ollamaConnected
                    ? 'text-moss'
                    : isOnline
                    ? 'text-amber-700'
                    : 'text-stone'
                }`}
              >
                {ollamaConnected ? 'Ready' : isOnline ? 'Down' : 'Unknown'}
              </span>
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
};

