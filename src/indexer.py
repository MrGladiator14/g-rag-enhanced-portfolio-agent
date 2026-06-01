from .database import db
from .vector_store import vector_db, embed_texts
from .sqlite_store import sqlite_db
from .logger import get_logger

logger = get_logger("indexer")


def index_pending_items():
    """
    Fetches unindexed items from SQLite, indexes them into Neo4j and Qdrant,
    and then marks them as indexed in SQLite.
    """
    sec_filings = sqlite_db.get_unindexed_sec_filings()
    gdelt_events = sqlite_db.get_unindexed_gdelt_events()
    if not sec_filings and not gdelt_events:
        logger.info("No new items to index.")
        return
    indexed_count = 0
    if sec_filings:
        logger.info(f"Indexing {len(sec_filings)} new SEC filings...")
        sec_texts = []
        sec_ids = []
        sec_payloads = []
        indexed_accessions = []
        for f in sec_filings:
            ticker = f["ticker"].upper()
            acc = f["accession_no"]
            try:
                db.add_sec_filing(
                    ticker=ticker,
                    form_type=f["form_type"],
                    date=f["filed_at"],
                    accession_no=acc,
                    url=f["url"],
                )
                sec_texts.append(f["text"])
                sec_ids.append(f"sec_{acc}")
                sec_payloads.append(
                    {
                        "source_type": "sec",
                        "ticker": ticker,
                        "accession_no": acc,
                        "form_type": f["form_type"],
                        "filed_at": f["filed_at"],
                        "url": f["url"],
                        "text": f["text"],
                    }
                )
                indexed_accessions.append(acc)
                indexed_count += 1
            except Exception as e:
                logger.error(f"Failed to index SEC filing {acc}: {str(e)}")
        if sec_texts:
            try:
                vectors = embed_texts(sec_texts)
                vector_db.upsert_points("sec_chunks_v1", sec_ids, vectors, sec_payloads)
                sqlite_db.mark_sec_filings_indexed(indexed_accessions)
            except Exception as e:
                logger.error(f"Failed to index SEC vectors: {str(e)}")
    if gdelt_events:
        logger.info(f"Indexing {len(gdelt_events)} new GDELT events...")
        event_texts = []
        event_ids = []
        event_payloads = []
        indexed_event_ids = []
        for ev in gdelt_events:
            ev_id = ev["event_id"]
            try:
                db.add_gdelt_event(
                    event_id=ev_id,
                    title=ev["title"],
                    source=ev["source"],
                    url=ev["url"],
                    date=ev["published_at"],
                    tickers=ev["tickers"],
                )
                event_texts.append(ev["title"])
                event_ids.append(f"news_{ev_id}")
                event_payloads.append(
                    {
                        "source_type": "news",
                        "event_id": ev_id,
                        "title": ev["title"],
                        "source": ev["source"],
                        "url": ev["url"],
                        "published_at": ev["published_at"],
                        "tickers": ev["tickers"],
                    }
                )
                indexed_event_ids.append(ev_id)
                indexed_count += 1
            except Exception as e:
                logger.error(f"Failed to index event {ev_id}: {str(e)}")
        if event_texts:
            try:
                vectors = embed_texts(event_texts)
                vector_db.upsert_points(
                    "event_snippets_v1", event_ids, vectors, event_payloads
                )
                sqlite_db.mark_gdelt_events_indexed(indexed_event_ids)
            except Exception as e:
                logger.error(f"Failed to index event vectors: {str(e)}")
    logger.info(f"Successfully indexed {indexed_count} total new items.")
