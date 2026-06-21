import os
import json
import hashlib
from typing import Optional, List
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from .config import settings
from .logger import setup_logging, get_logger
from .database import db
from .vector_store import vector_db
from .sqlite_store import sqlite_db
from .indexer import index_pending_items
from .data_generator import generate_local_gdelt_data
from .agent import compiled_graph

setup_logging()
logger = get_logger("app")
app = FastAPI(
    title="FinGraphRAG US Equities Portfolio Agent Platform",
    description="Stateful portfolio analysis using LangGraph, Neo4j, Qdrant, and OpenAI",
    version="1.0.0",
)


class HoldingItem(BaseModel):
    ticker: str
    weight: float


class QueryRequest(BaseModel):
    query: str
    portfolio: Optional[List[HoldingItem]] = None
    session_id: Optional[str] = "default_session"


class QueryResponse(BaseModel):
    query: str
    insight: str
    events_found: int
    indexed_count: int
    logs: List[str]


class SECFilingModel(BaseModel):
    ticker: str
    form_type: str
    filed_at: str
    accession_no: str
    url: str
    text: str


class GDELTEventModel(BaseModel):
    event_id: str
    title: str
    source: str
    url: str
    published_at: str
    tickers: List[str]


@app.post("/api/query", response_model=QueryResponse)
async def handle_agent_query(req: QueryRequest):
    """
    Triggers the stateful LangGraph agent to generate strategic portfolio risk and competitive insights.
    """
    logger.info(
        "Received portfolio query request",
        extra={"query": req.query, "session_id": req.session_id},
    )
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    try:
        portfolio_state = []
        if req.portfolio:
            portfolio_state = [
                {"ticker": h.ticker.upper(), "weight": h.weight} for h in req.portfolio
            ]
        initial_state = {
            "query": req.query,
            "portfolio": portfolio_state,
            "session_id": req.session_id or "default_session",
            "sec_filings": [],
            "gdelt_events": [],
            "indexed_count": 0,
            "neo4j_context": [],
            "vector_context": [],
            "insight": "",
            "logs": [],
        }
        final_state = compiled_graph.invoke(initial_state)
        return QueryResponse(
            query=req.query,
            insight=final_state["insight"],
            events_found=len(final_state.get("gdelt_events", []))
            + len(final_state.get("sec_filings", [])),
            indexed_count=final_state["indexed_count"],
            logs=final_state["logs"],
        )
    except Exception as e:
        logger.error(
            "Error executing agent query",
            extra={"query": req.query, "error": str(e)},
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Agent portfolio workflow execution failed: {str(e)}",
        )


@app.post("/api/add_sec_filing")
async def add_sec_filing(filing: SECFilingModel):
    success = sqlite_db.add_sec_filing(filing.dict())
    if not success:
        raise HTTPException(
            status_code=400, detail="Failed to insert or filing already exists."
        )
    index_pending_items()
    return {"status": "success", "message": "SEC filing added and indexed."}


@app.post("/api/add_gdelt_event")
async def add_gdelt_event(event: GDELTEventModel):
    success = sqlite_db.add_gdelt_event(event.dict())
    if not success:
        raise HTTPException(
            status_code=400, detail="Failed to insert or event already exists."
        )
    index_pending_items()
    return {"status": "success", "message": "GDELT event added and indexed."}


@app.get("/api/graph")
async def get_graph_visualizations():
    """
    Returns the network representation of the Neo4j knowledge graph
    for frontend rendering with D3/Vis.js.
    """
    try:
        graph_data = db.get_graph_visual()
        return graph_data
    except Exception as e:
        logger.error(
            "Failed to retrieve graph visualization data", extra={"error": str(e)}
        )
        raise HTTPException(status_code=500, detail=str(e))


def _seed_from_json():
    sec_path = os.path.join(settings.DATA_DIR, "sec_filings.json")
    if os.path.exists(sec_path):
        with open(sec_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            for item in data:
                sqlite_db.add_sec_filing(item)
    news_path = os.path.join(settings.DATA_DIR, "gdelt_events.json")
    if os.path.exists(news_path):
        with open(news_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            for item in data:
                sqlite_db.add_gdelt_event(item)


@app.post("/api/reset")
async def reset_agent_database():
    """
    Checks for changes in the local JSON files and incrementally ingests only the new entities.
    """
    logger.info("Triggering database update check.")
    
    sec_path = os.path.join(settings.DATA_DIR, "sec_filings.json")
    news_path = os.path.join(settings.DATA_DIR, "gdelt_events.json")
    hash_path = os.path.join(settings.DATA_DIR, ".data_hash.json")
    
    current_hash = hashlib.md5()
    if os.path.exists(sec_path):
        with open(sec_path, "rb") as f:
            current_hash.update(f.read())
    if os.path.exists(news_path):
        with open(news_path, "rb") as f:
            current_hash.update(f.read())
            
    current_digest = current_hash.hexdigest()
    
    if os.path.exists(hash_path):
        try:
            with open(hash_path, "r") as f:
                saved_hash = json.load(f).get("hash")
            if saved_hash == current_digest:
                logger.info("No changes in data files. Skipping update.")
                return {
                    "status": "skipped",
                    "message": "No changes detected in JSON files. Database update skipped."
                }
        except Exception:
            pass

    logger.info("Changes detected or first run. Proceeding with incremental database update.")
    try:
        _seed_from_json()
        index_pending_items()
        
        default_holdings = [
            {"ticker": "AAPL", "weight": 0.4},
            {"ticker": "NVDA", "weight": 0.4},
            {"ticker": "AMZN", "weight": 0.2},
        ]
        db.add_portfolio("default_session", default_holdings)
        db.add_company_sector("AAPL", "Information Technology")
        db.add_company_sector("NVDA", "Information Technology")
        db.add_company_sector("AMZN", "Consumer Discretionary")
        db.add_peers("AAPL", ["MSFT", "NVDA"])
        db.add_peers("NVDA", ["AAPL", "MSFT"])
        db.add_peers("AMZN", ["TSLA"])
        
        with open(hash_path, "w") as f:
            json.dump({"hash": current_digest}, f)
            
        return {
            "status": "success",
            "message": "Database incrementally updated. New entities ingested and default holdings pre-seeded.",
        }
    except Exception as e:
        logger.error("Failed to complete database update", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Update operation failed: {str(e)}")


static_path = str(settings.STATIC_DIR)
os.makedirs(static_path, exist_ok=True)


@app.get("/")
async def serve_index():
    index_file = os.path.join(static_path, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {
        "message": "FinGraphRAG US Equities Agent API is running. Frontend static index.html not found."
    }


app.mount("/static", StaticFiles(directory=static_path), name="static")


@app.on_event("startup")
async def startup_event():
    logger.info("Initializing system and verifying local financial data files...")
    os.makedirs(str(settings.DATA_DIR), exist_ok=True)
    has_sec = os.path.exists(os.path.join(str(settings.DATA_DIR), "sec_filings.json"))
    has_news = os.path.exists(os.path.join(str(settings.DATA_DIR), "gdelt_events.json"))
    if not has_sec or not has_news:
        logger.info(
            "No local mock financial files detected on startup. Auto-generating fresh files..."
        )
        generate_local_gdelt_data(str(settings.DATA_DIR))
        try:
            db.reset_db()
            vector_db.reset_store()
            logger.info(
                "Pre-seeding graph database with initial default portfolio holdings..."
            )
            default_holdings = [
                {"ticker": "AAPL", "weight": 0.4},
                {"ticker": "NVDA", "weight": 0.4},
                {"ticker": "AMZN", "weight": 0.2},
            ]
            db.add_portfolio("default_session", default_holdings)
            db.add_company_sector("AAPL", "Information Technology")
            db.add_company_sector("NVDA", "Information Technology")
            db.add_company_sector("AMZN", "Consumer Discretionary")
            db.add_peers("AAPL", ["MSFT", "NVDA"])
            db.add_peers("NVDA", ["AAPL", "MSFT"])
            db.add_peers("AMZN", ["TSLA"])
        except Exception as e:
            logger.warning(
                "Failed to pre-seed graph during startup", extra={"error": str(e)}
            )
    _seed_from_json()
    index_pending_items()
    logger.info("System successfully initialized.")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.app:app", host=settings.HOST, port=settings.PORT, reload=True)
