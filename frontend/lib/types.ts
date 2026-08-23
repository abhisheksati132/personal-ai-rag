export interface SourceInfo {
  file: string;
  chunk_index: number;
  score: number;
  source_type?: 'file' | 'bookmark';
  title?: string;
  url?: string;
  folder?: string;
}

export interface QueryResponse {
  answer: string;
  sources: SourceInfo[];
  provider?: 'local' | 'cloud';
  model?: string;
  session_id?: string;
}

export interface SessionItem {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
  message_count: number;
  first_query_preview?: string | null;
}

export interface StoredMessage {
  id: string;
  session_id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: SourceInfo[];
  provider?: 'local' | 'cloud';
  model?: string;
  created_at: number;
}

export interface SessionDetail {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
  messages: StoredMessage[];
}


export interface IndexedFile {
  item_type?: 'file' | 'bookmark';
  file_path: string;
  file_name: string;
  file_hash: string;
  file_size: number;
  mtime: number;
  chunk_count: number;
  indexed_at: number;
  status: 'indexed' | 'failed' | string;
  error_message?: string | null;
  url?: string | null;
  folder?: string | null;
}

export interface HealthResponse {
  status: string;
  ollama_connected: boolean;
  groq_configured?: boolean;
  embedding_model: string;
  llm_model: string;
  groq_model?: string;
  indexed_files: number;
  indexed_bookmarks?: number;
  total_vectors: number;
}

export interface StatsResponse {
  total_files: number;
  indexed_files: number;
  failed_files: number;
  total_bookmarks?: number;
  indexed_bookmarks?: number;
  failed_bookmarks?: number;
  total_items?: number;
  indexed_items?: number;
  failed_items?: number;
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
