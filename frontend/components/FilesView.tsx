'use client';

import React, { useState, useEffect } from 'react';
import { IndexedFile, StatsResponse } from '@/lib/types';
import { fetchFiles, fetchStats, ApiError } from '@/lib/api';
import { ErrorBanner } from './ErrorBanner';

interface FilesViewProps {
  onStatsUpdated?: (count: number) => void;
}

export const FilesView: React.FC<FilesViewProps> = ({ onStatsUpdated }) => {
  const [files, setFiles] = useState<IndexedFile[]>([]);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [filesData, statsData] = await Promise.all([fetchFiles(), fetchStats()]);
      setFiles(filesData);
      setStats(statsData);
      if (onStatsUpdated) {
        onStatsUpdated(statsData.indexed_files || filesData.length);
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Failed to load indexed files.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return '0 B';
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

  return (
    <div className="flex flex-col h-full bg-paper overflow-y-auto p-6 space-y-6">
      {/* Header & Refresh Action */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-serif text-2xl text-ink font-semibold tracking-tight">
            Indexed Knowledge Files
          </h2>
          <p className="text-xs text-stone font-sans mt-0.5">
            Documents actively indexed and embedded in local ChromaDB vector store
          </p>
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

      {error && <ErrorBanner message={error} onRetry={loadData} />}

      {/* Aggregate Stats Header */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="bg-card border border-moss/20 rounded-md p-3.5 shadow-xs">
            <span className="font-mono text-[11px] text-stone uppercase tracking-wider block">
              Tracked Files
            </span>
            <span className="font-mono text-xl font-semibold text-ink mt-1 block">
              {stats.indexed_files}
              {stats.failed_files > 0 && (
                <span className="text-xs text-red-600 font-normal ml-1.5">
                  ({stats.failed_files} failed)
                </span>
              )}
            </span>
          </div>

          <div className="bg-card border border-moss/20 rounded-md p-3.5 shadow-xs">
            <span className="font-mono text-[11px] text-stone uppercase tracking-wider block">
              Total Chunks / Vectors
            </span>
            <span className="font-mono text-xl font-semibold text-pine mt-1 block">
              {stats.total_chunks}
            </span>
          </div>

          <div className="bg-card border border-moss/20 rounded-md p-3.5 shadow-xs">
            <span className="font-mono text-[11px] text-stone uppercase tracking-wider block">
              Indexed Size
            </span>
            <span className="font-mono text-xl font-semibold text-ink mt-1 block">
              {formatBytes(stats.total_bytes)}
            </span>
          </div>

          <div className="bg-card border border-moss/20 rounded-md p-3.5 shadow-xs">
            <span className="font-mono text-[11px] text-stone uppercase tracking-wider block">
              Last Sync
            </span>
            <span className="font-mono text-xs font-semibold text-ink mt-2 block truncate">
              {formatDate(stats.last_indexed_at)}
            </span>
          </div>
        </div>
      )}

      {/* File List Table */}
      <div className="bg-card border border-moss/20 rounded-lg overflow-hidden shadow-xs">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-moss/15 bg-paper/60 font-mono text-[11px] uppercase tracking-wider text-moss">
                <th className="py-3 px-4">Document</th>
                <th className="py-3 px-4 text-center">Chunks</th>
                <th className="py-3 px-4 text-right">File Size</th>
                <th className="py-3 px-4 text-right">Last Indexed</th>
                <th className="py-3 px-4 text-center">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-moss/10 font-sans text-xs">
              {files.length === 0 ? (
                <tr>
                  <td
                    colSpan={5}
                    className="py-12 text-center text-stone font-mono text-xs"
                  >
                    {isLoading
                      ? 'Loading indexed documents...'
                      : 'No documents indexed yet. Drop files into data/documents/ to auto-index.'}
                  </td>
                </tr>
              ) : (
                files.map((file) => (
                  <tr
                    key={file.file_path}
                    className="hover:bg-paper/40 transition-colors"
                  >
                    <td className="py-3 px-4">
                      <div className="flex flex-col">
                        <span
                          className="font-mono text-xs font-semibold text-ink truncate max-w-md"
                          title={file.file_name}
                        >
                          {file.file_name}
                        </span>
                        <span
                          className="font-mono text-[10px] text-stone truncate max-w-sm"
                          title={file.file_path}
                        >
                          {file.file_path}
                        </span>
                      </div>
                    </td>
                    <td className="py-3 px-4 text-center font-mono text-ink">
                      {file.chunk_count}
                    </td>
                    <td className="py-3 px-4 text-right font-mono text-stone">
                      {formatBytes(file.file_size)}
                    </td>
                    <td className="py-3 px-4 text-right font-mono text-stone">
                      {formatDate(file.indexed_at)}
                    </td>
                    <td className="py-3 px-4 text-center">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono font-medium ${
                          file.status === 'indexed'
                            ? 'bg-pine/10 text-pine border border-pine/20'
                            : 'bg-red-50 text-red-700 border border-red-200'
                        }`}
                      >
                        {file.status}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
