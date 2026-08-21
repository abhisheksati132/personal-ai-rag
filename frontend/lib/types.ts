export interface SourceInfo {
  file: string;
  chunk_index: number;
  score: number;
}

export interface QueryResponse {
  answer: string;
  sources: SourceInfo[];
  provider?: 'local' | 'cloud';
  model?: string;
}

export interface IndexedFile {
  file_path: string;
  file_name: string;
  file_hash: string;
  file_size: number;
  mtime: number;
  chunk_count: number;
  indexed_at: number;
  status: 'indexed' | 'failed' | string;
  error_message?: string | null;
}

export interface HealthResponse {
  status: string;
  ollama_connected: boolean;
  groq_configured?: boolean;
  embedding_model: string;
  llm_model: string;
  groq_model?: string;
  indexed_files: number;
  total_vectors: number;
}

export interface StatsResponse {
  total_files: number;
  indexed_files: number;
  failed_files: number;
  total_chunks: number;
  total_bytes: number;
  last_indexed_at?: number | null;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  sources?: SourceInfo[];
  provider?: 'local' | 'cloud';
  model?: string;
  timestamp: number;
  isError?: boolean;
  errorMessage?: string;
}

