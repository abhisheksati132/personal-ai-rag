'use client';

import React, { useState } from 'react';
import { SessionItem } from '@/lib/types';

interface SidebarProps {
  activeTab: 'ask' | 'files';
  onTabChange: (tab: 'ask' | 'files') => void;
  fileCount: number;
  isOnline: boolean;
  ollamaConnected: boolean;
  sessions?: SessionItem[];
  activeSessionId?: string | null;
  onSelectSession?: (sessionId: string) => void;
  onNewChat?: () => void;
  onRenameSession?: (sessionId: string, newTitle: string) => Promise<void>;
  onDeleteSession?: (sessionId: string) => Promise<void>;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onTabChange,
  fileCount,
  isOnline,
  ollamaConnected,
  sessions = [],
  activeSessionId = null,
  onSelectSession,
  onNewChat,
  onRenameSession,
  onDeleteSession,
}) => {
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [editTitleInput, setEditTitleInput] = useState<string>('');
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [isActionLoading, setIsActionLoading] = useState<boolean>(false);

  const startRename = (session: SessionItem, e: React.MouseEvent) => {
    e.stopPropagation();
    setConfirmDeleteId(null);
    setEditingSessionId(session.id);
    setEditTitleInput(session.title);
  };

  const handleSaveRename = async (sessionId: string) => {
    const trimmed = editTitleInput.trim();
    if (trimmed && onRenameSession) {
      setIsActionLoading(true);
      try {
        await onRenameSession(sessionId, trimmed);
      } finally {
        setIsActionLoading(false);
        setEditingSessionId(null);
      }
    } else {
      setEditingSessionId(null);
    }
  };

  const handleDeleteConfirm = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (onDeleteSession) {
      setIsActionLoading(true);
      try {
        await onDeleteSession(sessionId);
      } finally {
        setIsActionLoading(false);
        setConfirmDeleteId(null);
      }
    }
  };

  return (
    <aside className="w-64 flex-shrink-0 bg-card border-r border-moss/20 flex flex-col justify-between p-5 select-none z-10 h-full min-h-0 overflow-hidden space-y-4">
      {/* Top: Brand & Main Navigation */}
      <div className="flex-shrink-0 space-y-5">
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
            onClick={() => {
              onTabChange('ask');
              if (onNewChat) onNewChat();
            }}
            className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-md transition-colors cursor-pointer text-left ${
              activeTab === 'ask' && activeSessionId === null
                ? 'bg-paper text-pine font-semibold border border-moss/20 shadow-2xs'
                : 'text-stone hover:text-ink hover:bg-paper/50'
            }`}
          >
            <div className="flex items-center gap-2">
              <span className="uppercase tracking-wider">Ask</span>
              <span className="text-[10px] text-stone/60 font-sans font-normal">(New)</span>
            </div>
            {activeTab === 'ask' && activeSessionId === null && (
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

      {/* Middle: Conversation Sessions History List */}
      <div className="flex-1 min-h-0 flex flex-col pt-3 border-t border-moss/15 space-y-2">
        <div className="flex items-center justify-between px-1">
          <span className="font-mono text-[10px] text-stone tracking-widest uppercase font-semibold">
            History
          </span>
          <button
            onClick={() => {
              onTabChange('ask');
              if (onNewChat) onNewChat();
            }}
            title="Start fresh conversation"
            className="font-mono text-[10px] px-2 py-0.5 rounded text-pine bg-paper border border-moss/20 hover:bg-pine hover:text-paper transition-all cursor-pointer"
          >
            + New
          </button>
        </div>

        {/* Scrollable Sessions List */}
        <div className="flex-1 min-h-0 overflow-y-auto space-y-1.5 pr-1">
          {sessions.length === 0 ? (
            <div className="py-6 text-center">
              <p className="font-mono text-[11px] text-stone/70 italic">
                No conversations yet
              </p>
            </div>
          ) : (
            sessions.map((session) => {
              const isSelected = activeTab === 'ask' && activeSessionId === session.id;
              const isEditing = editingSessionId === session.id;
              const isConfirmingDelete = confirmDeleteId === session.id;

              return (
                <div
                  key={session.id}
                  onClick={() => {
                    if (!isEditing && !isConfirmingDelete && onSelectSession) {
                      onSelectSession(session.id);
                    }
                  }}
                  className={`group relative flex flex-col p-2.5 rounded-md transition-all cursor-pointer border ${
                    isSelected
                      ? 'bg-paper border-moss/30 shadow-2xs text-pine'
                      : 'bg-paper/40 border-transparent hover:border-moss/15 hover:bg-paper/80 text-stone hover:text-ink'
                  }`}
                >
                  {isEditing ? (
                    <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="text"
                        autoFocus
                        value={editTitleInput}
                        onChange={(e) => setEditTitleInput(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleSaveRename(session.id);
                          if (e.key === 'Escape') setEditingSessionId(null);
                        }}
                        className="w-full bg-paper px-2 py-1 text-xs text-ink font-sans border border-moss/40 rounded focus:outline-none focus:ring-1 focus:ring-pine"
                      />
                      <button
                        onClick={() => handleSaveRename(session.id)}
                        disabled={isActionLoading}
                        className="text-[10px] font-mono px-1.5 py-1 rounded bg-pine text-paper hover:bg-pine/90"
                      >
                        ✓
                      </button>
                      <button
                        onClick={() => setEditingSessionId(null)}
                        className="text-[10px] font-mono px-1.5 py-1 rounded bg-paper text-stone border border-moss/20 hover:text-ink"
                      >
                        ✕
                      </button>
                    </div>
                  ) : isConfirmingDelete ? (
                    <div className="flex flex-col gap-1.5 p-1 bg-red-50/80 border border-red-200 rounded" onClick={(e) => e.stopPropagation()}>
                      <span className="text-[10px] font-mono text-red-700 font-medium">Delete session?</span>
                      <div className="flex items-center gap-1.5">
                        <button
                          onClick={(e) => handleDeleteConfirm(session.id, e)}
                          disabled={isActionLoading}
                          className="text-[10px] font-mono px-2 py-0.5 rounded bg-red-600 text-white hover:bg-red-700 font-semibold"
                        >
                          Delete
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setConfirmDeleteId(null);
                          }}
                          className="text-[10px] font-mono px-2 py-0.5 rounded bg-white text-stone border border-stone/30 hover:text-ink"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-start justify-between gap-1">
                      <div className="flex-1 min-w-0 pr-1 space-y-0.5">
                        <p
                          className={`text-xs font-sans truncate font-medium ${
                            isSelected ? 'text-pine font-semibold' : 'text-ink'
                          }`}
                          title={session.title}
                        >
                          {session.title}
                        </p>
                        {session.first_query_preview && session.title !== session.first_query_preview ? (
                          <p className="text-[11px] font-sans text-stone truncate">
                            {session.first_query_preview}
                          </p>
                        ) : null}
                      </div>

                      {/* Action buttons (Rename & Delete) */}
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                        <button
                          onClick={(e) => startRename(session, e)}
                          title="Rename session"
                          className="p-1 rounded text-stone hover:text-pine hover:bg-paper"
                        >
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                          </svg>
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setEditingSessionId(null);
                            setConfirmDeleteId(session.id);
                          }}
                          title="Delete session"
                          className="p-1 rounded text-stone hover:text-red-600 hover:bg-red-50"
                        >
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Bottom: System Status Footer */}
      <div className="flex-shrink-0 pt-3 border-t border-moss/15 space-y-2">
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


