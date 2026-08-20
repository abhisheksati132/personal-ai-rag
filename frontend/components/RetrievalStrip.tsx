'use client';

import React from 'react';
import { SourceInfo } from '@/lib/types';
import { RetrievalCard } from './RetrievalCard';

interface RetrievalStripProps {
  sources: SourceInfo[];
}

export const RetrievalStrip: React.FC<RetrievalStripProps> = ({ sources }) => {
  if (!sources || sources.length === 0) return null;

  return (
    <div className="mt-4 pt-3.5 border-t border-moss/15">
      <div className="flex items-center gap-2 mb-2.5">
        <div className="w-1.5 h-1.5 rounded-full bg-pine" />
        <span className="font-mono text-[10.5px] tracking-wider uppercase text-moss font-semibold">
          Evidence Trail ({sources.length} {sources.length === 1 ? 'Chunk' : 'Chunks'} Cited)
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5 pt-0.5">
        {sources.map((source, idx) => (
          <RetrievalCard
            key={`${source.file}-${source.chunk_index}-${idx}`}
            source={source}
            index={idx}
          />
        ))}
      </div>
    </div>
  );

};
