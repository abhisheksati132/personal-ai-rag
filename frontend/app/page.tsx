'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Sidebar } from '@/components/Sidebar';
import { ChatView } from '@/components/ChatView';
import { FilesView } from '@/components/FilesView';
import { AuthGate } from '@/components/AuthGate';
import {
  checkHealth,
  fetchSessions,
  renameSession,
  deleteSession,
  checkAuthStatus,
  logout,
} from '@/lib/api';
import { SessionItem } from '@/lib/types';

export default function Home() {
  const [activeTab, setActiveTab] = useState<'ask' | 'files'>('ask');
  const [fileCount, setFileCount] = useState<number>(0);
  const [isOnline, setIsOnline] = useState<boolean>(true);
  const [ollamaConnected, setOllamaConnected] = useState<boolean>(true);

  // Authentication state
  const [authEnabled, setAuthEnabled] = useState<boolean>(false);
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(true);
  const [isAuthLoading, setIsAuthLoading] = useState<boolean>(true);

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

  const refreshSystemStatus = useCallback(async () => {
    try {
      const health = await checkHealth();
      setIsOnline(true);
      setOllamaConnected(health.ollama_connected);
      setFileCount(health.indexed_files + (health.indexed_bookmarks || 0));
    } catch {
      setIsOnline(false);
      setOllamaConnected(false);
    }
  }, []);

  const verifyAuth = useCallback(async () => {
    try {
      const status = await checkAuthStatus();
      setAuthEnabled(status.auth_enabled);
      setIsAuthenticated(status.authenticated);
      return status;
    } catch {
      return { auth_enabled: false, authenticated: true };
    } finally {
      setIsAuthLoading(false);
    }
  }, []);

  useEffect(() => {
    verifyAuth().then((status) => {
      if (!status.auth_enabled || status.authenticated) {
        refreshSystemStatus();
        refreshSessions();
      }
    });

    const handleUnauthorized = () => {
      setIsAuthenticated(false);
    };
    window.addEventListener('brain-unauthorized', handleUnauthorized);

    const interval = setInterval(() => {
      refreshSystemStatus();
    }, 8000);

    return () => {
      window.removeEventListener('brain-unauthorized', handleUnauthorized);
      clearInterval(interval);
    };
  }, [verifyAuth, refreshSystemStatus, refreshSessions]);

  const handleAuthSuccess = () => {
    setIsAuthenticated(true);
    refreshSystemStatus();
    refreshSessions();
  };

  const handleLogout = () => {
    logout();
    setIsAuthenticated(false);
    setActiveSessionId(null);
  };

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

  if (isAuthLoading) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-[#F6F5F2]">
        <div className="flex items-center gap-3 text-[#8A8578] font-mono text-xs">
          <span className="w-2.5 h-2.5 rounded-full bg-[#3D5A4C] animate-pulse" />
          <span>Connecting to Knowledge Archive...</span>
        </div>
      </div>
    );
  }

  if (authEnabled && !isAuthenticated) {
    return <AuthGate onSuccess={handleAuthSuccess} />;
  }

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
        onLogout={handleLogout}
        showLogout={authEnabled}
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
            ollamaConnected={ollamaConnected}
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
