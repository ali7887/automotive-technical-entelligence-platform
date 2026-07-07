# Document Processing

## Steps
1) Validate PDF size/type
2) Extract text per page
3) Detect headings + clause numbering (e.g. "6.4.3.1")
4) Chunk text (350-600 tokens target)
5) Compute hash and metadata
6) Save metadata to Postgres & Upsert vector to Qdrant
7) Set ProcessingJob to READY
