-- RAG Pipeline Database Schema for Supabase
-- YouTube Video Processing: videos → transcripts → chunks with pgvector embeddings

CREATE EXTENSION IF NOT EXISTS vector;

-- User Profiles Table
CREATE TABLE user_profiles (
  ID uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT NOT NULL UNIQUE,
  full_name TEXT,
  is_admin BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);


-- Videos table: stores metadata for each YouTube video processed
CREATE TABLE video (
  ID uuid PRIMARY KEY DEFAULT gen_random_uuid(), -- per la riga nel DB
  ID_user uuid REFERENCES user_profiles(ID) ON DELETE CASCADE,
  ID_video TEXT UNIQUE NOT NULL, -- per il video specifico, ognuno ha il suo ID da YouTube
  title TEXT CHECK(char_length(title) <= 100),
  ID_channel TEXT NOT NULL CHECK (char_length(ID_channel) = 24 AND ID_channel ~ '^UC[A-Za-z0-9_-]{22}$'),
  summary TEXT CHECK(char_length(summary) <= 200),
  url TEXT UNIQUE NOT NULL,
  duration INT CHECK(duration > 0),
  published_at TIMESTAMPTZ,
  processed_at TIMESTAMPTZ DEFAULT NOW()
);

-- Transcripts table: full transcriptions with language and raw data
CREATE TABLE transcript(
  ID uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  language TEXT CHECK(language IN ('ITA', 'EN')),
  raw_transcript TEXT NOT NULL,
  final_transcript TEXT NOT NULL,
  ID_video uuid REFERENCES video(ID) ON DELETE CASCADE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Chunks table: chunked transcript segments with embeddings for RAG retrieval
CREATE TABLE chunk(
  ID uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ID_transcript uuid REFERENCES transcript(ID) ON DELETE CASCADE,
  chunk_text TEXT CHECK(char_length(chunk_text) <= 512),
  chunk_index INT NOT NULL,
  start_time numeric(10,3) CHECK(start_time >= 0),
  end_time numeric(10,3) CHECK(end_time >= start_time),
  tokens INT CHECK(tokens <= 512),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  embedding vector(1536)
);

-- RAG Pipeline State Table
CREATE TABLE ragPipelineState (
  ID_pipeline TEXT PRIMARY KEY,
  last_check_time TIMESTAMPTZ,
  last_run TIMESTAMPTZ,
  known_videos JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance optimization
CREATE INDEX chunk_embedding_idx ON chunk USING hnsw (embedding vector_cosine_ops);
CREATE INDEX transcript_idvideo_idx ON transcript(ID_video);
CREATE INDEX chunk_idtranscript_idx ON chunk(ID_transcript);

-- ==============================================================================
-- FUNCTIONS
-- ==============================================================================

-- 1. Handle New User - Sync auth.users to user_profiles
CREATE OR REPLACE FUNCTION public.handle_new_user() 
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.user_profiles (id, email, full_name)
    VALUES (NEW.id, NEW.email, NEW.raw_user_meta_data->>'full_name');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 2. Update timestamp automaticamente
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 3. Vector similarity search per RAG retrieval
CREATE OR REPLACE FUNCTION match_chunks(
  query_embedding vector(1536),
  match_count int DEFAULT 5,
  filter jsonb DEFAULT '{}'
) 
RETURNS TABLE (
  id uuid,
  chunk_text text,
  chunk_index int,
  start_time numeric,
  end_time numeric,
  video_url text,
  video_title text,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT 
    c.ID,
    c.chunk_text,
    c.chunk_index,
    c.start_time,
    c.end_time,
    v.url,
    v.title,
    1 - (c.embedding <=> query_embedding) as similarity
  FROM chunk c
  JOIN transcript t ON c.ID_transcript = t.ID
  JOIN video v ON t.ID_video = v.ID
  WHERE 
    CASE 
      WHEN filter ? 'ID_channel' THEN v.ID_channel = (filter->>'ID_channel')
      ELSE TRUE
    END
  ORDER BY c.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- 4. Helper function: check if admin
CREATE OR REPLACE FUNCTION is_admin()
RETURNS BOOLEAN AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM user_profiles
    WHERE id = auth.uid() AND is_admin = TRUE
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ==============================================================================
-- TRIGGERS
-- ==============================================================================

-- 1. Trigger su auth.users per creare automaticamente user_profiles
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW
  EXECUTE FUNCTION public.handle_new_user();

-- 2. Trigger per aggiornare updatedAt su user_profiles
CREATE TRIGGER update_user_profiles_updated_at
  BEFORE UPDATE ON user_profiles
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at();

-- 3. Trigger per aggiornare updatedAt su ragPipelineState
CREATE TRIGGER update_rag_pipeline_state_updated_at
  BEFORE UPDATE ON ragPipelineState
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at();



-- Abilita RLS sulla tabella
ALTER TABLE video ENABLE ROW LEVEL SECURITY;

-- Policy: gli admin possono vedere tutto
CREATE POLICY "Admins can view all videos"
  ON video
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM user_profiles 
      WHERE id = auth.uid() AND is_admin = TRUE
    )
  );

-- Policy: gli utenti normali vedono solo i loro video
CREATE POLICY "Users can view their own videos"
  ON video
  FOR SELECT
  USING (ID_user = auth.uid());

-- Policy: solo admin possono inserire video
CREATE POLICY "Only admins can insert videos"
  ON video
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM user_profiles 
      WHERE id = auth.uid() AND is_admin = TRUE
    )
  );