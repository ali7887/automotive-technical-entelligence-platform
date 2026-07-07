# Data Model (MVP)

## PostgreSQL Entities
- **Workspace**: id (uuid, PK), name, created_at
- **Document**: id (uuid, PK), workspace_id (FK), name, status (processing status enum), storage_path, created_at
- **ProcessingJob**: id (uuid, PK), document_id (FK), status, error_message, updated_at
- **Chunk**: id (uuid, PK, deterministic UUIDv5 of document+index+content hash), document_id (FK), workspace_id (FK), chunk_index, page_start, page_end, clause_id (nullable), heading (nullable), text, token_count, content_hash, embedded_at (nullable), text_search (generated tsvector, GIN-indexed)

## Qdrant Payload Scheme (Semantic Chunk Store)
- Vector Dimension: 1536 (default for OpenAI text-embedding-3-small)
- Payload Schema:
  - `postgres_chunk_id`: string (UUID mapping back to PG metadata)
  - `version_id`: string (UUID)
  - `document_id`: string (UUID)
  - `clause_id`: string (nullable)
  - `chunk_text`: string
  - `page_start`: integer
