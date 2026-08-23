'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Sidebar } from '@/components/Sidebar';
import { ChatView } from '@/components/ChatView';
import { FilesView } from '@/components/FilesView';
import { checkHealth, fetchSessions, renameSession, deleteSession } from '@/lib/api';
import { SessionItem } from '@/lib/types';

export default function Home() {
  const [activeTab, setActiveTab] = useState<'ask' | 'files'>('ask');
  const [fileCount, setFileCount] = useState<number>(0);
  const [isOnline, setIsOnline] = useState<boolean>(true);
  const [ollamaConnected, setOllamaConnected] = useState<boolean>(true);

  // Session state: always starts fresh as null on app startup / reload
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<SessionItem[]>([]);

  const refreshSessions = useCallback(async () => {
    try {
      const sessionList = await fetchSessions();
      setSessions(sessionList);
    } catch (err) {
      console.error('Failed to fetch sessions list:', err);
    }
  }, []);

  const refreshSystemStatus = async () => {
    try {
      const health = await checkHealth();
      setIsOnline(true);
      setOllamaConnected(health.ollama_connected);
      setFileCount(health.indexed_files + (health.indexed_bookmarks || 0));
    } catch {
      setIsOnline(false);
      setOllamaConnected(false);
    }
  };

  useEffect(() => {
    refreshSystemStatus();
    refreshSessions();
    const interval = setInterval(refreshSystemStatus, 8000);
    return () => clearInterval(interval);
  }, [refreshSessions]);

  const handleSelectSession = (sessionId: string) => {
    setActiveSessionId(sessionId);
    setActiveTab('ask');
  };

  const handleNewChat = () => {
    setActiveSessionId(null);
    setActiveTab('ask');
  };

  const handleRenameSession = async (sessionId: string, newTitle: string) => {
    await renameSession(sessionId, newTitle);
    await refreshSessions();
  };

  const handleDeleteSession = async (sessionId: string) => {
    await deleteSession(sessionId);
    if (activeSessionId === sessionId) {
      setActiveSessionId(null);
    }
    await refreshSessions();
  };

  const handleSessionCreated = (newSessionId: string) => {
    setActiveSessionId(newSessionId);
    refreshSessions();
  };

  return (
    <div className="flex h-full w-full bg-paper overflow-hidden select-text">
      {/* Left Sidebar with Navigation & History */}
      <Sidebar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        fileCount={fileCount}
        isOnline={isOnline}
        ollamaConnected={ollamaConnected}
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={handleSelectSession}
        onNewChat={handleNewChat}
        onRenameSession={handleRenameSession}
        onDeleteSession={handleDeleteSession}
      />

      {/* Main Panel */}
      <main className="flex-1 flex flex-col h-full min-h-0 min-w-0 overflow-hidden">
        {activeTab === 'ask' ? (
          <ChatView
            key={activeSessionId || 'fresh-chat'}
            activeSessionId={activeSessionId}
            onSessionCreated={handleSessionCreated}
            onSessionsUpdated={refreshSessions}
            onIndexedFilesCountChange={refreshSystemStatus}
          />
        ) : (
          <FilesView
            onStatsUpdated={(count) => {
              setFileCount(count);
              refreshSystemStatus();
            }}
          />
        )}
      </main>
    </div>
  );
}

