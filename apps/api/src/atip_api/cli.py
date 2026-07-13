"""Operational CLI: `uv run python -m atip_api.cli <command> [...]`.

Commands run in-process against the configured database — they are for
operators (deploy user on the VPS, developers locally), not for end users.
"""

import argparse
import asyncio
import logging
import sys

from sqlalchemy import select

from atip_api.config import get_settings
from atip_api.db import get_session_factory
from atip_api.models import Document, DocumentStatus, JobStatus, ProcessingJob
from atip_api.observability import configure_logging

logger = logging.getLogger(__name__)


async def backfill_chunks() -> int:
    """Reprocess every READY document to refresh chunk structural metadata.

    Chunk ids are derived from position + content hash, so unchanged text keeps
    its id and its embedding: the backfill updates the lineage columns
    (parent_clause_id, section_path) in place and never re-embeds. Safe to run
    while the app is serving traffic; documents flip through PROCESSING and
    back to READY one at a time.
    """
    from atip_api.processing.pipeline import process_document

    session_factory = get_session_factory()
    async with session_factory() as session:
        documents = (
            await session.scalars(
                select(Document)
                .where(Document.status == DocumentStatus.READY)
                .order_by(Document.created_at)
            )
        ).all()
    logger.info("Backfilling chunk metadata for %d READY documents", len(documents))

    failed = 0
    for document in documents:
        async with session_factory() as session:
            job = ProcessingJob(document_id=document.id)
            session.add(job)
            await session.commit()
            job_id = job.id
        await process_document(document.id, job_id)
        async with session_factory() as session:
            finished = await session.get(ProcessingJob, job_id)
            if finished is None or finished.status != JobStatus.READY:
                failed += 1
                message = finished.error_message if finished else "job row missing"
                logger.error("Backfill failed for document %s: %s", document.id, message)

    logger.info("Backfill complete: %d ok, %d failed", len(documents) - failed, failed)
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="atip_api.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "backfill-chunks",
        help="reprocess READY documents to populate chunk structural metadata",
    )
    args = parser.parse_args(argv)

    configure_logging(get_settings())
    if args.command == "backfill-chunks":
        return asyncio.run(backfill_chunks())
    parser.error(f"unknown command {args.command!r}")
    return 2  # unreachable; parser.error exits


if __name__ == "__main__":
    sys.exit(main())
