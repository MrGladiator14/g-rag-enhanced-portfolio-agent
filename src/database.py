from typing import Dict, List, Any, Optional
from neo4j import GraphDatabase, Driver
from .config import settings
from .logger import get_logger

logger = get_logger("database")


class Neo4jConnector:
    """
    Handles connectivity and queries for Neo4j.
    """

    def __init__(self) -> None:
        self.driver: Optional[Driver] = None
        try:
            self.driver = GraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD),
            )
            self.driver.verify_connectivity()
            logger.info(
                "Successfully connected to Neo4j", extra={"uri": settings.NEO4J_URI}
            )
        except Exception as exc:
            logger.error(
                "Could not connect to Neo4j. Check if it is running.",
                extra={"error": str(exc), "uri": settings.NEO4J_URI},
            )
            raise exc

    def close(self) -> None:
        if self.driver:
            self.driver.close()

    def reset_db(self) -> None:
        """Clears all nodes and relationships."""
        if self.driver:
            try:
                with self.driver.session() as session:
                    session.run("MATCH (n) DETACH DELETE n")
                logger.info("Neo4j database successfully reset.")
            except Exception as e:
                logger.error("Failed to reset Neo4j database", extra={"error": str(e)})

    def add_portfolio(self, session_id: str, holdings: List[Dict[str, Any]]) -> None:
        """
        Creates Portfolio node, Holding nodes, and maps them to Company nodes.
        holdings is a list of dicts like: [{"ticker": "AAPL", "weight": 0.4}, ...]
        """
        if self.driver:
            cypher = """
            MERGE (p:Portfolio {session_id: $session_id})
            WITH p
            OPTIONAL MATCH (p)-[r:HAS_HOLDING]->(h:Holding)
            DETACH DELETE h
            WITH p
            UNWIND $holdings AS h_data
            MERGE (c:Company {ticker: h_data.ticker})
            SET c.name = h_data.ticker + " Inc."
            CREATE (h:Holding {holding_id: $session_id + "_" + h_data.ticker, ticker: h_data.ticker, weight: h_data.weight})
            CREATE (p)-[:HAS_HOLDING]->(h)
            CREATE (h)-[:OF_COMPANY]->(c)
            """
            try:
                with self.driver.session() as session:
                    session.run(
                        cypher, {"session_id": session_id, "holdings": holdings}
                    )
                logger.info(
                    "Indexed Portfolio and Holdings in Neo4j",
                    extra={"session_id": session_id},
                )
            except Exception as e:
                logger.error(
                    "Failed to write Portfolio to Neo4j.", extra={"error": str(e)}
                )

    def add_sec_filing(
        self, ticker: str, form_type: str, date: str, accession_no: str, url: str
    ) -> None:
        """
        Creates Filing node and establishes relationship (Company)-[:FILED]->(Filing).
        """
        ticker = ticker.upper()
        if self.driver:
            cypher = """
            MERGE (c:Company {ticker: $ticker})
            MERGE (f:Filing {accession_no: $accession_no})
            SET f.form_type = $form_type, f.filed_at = $date, f.url = $url
            MERGE (c)-[:FILED]->(f)
            """
            try:
                with self.driver.session() as session:
                    session.run(
                        cypher,
                        {
                            "ticker": ticker,
                            "form_type": form_type,
                            "date": date,
                            "accession_no": accession_no,
                            "url": url,
                        },
                    )
                logger.info(
                    "Indexed SEC filing in Neo4j",
                    extra={"ticker": ticker, "accession_no": accession_no},
                )
            except Exception as e:
                logger.error(
                    "Failed to write Filing to Neo4j.", extra={"error": str(e)}
                )

    def add_company_sector(self, ticker: str, sector: str) -> None:
        """
        Creates Sector node and establishes relationship (Company)-[:IN_SECTOR]->(Sector).
        """
        ticker = ticker.upper()
        if self.driver:
            cypher = """
            MERGE (c:Company {ticker: $ticker})
            MERGE (s:Sector {name: $sector})
            MERGE (c)-[:IN_SECTOR]->(s)
            """
            try:
                with self.driver.session() as session:
                    session.run(cypher, {"ticker": ticker, "sector": sector})
                logger.info(
                    "Indexed Company Sector in Neo4j",
                    extra={"ticker": ticker, "sector": sector},
                )
            except Exception as e:
                logger.error(
                    "Failed to write Sector to Neo4j.", extra={"error": str(e)}
                )

    def add_peers(self, ticker: str, peers: List[str]) -> None:
        """
        Establishes relationships between Company nodes representing peers.
        """
        ticker = ticker.upper()
        if self.driver:
            cypher = """
            MERGE (c1:Company {ticker: $ticker})
            WITH c1
            UNWIND $peers AS peer_ticker
            MERGE (c2:Company {ticker: peer_ticker})
            MERGE (c1)-[:PEER_OF]->(c2)
            """
            try:
                with self.driver.session() as session:
                    session.run(cypher, {"ticker": ticker, "peers": peers})
                logger.info(
                    "Indexed Peers in Neo4j",
                    extra={"ticker": ticker, "peers_count": len(peers)},
                )
            except Exception as e:
                logger.error("Failed to write Peers to Neo4j.", extra={"error": str(e)})

    def add_gdelt_event(
        self,
        event_id: str,
        title: str,
        source: str,
        url: str,
        date: str,
        tickers: List[str],
    ) -> None:
        """
        Creates Event node and links Event -[:MENTIONS]-> Company for each mentioned ticker.
        """
        if self.driver:
            cypher = """
            MERGE (e:Event {event_id: $event_id})
            SET e.title = $title, e.source = $source, e.url = $url, e.published_at = $date
            WITH e
            UNWIND $tickers AS t
            MERGE (c:Company {ticker: t})
            MERGE (e)-[:MENTIONS]->(c)
            """
            try:
                with self.driver.session() as session:
                    session.run(
                        cypher,
                        {
                            "event_id": event_id,
                            "title": title,
                            "source": source,
                            "url": url,
                            "date": date,
                            "tickers": [t.upper() for t in tickers],
                        },
                    )
                logger.info(
                    "Indexed GDELT Equities Event in Neo4j",
                    extra={"event_id": event_id},
                )
            except Exception as e:
                logger.error("Failed to write Event to Neo4j.", extra={"error": str(e)})

    def query_subgraph(self, search_term: str) -> List[Dict[str, Any]]:
        """
        Retrieves context around search term. Searches for matching Companies,
        Sectors, or Events and returns aggregated neighborhood.
        """
        results = []
        term_upper = search_term.upper()
        if self.driver:
            cypher = """
            MATCH (c:Company)
            WHERE c.ticker CONTAINS $term OR c.name CONTAINS $term
            OPTIONAL MATCH (c)-[:IN_SECTOR]->(s:Sector)
            OPTIONAL MATCH (c)-[:FILED]->(f:Filing)
            OPTIONAL MATCH (e:Event)-[:MENTIONS]->(c)
            RETURN c.ticker AS ticker, s.name AS sector, f.form_type AS filing_form, 
                   f.filed_at AS filing_date, e.title AS event_title, e.published_at AS event_date,
                   f.accession_no AS accession_no, e.event_id AS event_id
            LIMIT 50
            """
            try:
                with self.driver.session() as session:
                    result = session.run(cypher, {"term": term_upper})
                    results = [record.data() for record in result]
                return results
            except Exception as e:
                logger.error("Failed to query Neo4j.", extra={"error": str(e)})
        return []

    def get_graph_visual(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Formats full graph for frontend D3/Vis.js visualization.
        """
        if self.driver:
            nodes_cypher = """
            MATCH (n)
            RETURN id(n) AS neo_id, labels(n)[0] AS label, n.ticker AS ticker, 
                   n.name AS name, n.session_id AS session_id, n.weight AS weight, 
                   n.title AS title, n.published_at AS event_date, n.form_type AS form_type, 
                   n.filed_at AS filing_date, n.accession_no AS accession_no, n.event_id AS event_id
            """
            edges_cypher = """
            MATCH (n)-[r]->(m)
            RETURN id(n) AS source_id, id(m) AS target_id, type(r) AS type
            """
            try:
                with self.driver.session() as session:
                    n_records = session.run(nodes_cypher)
                    nodes = []
                    id_map = {}
                    for r in n_records:
                        n_data = r.data()
                        node_id = str(n_data["neo_id"])
                        id_map[n_data["neo_id"]] = node_id
                        label = n_data["label"]
                        title = ""
                        subtitle = ""
                        if label == "Portfolio":
                            title = f"Portfolio: {n_data['session_id']}"
                        elif label == "Holding":
                            title = f"Holding: {n_data['ticker']} ({int(n_data['weight'] * 100)}%)"
                            subtitle = f"Weight: {n_data['weight']}"
                        elif label == "Company":
                            title = n_data["ticker"]
                            subtitle = n_data["name"] or ""
                        elif label == "Sector":
                            title = n_data["name"]
                        elif label == "Filing":
                            title = f"Filing: {n_data['form_type']}"
                            subtitle = n_data["filing_date"] or ""
                        elif label == "Event":
                            title = n_data["title"] or f"Event {n_data['event_id']}"
                            subtitle = n_data["event_date"] or ""
                        nodes.append(
                            {
                                "id": node_id,
                                "label": label,
                                "title": title,
                                "subtitle": subtitle,
                            }
                        )
                    e_records = session.run(edges_cypher)
                    edges = []
                    for r in e_records:
                        e_data = r.data()
                        edges.append(
                            {
                                "source": id_map.get(e_data["source_id"]),
                                "target": id_map.get(e_data["target_id"]),
                                "type": e_data["type"],
                            }
                        )
                return {"nodes": nodes, "edges": edges}
            except Exception as e:
                logger.error(
                    "Failed to fetch Neo4j graph visuals.", extra={"error": str(e)}
                )
        return {"nodes": [], "edges": []}


db = Neo4jConnector()
