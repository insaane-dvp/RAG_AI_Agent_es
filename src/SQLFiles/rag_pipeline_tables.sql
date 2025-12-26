-- RAG Pipeline Database Schema for Supabase
-- YouTube Video Processing: videos → transcripts → chunks with pgvector embeddings

DROP DATABASE IF EXISTS RAG_Agent_ColeMedin;
CREATE DATABASE RAG_Agent_ColeMedin;
CREATE EXTENSION IF NOT EXISTS vector;

-- User Profiles Table
CREATE TABLE user (
  ID uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT NOT NULL UNIQUE,
  fullName TEXT,
  isAdmin BOOLEAN DEFAULT FALSE,
  createdAt TIMESTAMPTZ DEFAULT NOW(),
  updatedAt TIMESTAMPTZ DEFAULT NOW()
);


-- Videos table: stores metadata for each YouTube video processed
CREATE TABLE video (
  ID uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  IDUser uuid REFERENCES user(ID) ON DELETE CASCADE,
  IDvideo TEXT UNIQUE NOT NULL,
  title TEXT CHECK(char_length(title) <= 100),
  IDChannel TEXT NOT NULL,
  summary TEXT CHECK(char_length(summary) <= 200),
  url TEXT UNIQUE NOT NULL,
  duration INT CHECK(duration > 0),
  publishedAt TIMESTAMPTZ,
  processedAt TIMESTAMPTZ DEFAULT NOW()
);

-- Transcripts table: full transcriptions with language and raw data
CREATE TABLE transcript(
  ID uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  language TEXT CHECK(language IN ('ITA', 'EN')),
  rawTranscript TEXT NOT NULL,
  finalTranscript TEXT NOT NULL,
  IDvideo uuid REFERENCES video(ID) ON DELETE CASCADE,
  createdAt TIMESTAMPTZ DEFAULT NOW()
);

-- Chunks table: chunked transcript segments with embeddings for RAG retrieval
CREATE TABLE chunk(
  ID uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  IDTranscript uuid REFERENCES transcript(ID) ON DELETE CASCADE,
  chunkText TEXT CHECK(char_length(chunkText) <= 512),
  chunkIndex INT NOT NULL,
  startTime numeric(10,3) CHECK(startTime >= 0),
  endTime numeric(10,3) CHECK(endTime >= startTime),
  tokens INT CHECK(tokens <= 512),
  createdAt TIMESTAMPTZ DEFAULT NOW(),
  embedding vector(1536)
);

-- RAG Pipeline State Table
CREATE TABLE ragPipelineState (
  IDPipeline TEXT PRIMARY KEY,
  lastCheckTime TIMESTAMPTZ,
  lastRun TIMESTAMPTZ,
  knownVideos JSONB DEFAULT '{}'::jsonb,
  createdAt TIMESTAMPTZ DEFAULT NOW(),
  updatedAt TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance optimization
CREATE INDEX chunk_embedding_idx ON chunk USING hnsw (embedding vector_cosine_ops);
CREATE INDEX transcript_idvideo_idx ON transcript(IDvideo);
CREATE INDEX chunk_idtranscript_idx ON chunk(IDTranscript);
