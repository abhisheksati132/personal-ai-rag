'use client';

import React, { useState, useEffect } from 'react';
import { Sidebar } from '@/components/Sidebar';
import { ChatView } from '@/components/ChatView';
import { FilesView } from '@/components/FilesView';
import { checkHealth, fetchStats } from '@/lib/api';

export default function Home() {
  const [activeTab, setActiveTab] = useState<'ask' | 'files'>('ask');
  const [fileCount, setFileCount] = useState<number>(0);
  const [isOnline, setIsOnline] = useState<boolean>(true);
  const [ollamaConnected, setOllamaConnected] = useState<boolean>(true);

  const refreshSystemStatus = async () => {
    try {
      const health = await checkHealth();
      setIsOnline(true);
      setOllamaConnected(health.ollama_connected);
      setFileCount(health.indexed_files);
    } catch {
      setIsOnline(false);
      setOllamaConnected(false);
    }
  };

  useEffect(() => {
    refreshSystemStatus();
    const interval = setInterval(refreshSystemStatus, 8000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex h-screen w-screen bg-paper overflow-hidden select-text">
      {/* Narrow Left Sidebar */}
      <Sidebar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        fileCount={fileCount}
        isOnline={isOnline}
        ollamaConnected={ollamaConnected}
      />

      {/* Main Panel */}
      <main className="flex-1 flex flex-col h-full overflow-hidden">
        {activeTab === 'ask' ? (
          <ChatView onIndexedFilesCountChange={refreshSystemStatus} />
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
