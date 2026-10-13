-- ==============================================================================
-- DocuMind: Supabase PostgreSQL + pgvector Schema
-- 100% Free Production Tier Configuration
-- ==============================================================================

-- 1. Enable the pgvector extension for similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Create documents table (tracks uploaded files and metadata)
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    session_id TEXT NOT NULL DEFAULT 'default',
    size_bytes BIGINT DEFAULT 0,
    chunk_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_document_per_session UNIQUE (name, session_id)
);

-- 3. Create document_sections table (stores text chunks and 768-dim embeddings from Gemini)
CREATE TABLE IF NOT EXISTS document_sections (
    id BIGSERIAL PRIMARY KEY,
    document_name TEXT NOT NULL,
    session_id TEXT NOT NULL DEFAULT 'default',
    page_number INTEGER DEFAULT 1,
    content TEXT NOT NULL,
    embedding VECTOR(768), -- Gemini text-embedding-004 produces 768 dimensions
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Fast search indexes
-- HNSW index for ultra-fast approximate nearest neighbor cosine distance search
CREATE INDEX IF NOT EXISTS document_sections_embedding_hnsw_idx
ON document_sections
USING hnsw (embedding vector_cosine_ops);

-- Composite index for fast session and document filtering
CREATE INDEX IF NOT EXISTS document_sections_session_doc_idx
ON document_sections (session_id, document_name);

CREATE INDEX IF NOT EXISTS documents_session_idx
ON documents (session_id);

-- 5. Stored Procedure: match_documents
-- Efficiently searches for top-K matching sections using cosine similarity
CREATE OR REPLACE FUNCTION match_documents (
    query_embedding VECTOR(768),
    match_count INT DEFAULT 8,
    filter_sources TEXT[] DEFAULT NULL,
    filter_session TEXT DEFAULT 'default'
)
RETURNS TABLE (
    id BIGINT,
    document_name TEXT,
    page_number INT,
    content TEXT,
    metadata JSONB,
    similarity FLOAT
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RETURN QUERY
    SELECT
        ds.id,
        ds.document_name,
        ds.page_number,
        ds.content,
        ds.metadata,
        1 - (ds.embedding <=> query_embedding) AS similarity
    FROM document_sections ds
    WHERE ds.session_id = filter_session
      AND (filter_sources IS NULL OR array_length(filter_sources, 1) IS NULL OR ds.document_name = ANY(filter_sources))
    ORDER BY ds.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- 6. Grants & Row Level Security
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_sections ENABLE ROW LEVEL SECURITY;

-- Allow access via Supabase anon / service key
CREATE POLICY "Allow public all access to documents"
ON documents FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Allow public all access to document_sections"
ON document_sections FOR ALL USING (true) WITH CHECK (true);

-- Grant schema and table permissions to anon and authenticated roles
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
GRANT ALL ON TABLE public.documents TO anon, authenticated, service_role;
GRANT ALL ON TABLE public.document_sections TO anon, authenticated, service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.match_documents TO anon, authenticated, service_role;
