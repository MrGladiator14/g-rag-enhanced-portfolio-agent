import json
from typing import Dict, List, Any, TypedDict
from langgraph.graph import StateGraph, END
from openai import OpenAI
from .config import settings
from .logger import get_logger
from .database import db
from .vector_store import vector_db, embed_texts
from .tracing import trace_agent_step

logger = get_logger("agent")
SECTOR_MAP = {
    "AAPL": "Information Technology",
    "MSFT": "Information Technology",
    "NVDA": "Information Technology",
    "TSLA": "Consumer Discretionary",
    "AMZN": "Consumer Discretionary",
    "GOOG": "Communication Services",
    "META": "Communication Services",
    "NFLX": "Communication Services",
}


def get_peers(ticker: str) -> List[str]:
    sector = SECTOR_MAP.get(ticker.upper(), "Unknown")
    if sector == "Unknown":
        return []
    return [t for t, s in SECTOR_MAP.items() if s == sector and t != ticker.upper()]


class AgentState(TypedDict):
    query: str
    portfolio: List[Dict[str, Any]]
    session_id: str
    sec_filings: List[Dict[str, Any]]
    gdelt_events: List[Dict[str, Any]]
    indexed_count: int
    neo4j_context: List[Dict[str, Any]]
    vector_context: List[Dict[str, Any]]
    insight: str
    logs: List[str]


@trace_agent_step("Prepare Portfolio State")
def prepare_portfolio(state: AgentState) -> Dict[str, Any]:
    """
    Validates query and active portfolio tickers.
    """
    query = state.get("query", "").strip()
    portfolio = state.get("portfolio", [])
    logs = state.get("logs", [])
    logs.append(f"Analyzing query: '{query}'")
    if not portfolio:
        portfolio = [
            {"ticker": "AAPL", "weight": 0.4},
            {"ticker": "NVDA", "weight": 0.4},
            {"ticker": "AMZN", "weight": 0.2},
        ]
        logs.append(
            "No portfolio found in state. Using default tech portfolio: AAPL (40%), NVDA (40%), AMZN (20%)"
        )
    tickers = {h["ticker"].upper() for h in portfolio}
    logs.append(f"Target portfolio tickers: {list(tickers)}")
    return {"portfolio": portfolio, "logs": logs}


@trace_agent_step("Index Portfolio Structure")
def index_portfolio_structure(state: AgentState) -> Dict[str, Any]:
    """
    Populates current session portfolio structure in Neo4j.
    """
    session_id = state.get("session_id", "default_session")
    portfolio = state.get("portfolio", [])
    logs = state.get("logs", [])
    logs.append("Indexing portfolio structure and weights in graph database...")
    try:
        db.add_portfolio(session_id, portfolio)
        for holding in portfolio:
            ticker = holding["ticker"].upper()
            sector = SECTOR_MAP.get(ticker, "Information Technology")
            db.add_company_sector(ticker, sector)
            db.add_peers(ticker, get_peers(ticker))
        logs.append(
            "Successfully indexed portfolio nodes, sector mapping, and peer linkages in graph."
        )
    except Exception as e:
        logs.append(f"Failed to index portfolio in graph: {str(e)}")
    return {"indexed_count": len(portfolio), "logs": logs}


@trace_agent_step("Synthesize GraphRAG Answer")
def synthesize_portfolio_insight(state: AgentState) -> Dict[str, Any]:
    """
    Queries Graph for 1-hop context, then constrains vector search to retrieved IDs,
    then invokes OpenAI to output a premium US equities portfolio analysis report.
    """
    query = state.get("query", "")
    portfolio = state.get("portfolio", [])
    logs = state.get("logs", [])
    logs.append("Executing Graph-First Context Retrieval...")
    search_ticker = "AAPL"
    for holding in portfolio:
        t = holding["ticker"].upper()
        if t in query.upper():
            search_ticker = t
            break
    graph_context = db.query_subgraph(search_ticker)
    logs.append(
        f"Retrieved 1-hop graph neighborhood context for primary hub {search_ticker}."
    )
    extracted_accessions = []
    extracted_event_ids = []
    context_str = "## Graph Neighbors & Mappings:\n"
    seen_relations = set()
    for item in graph_context:
        ticker = item["ticker"]
        sector = item["sector"]
        rel1 = f"{ticker} in sector {sector}"
        if rel1 not in seen_relations:
            context_str += f"- {rel1}\n"
            seen_relations.add(rel1)
        f_form = item.get("filing_form")
        f_date = item.get("filing_date")
        acc = item.get("accession_no")
        if f_form and f_date:
            rel2 = f"{ticker} filed {f_form} on {f_date}"
            if rel2 not in seen_relations:
                context_str += f"- {rel2}\n"
                seen_relations.add(rel2)
            if acc:
                extracted_accessions.append(f"sec_{acc}")
        e_title = item.get("event_title")
        e_date = item.get("event_date")
        ev_id = item.get("event_id")
        if e_title and e_date:
            rel3 = f"News event mentions {ticker} on {e_date}: '{e_title}'"
            if rel3 not in seen_relations:
                context_str += f"- {rel3}\n"
                seen_relations.add(rel3)
            if ev_id:
                extracted_event_ids.append(f"news_{ev_id}")
    logs.append(
        f"Extracted {len(extracted_accessions)} SEC IDs and {len(extracted_event_ids)} Event IDs from graph."
    )
    logs.append("Executing Constrained Vector Search on 1-hop neighbors...")
    query_vector = embed_texts([query])[0]
    sec_hits = vector_db.search(
        "sec_chunks_v1",
        query_vector,
        top_k=settings.VECTOR_TOP_K,
        filter_ids=extracted_accessions,
    )
    news_hits = vector_db.search(
        "event_snippets_v1",
        query_vector,
        top_k=settings.VECTOR_TOP_K,
        filter_ids=extracted_event_ids,
    )
    logs.append(
        f"Retrieved {len(sec_hits)} filtered SEC chunks & {len(news_hits)} filtered news snippets from vector store."
    )
    context_str += "\n## SEC Filing Insight Chunks:\n"
    for hit in sec_hits:
        p = hit["payload"]
        context_str += f'- [{p["ticker"]} SEC {p["form_type"]} filing dated {p["filed_at"]}]: "{p["text"]}"\n'
    context_str += "\n## GDELT News Headlines:\n"
    for hit in news_hits:
        p = hit["payload"]
        context_str += f'- [{p["source"]} - {p["published_at"]}]: "{p["title"]}"\n'
    sector_exposures = {}
    for h in portfolio:
        ticker = h["ticker"].upper()
        weight = h["weight"]
        sector = SECTOR_MAP.get(ticker, "Information Technology")
        sector_exposures[sector] = sector_exposures.get(sector, 0.0) + weight
    exposure_str = ", ".join(
        [f"{s}: {int(w * 100)}%" for s, w in sector_exposures.items()]
    )
    system_prompt = (
        "You are an expert Wall Street equities research analyst and portfolio risk manager. "
        "Your task is to analyze SEC filings, GDELT news events, and active knowledge graph relationships "
        "to produce a premium, deeply-reasoned Portfolio Intelligence Report."
    )
    user_prompt = f"""
Analyze our US equities portfolio and answer the user question: "{query}"
Portfolio holdings:
{json.dumps(portfolio, indent=2)}
Computed Sector Exposures: {exposure_str}
Retrieved GraphRAG Context:
{context_str}
Produce a stunning, institutional-grade markdown report including:
1. **Executive Summary**: Synthesized threat, asset allocation, and macro opportunity assessment.
2. **Sector Allocation & Holding Distribution**: Explain the exposure distribution and core holdings.
3. **Strategic Risk & Geopolitical Analysis**: Focus on competitive dynamics, supply chains (e.g. TSMC packaging limits), and sovereign regulatory changes.
4. **SEC filings & News Timeline**: Order important filings and news events chronologically.
5. **Portfolio Recommendations**: Actionable tactical portfolio balancing actions based on findings.
Please ground your analysis strictly in the provided SEC and GDELT context.
"""
    insight = ""
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
                max_tokens=1000,
            )
            insight = resp.choices[0].message.content
            logs.append(
                "Successfully generated Portfolio Intelligence Report using OpenAI GPT."
            )
        except Exception as e:
            logs.append(f"OpenAI completion failed: {str(e)}.")
            insight = "Error generating report with OpenAI: " + str(e)
    if not insight:
        insight = "OpenAI API Key is missing or invalid. Please check your .env file."
    return {"insight": insight, "logs": logs}


workflow = StateGraph(AgentState)
workflow.add_node("prepare_portfolio", prepare_portfolio)
workflow.add_node("index_portfolio_structure", index_portfolio_structure)
workflow.add_node("synthesize", synthesize_portfolio_insight)
workflow.set_entry_point("prepare_portfolio")
workflow.add_edge("prepare_portfolio", "index_portfolio_structure")
workflow.add_edge("index_portfolio_structure", "synthesize")
workflow.add_edge("synthesize", END)
compiled_graph = workflow.compile()
