'use client';

import React, { useState, useEffect } from 'react';
import { IndexedFile, StatsResponse } from '@/lib/types';
import { fetchFiles, fetchStats, ApiError } from '@/lib/api';
import { ErrorBanner } from './ErrorBanner';

interface FilesViewProps {
  onStatsUpdated?: (count: number) => void;
}

export const FilesView: React.FC<FilesViewProps> = ({ onStatsUpdated }) => {
  const [items, setItems] = useState<IndexedFile[]>([]);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<'all' | 'file' | 'bookmark'>('all');

  const loadData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [itemsData, statsData] = await Promise.all([fetchFiles(), fetchStats()]);
      setItems(itemsData);
      setStats(statsData);
      if (onStatsUpdated) {
        onStatsUpdated(statsData.indexed_items || statsData.indexed_files || itemsData.length);
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Failed to load indexed knowledge items.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const formatBytes = (bytes: number): string => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
  };

  const formatDate = (timestamp?: number | null): string => {
    if (!timestamp) return 'Never';
    return new Date(timestamp * 1000).toLocaleString([], {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const filteredItems = items.filter((item) => {
    const isBookmark = item.item_type === 'bookmark' || !!item.url;
    if (filterType === 'file') return !isBookmark;
    if (filterType === 'bookmark') return isBookmark;
    return true;
  });

  return (
    <div className="flex-1 flex flex-col h-full min-h-0 bg-paper overflow-hidden">
      {/* Top Header Section (Fixed at top) */}
      <div className="flex-shrink-0 p-6 pb-4 space-y-4">
        {/* Header & Refresh Action */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-serif text-2xl text-ink font-semibold tracking-tight">
              Knowledge Archive
            </h2>
            <p className="text-xs text-stone font-sans mt-0.5">
              Documents and Chrome bookmarks embedded in local ChromaDB vector store
            </p>
          </div>

          <div className="flex items-center gap-2">
            {/* Filter Pills */}
            <div className="flex items-center bg-card border border-moss/20 rounded-md p-0.5 text-xs font-mono">
              <button
                onClick={() => setFilterType('all')}
                className={`px-2.5 py-1 rounded transition-colors cursor-pointer ${
                  filterType === 'all'
                    ? 'bg-pine text-white font-medium shadow-2xs'
                    : 'text-stone hover:text-ink'
                }`}
              >
                All ({items.length})
              </button>
              <button
                onClick={() => setFilterType('file')}
                className={`px-2.5 py-1 rounded transition-colors cursor-pointer ${
                  filterType === 'file'
                    ? 'bg-pine text-white font-medium shadow-2xs'
                    : 'text-stone hover:text-ink'
                }`}
              >
                Files ({items.filter((i) => i.item_type !== 'bookmark' && !i.url).length})
              </button>
              <button
                onClick={() => setFilterType('bookmark')}
                className={`px-2.5 py-1 rounded transition-colors cursor-pointer ${
                  filterType === 'bookmark'
                    ? 'bg-pine text-white font-medium shadow-2xs'
                    : 'text-stone hover:text-ink'
                }`}
              >
                Bookmarks ({items.filter((i) => i.item_type === 'bookmark' || !!i.url).length})
              </button>
            </div>

            <button
              onClick={loadData}
              disabled={isLoading}
              className="px-3.5 py-1.5 bg-card hover:bg-paper border border-moss/25 hover:border-moss/50 text-ink font-mono text-xs font-medium rounded-md transition-colors flex items-center gap-2 shadow-xs cursor-pointer disabled:opacity-50"
            >
              <span className={isLoading ? 'animate-spin' : ''}>↻</span>
              <span>Refresh</span>
            </button>
          </div>
        </div>

        {error && <ErrorBanner message={error} onRetry={loadData} />}

        {/* Aggregate Stats Header */}
        {stats && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="bg-card border border-moss/20 rounded-md p-3.5 shadow-xs">
              <span className="font-mono text-[11px] text-stone uppercase tracking-wider block">
                Tracked Items
              </span>
              <span className="font-mono text-xl font-semibold text-ink mt-1 block">
                {(stats.indexed_items ?? (stats.indexed_files + (stats.indexed_bookmarks || 0)))}
                {(stats.failed_items || stats.failed_files > 0) && (
                  <span className="text-xs text-red-600 font-normal ml-1.5">
                    ({stats.failed_items ?? stats.failed_files} failed)
                  </span>
                )}
              </span>
              <span className="text-[10px] font-mono text-stone mt-1 block">
                {stats.indexed_files} files • {stats.indexed_bookmarks || 0} bookmarks
              </span>
            </div>

            <div className="bg-card border border-moss/20 rounded-md p-3.5 shadow-xs">
              <span className="font-mono text-[11px] text-stone uppercase tracking-wider block">
                Total Chunks / Vectors
              </span>
              <span className="font-mono text-xl font-semibold text-pine mt-1 block">
                {stats.total_chunks}
              </span>
              <span className="text-[10px] font-mono text-stone mt-1 block">
                ChromaDB cosine index
              </span>
            </div>

            <div className="bg-card border border-moss/20 rounded-md p-3.5 shadow-xs">
              <span className="font-mono text-[11px] text-stone uppercase tracking-wider block">
                Indexed File Size
              </span>
              <span className="font-mono text-xl font-semibold text-ink mt-1 block">
                {formatBytes(stats.total_bytes)}
              </span>
              <span className="text-[10px] font-mono text-stone mt-1 block">
                Excluding web bookmarks
              </span>
            </div>

            <div className="bg-card border border-moss/20 rounded-md p-3.5 shadow-xs">
              <span className="font-mono text-[11px] text-stone uppercase tracking-wider block">
                Last Ingestion
              </span>
              <span className="font-mono text-xs font-semibold text-ink mt-2 block truncate">
                {formatDate(stats.last_indexed_at)}
              </span>
              <span className="text-[10px] font-mono text-stone mt-1 block">
                Auto-sync active
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Scrollable File & Bookmark List Table Container */}
      <div className="flex-1 min-h-0 px-6 pb-6 flex flex-col">
        <div className="flex-1 min-h-0 bg-card border border-moss/20 rounded-lg overflow-hidden shadow-xs flex flex-col">
          <div className="flex-1 min-h-0 overflow-y-auto overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead className="sticky top-0 bg-paper/95 backdrop-blur-xs border-b border-moss/15 z-10">
                <tr className="font-mono text-[11px] uppercase tracking-wider text-moss">
                  <th className="py-3 px-4 bg-paper/95">Source & Title</th>
                  <th className="py-3 px-4 bg-paper/95">Type</th>
                  <th className="py-3 px-4 text-center bg-paper/95">Chunks</th>
                  <th className="py-3 px-4 text-right bg-paper/95">Size / Location</th>
                  <th className="py-3 px-4 text-right bg-paper/95">Last Indexed</th>
                  <th className="py-3 px-4 text-center bg-paper/95">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-moss/10 font-sans text-xs">
                {filteredItems.length === 0 ? (
                  <tr>
                    <td
                      colSpan={6}
                      className="py-12 text-center text-stone font-mono text-xs"
                    >
                      {isLoading
                        ? 'Loading knowledge base items...'
                        : 'No items found matching filter.'}
                    </td>
                  </tr>
                ) : (
                  filteredItems.map((item) => {
                    const isBookmark = item.item_type === 'bookmark' || !!item.url;
                    const key = item.url || item.file_path;

                    return (
                      <tr
                        key={key}
                        className="hover:bg-paper/40 transition-colors"
                      >
                        <td className="py-3 px-4">
                          <div className="flex flex-col">
                            {isBookmark && item.url ? (
                              <a
                                href={item.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="font-mono text-xs font-semibold text-pine hover:underline truncate max-w-md flex items-center gap-1"
                                title={`${item.file_name} (${item.url})`}
                              >
                                <span className="truncate">{item.file_name}</span>
                                <span className="text-[10px] flex-shrink-0">↗</span>
                              </a>
                            ) : (
                              <span
                                className="font-mono text-xs font-semibold text-ink truncate max-w-md"
                                title={item.file_name}
                              >
                                {item.file_name}
                              </span>
                            )}

                            <span
                              className="font-mono text-[10px] text-stone truncate max-w-sm mt-0.5"
                              title={item.url || item.file_path}
                            >
                              {item.url || item.file_path}
                            </span>
                          </div>
                        </td>

                        <td className="py-3 px-4">
                          <span
                            className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono font-medium ${
                              isBookmark
                                ? 'bg-moss/10 text-moss border border-moss/20'
                                : 'bg-pine/10 text-pine border border-pine/20'
                            }`}
                          >
                            {isBookmark ? '🔖 Bookmark' : '📄 File'}
                          </span>
                        </td>

                        <td className="py-3 px-4 text-center font-mono text-ink">
                          {item.chunk_count}
                        </td>

                        <td className="py-3 px-4 text-right font-mono text-stone">
                          {isBookmark
                            ? item.folder || 'Bookmarks'
                            : formatBytes(item.file_size)}
                        </td>

                        <td className="py-3 px-4 text-right font-mono text-stone">
                          {formatDate(item.indexed_at)}
                        </td>

                        <td className="py-3 px-4 text-center">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono font-medium ${
                              item.status === 'indexed'
                                ? 'bg-pine/10 text-pine border border-pine/20'
                                : 'bg-red-50 text-red-700 border border-red-200'
                            }`}
                            title={item.error_message || undefined}
                          >
                            {item.status}
                          </span>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};
