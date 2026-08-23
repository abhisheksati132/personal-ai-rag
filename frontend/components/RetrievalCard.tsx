'use client';

import React from 'react';
import { SourceInfo } from '@/lib/types';

interface RetrievalCardProps {
  source: SourceInfo;
  index: number;
}

export const RetrievalCard: React.FC<RetrievalCardProps> = ({ source, index }) => {
  const percentage = Math.min(100, Math.max(0, Math.round(source.score * 100)));
  const isBookmark = source.source_type === 'bookmark' || !!source.url;
  const title = source.title || source.file;

  return (
    <div
      className="retrieval-card-stagger w-full bg-paper/60 hover:bg-card border border-moss/20 hover:border-moss/40 rounded-md p-3 transition-all duration-150 flex flex-col justify-between"
      style={{
        animationDelay: `${index * 40}ms`,
      }}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-1">
            <span
              className={`font-mono text-[9.5px] uppercase tracking-wider font-semibold px-1.5 py-0.2 rounded border ${
                isBookmark
                  ? 'bg-moss/10 text-moss border-moss/25'
                  : 'bg-pine/10 text-pine border-pine/20'
              }`}
            >
              {isBookmark ? '🔖 Bookmark' : '📄 File'}
            </span>
            {source.folder && (
              <span
                className="font-mono text-[10px] text-stone truncate max-w-[140px]"
                title={source.folder}
              >
                {source.folder}
              </span>
            )}
          </div>

          {isBookmark && source.url ? (
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="font-mono text-xs font-semibold text-pine hover:text-pine/80 hover:underline truncate flex items-center gap-1"
              title={`${title} (${source.url})`}
            >
              <span className="truncate">{title}</span>
              <span className="text-[10px] flex-shrink-0">↗</span>
            </a>
          ) : (
            <span
              className="font-mono text-xs font-semibold text-ink truncate block"
              title={source.file}
            >
              {source.file}
            </span>
          )}
        </div>

        <span className="font-mono text-[11px] px-1.5 py-0.5 rounded bg-paper text-stone border border-moss/15 flex-shrink-0">
          Chunk #{source.chunk_index}
        </span>
      </div>

      <div className="space-y-1 mt-2">
        <div className="flex items-center justify-between text-[11px] font-mono text-stone">
          <span>Confidence</span>
          <span className="text-pine font-medium">
            {percentage}% ({source.score.toFixed(3)})
          </span>
        </div>
        <div className="w-full bg-paper rounded-full h-1.5 overflow-hidden border border-moss/10">
          <div
            className="bg-pine h-full rounded-full transition-all duration-500 ease-out"
            style={{ width: `${percentage}%` }}
          />
        </div>
      </div>
    </div>
  );
};
