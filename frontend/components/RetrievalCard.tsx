'use client';

import React from 'react';
import { SourceInfo } from '@/lib/types';

interface RetrievalCardProps {
  source: SourceInfo;
  index: number;
}

export const RetrievalCard: React.FC<RetrievalCardProps> = ({ source, index }) => {
  const percentage = Math.min(100, Math.max(0, Math.round(source.score * 100)));

  return (
    <div
      className="retrieval-card-stagger w-full bg-paper/60 hover:bg-card border border-moss/20 hover:border-moss/40 rounded-md p-3 transition-all duration-150 flex flex-col justify-between"
      style={{
        animationDelay: `${index * 40}ms`,
      }}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <span
          className="font-mono text-xs font-semibold text-ink truncate block flex-1"
          title={source.file}
        >
          {source.file}
        </span>

        <span className="font-mono text-[11px] px-1.5 py-0.5 rounded bg-paper text-stone border border-moss/15 flex-shrink-0">
          Chunk #{source.chunk_index}
        </span>
      </div>

      <div className="space-y-1">
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
