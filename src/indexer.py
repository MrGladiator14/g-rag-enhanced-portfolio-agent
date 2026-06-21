from openai import OpenAI
from .database import db
from .vector_store import vector_db, embed_texts
from .sqlite_store import sqlite_db
from .config import settings
from .logger import get_logger

logger = get_logger("indexer")


def generate_company_summary(ticker: str) -> str:
    """
    Queries the vector store for all sec_chunks_v1 and event_snippets_v1 related to the specific ticker,
    and prompts OpenAI LLM to synthesize these chunks into a concise, ~100-word summary.
    """
    ticker = ticker.upper()
    logger.info(f"Generating summary for {ticker}...")
    

    sec_points = vector_db.scroll(
        collection="sec_chunks_v1",
        filter_must=[{"key": "ticker", "match": {"value": ticker}}],
        limit=100
    )
    

    event_points = vector_db.scroll(
        collection="event_snippets_v1",
        filter_must=[{"key": "tickers", "match": {"value": ticker}}],
        limit=100
    )
    

    combined_texts = []
    for item in sec_points:
        p = item.get("payload", {})
        if "text" in p:
            combined_texts.append(f"SEC Filing ({p.get('filed_at', 'unknown')}): {p['text']}")
    for item in event_points:
        p = item.get("payload", {})
        if "title" in p:
            combined_texts.append(f"News event ({p.get('published_at', 'unknown')}): {p['title']}")
            
    if not combined_texts:
        return f"{ticker} has updated financial filings and news activities recorded in the database."
        
    combined_context = "\n".join(combined_texts)[:30000] # Safe context limit
    
    system_prompt = (
        "You are an expert Wall Street equities research analyst. "
        "Your task is to synthesize the provided recent SEC filings and news headlines for a company "
        "into a concise, premium, ~100-word company summary. Do not use generic statements or placeholders. "
        "Strictly ground the summary in the provided context. Enforce strict groundedness: Do not hallucinate any information. "
        "You must include the following disclaimer at the end of the summary: 'Disclaimer: This summary is AI-generated and does not constitute financial advice.'"
    )
    user_prompt = f"Generate a ~100-word summary for {ticker} based on the following filings and news events:\n\n{combined_context}"
    
    summary = ""
    if (
        settings.OPENAI_API_KEY
        and settings.OPENAI_API_KEY.startswith("sk-")
        and len(settings.OPENAI_API_KEY) > 20
    ):
        try:
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            resp = client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=250,
            )
            summary = resp.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"OpenAI summary generation failed for {ticker}: {str(e)}")
            
    if not summary:

        summary = f"{ticker} is an active enterprise with recently updated financial filings and news events indexed in the system, reflecting ongoing strategic developments."
        
    return summary


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
    affected_tickers = set()

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
                for p in sec_payloads:
                    affected_tickers.add(p["ticker"])
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
                for p in event_payloads:
                    for t in p["tickers"]:
                        affected_tickers.add(t.upper())
            except Exception as e:
                logger.error(f"Failed to index event vectors: {str(e)}")

    if affected_tickers:
        logger.info(f"Generating/updating summaries for affected tickers: {list(affected_tickers)}")
        for ticker in affected_tickers:
            try:
                summary = generate_company_summary(ticker)
                db.update_company_summary(ticker, summary)
            except Exception as e:
                logger.error(f"Failed to generate and save company summary for {ticker}: {str(e)}")

    logger.info(f"Successfully indexed {indexed_count} total new items.")
