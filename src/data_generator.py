import os
import json
from datetime import datetime, timedelta


def generate_local_gdelt_data(output_dir: str = "data"):
    """
    Generates sample SEC filing chunks and GDELT news events for US equities.
    Saves them as JSON files in the data/ directory.
    """
    os.makedirs(output_dir, exist_ok=True)
    sec_filings = [
        {
            "ticker": "AAPL",
            "form_type": "10-K",
            "filed_at": "2026-02-18",
            "accession_no": "AAPL-10K-2026",
            "url": "https://www.sec.gov/Archives/edgar/data/320193/000032019326000008/a10-k.htm",
            "text": "Apple Inc. Form 10-K for the fiscal year ended December 27, 2025. Item 1A. Risk Factors. "
            "Our business, results of operations, and financial condition could be materially adversely affected by several factors. "
            "Global supply chain vulnerabilities, semiconductor supply constraints, and geopolitical friction in the Asia-Pacific "
            "region remain significant risks. Increased regulatory scrutiny on App Store pricing structures, anti-steering provisions, "
            "and antitrust actions in the EU and US pose structural headwinds. We are heavily investing in consumer-facing generative "
            "artificial intelligence, silicon optimization, and mixed-reality ecosystems. The success of our proprietary Apple Silicon "
            "chips (M-series and A-series) depends on foundry execution by TSMC. Any escalation in regional disputes in the Taiwan Strait "
            "could disrupt our ability to procure high-end chips.",
        },
        {
            "ticker": "MSFT",
            "form_type": "10-K",
            "filed_at": "2026-01-29",
            "accession_no": "MSFT-10K-2026",
            "url": "https://www.sec.gov/Archives/edgar/data/789019/000156459026000012/msft-10k.htm",
            "text": "Microsoft Corporation Form 10-K. Item 1. Business Section. "
            "Azure Cloud platform growth remains the primary engine of commercial Cloud segment performance. "
            "We continue to expand our cloud infrastructure footprint globally. We are integrating advanced GPT large language models "
            "and Azure OpenAI services across our commercial suites, Windows Copilot, and office application stack. "
            "Risk Factors: High capital expenditures are required to build and maintain next-generation data centers, GPU computing fleets, "
            "and network topology. Our strategic alliance with OpenAI is highly competitive and subjects us to technical and regulatory risk. "
            "We face intense competition from Google Cloud Platform (GCP) and Amazon Web Services (AWS) in hyperscale infrastructure. "
            "Energy grid reliability, carbon neutral commitments, and sovereign cloud data residency policies represent key compliance metrics.",
        },
        {
            "ticker": "NVDA",
            "form_type": "10-Q",
            "filed_at": "2026-03-12",
            "accession_no": "NVDA-10Q-Q3-2026",
            "url": "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000045/nvda-10q.htm",
            "text": "NVIDIA Corporation Form 10-Q for the Quarter ended January 25, 2026. Item 2. MD&A. "
            "Our Data Center revenue hit record highs, driven by hyperscaler adoption of Hopper H200 and Blackwell B200 architectures. "
            "GPU demand continues to far outpace industry supply capability, and lead times remain extended. "
            "We are expanding our networking suite, including InfiniBand and Spectrum-X Ethernet systems, to alleviate compute bottlenecks. "
            "Supply Chain & Operations: We rely on single-source manufacturing partners, specifically TSMC for advanced silicon packaging "
            "(CoWoS) and ASML for EUV lithography tooling. Regulatory limits: Stringent export control guidelines imposed by the US "
            "Department of Commerce restrict delivery of high-bandwidth AI hardware to sovereign entities in China and parts of the Middle East, "
            "which could impact future growth trajectories.",
        },
        {
            "ticker": "TSLA",
            "form_type": "10-K",
            "filed_at": "2026-02-05",
            "accession_no": "TSLA-10K-2026",
            "url": "https://www.sec.gov/Archives/edgar/data/1318605/000162828026000344/tsla-10k.htm",
            "text": "Tesla, Inc. Form 10-K. Item 1A. Operational Risk Factors. "
            "Automotive margins experienced volatility due to global price matching adjustments, shifting consumer EV incentives in Europe, "
            "and factory retooling downtimes. We are accelerating deployment of the Next-Generation vehicle platform, Full Self-Driving (FSD) "
            "Supervised neural networks, and Optimus humanoid robotics. Supply chain dynamics: Lithium-ion battery pack manufacturing and raw "
            "material refinement (Lithium, Nickel, Cobalt) are sensitive to localized geopolitical changes and export quotas. "
            "Our Gigafactory Shanghai production facility represents our highest capacity center, exposing our operations to US-China trade tariffs "
            "and supply chain localization rules under the US Inflation Reduction Act (IRA).",
        },
        {
            "ticker": "AMZN",
            "form_type": "10-K",
            "filed_at": "2026-02-10",
            "accession_no": "AMZN-10K-2026",
            "url": "https://www.sec.gov/Archives/edgar/data/1018724/000101872426000015/amzn-10k.htm",
            "text": "Amazon.com, Inc. Form 10-K. MD&A Section. "
            "Amazon Web Services (AWS) net sales increased, driven by extensive migrations, enterprise AI integrations, and the roll-out of "
            "AWS Trainium and Inferentia proprietary AI chips. Retail Operations: Shipping costs, labor relations, and warehouse automated "
            "sorting deployments represent major cost leverage components. We are actively incorporating robotics to enhance delivery efficiency. "
            "Risk Factors: Rapid technological changes in generative AI models require persistent capital allocation. "
            "We are subject to complex antitrust reviews by the FTC regarding Prime bundled services, merchant agreements, and logistics policies. "
            "Any adverse regulatory outcomes could force business model structural adjustments.",
        },
        {
            "ticker": "GOOG",
            "form_type": "10-K",
            "filed_at": "2026-02-01",
            "accession_no": "GOOG-10K-2026",
            "url": "https://www.sec.gov/Archives/edgar/data/1652044/000165204426000018/goog-10k.htm",
            "text": "Alphabet Inc. Form 10-K. Our Search revenue continues to grow, although we are actively investing heavily in Google DeepMind and our Gemini AI infrastructure. Data privacy regulations in the EU (GDPR) and the ongoing DOJ antitrust lawsuit regarding our Search monopoly represent material risks to our core business model. We depend on highly optimized custom Tensor Processing Units (TPUs) for our compute workloads, reducing our dependency on external GPU suppliers but exposing us to specialized manufacturing constraints.",
        },
    ]
    start_date = datetime.now() - timedelta(days=10)
    gdelt_news = [
        {
            "event_id": "EV_NEWS_001",
            "title": "US Imposes Additional Export Restraints on Advanced Semiconductor Tooling Targeting Semiconductor Hubs",
            "source": "Bloomberg",
            "url": "https://www.bloomberg.com/news/articles/2026-05-22/us-chips-rules-semiconductors",
            "published_at": (start_date + timedelta(days=1)).strftime("%Y-%m-%d"),
            "tickers": ["NVDA", "AAPL", "MSFT"],
        },
        {
            "event_id": "EV_NEWS_002",
            "title": "EU Commission Approves Landmark AI Act Compliance Audit, Pushing Sovereign Audits for Major Hyperscalers",
            "source": "Reuters",
            "url": "https://www.reuters.com/technology/eu-ai-act-compliance-audits-2026-05-24/",
            "published_at": (start_date + timedelta(days=3)).strftime("%Y-%m-%d"),
            "tickers": ["MSFT", "GOOG", "AMZN"],
        },
        {
            "event_id": "EV_NEWS_003",
            "title": "Apple Unveils Generative AI Operating System Integrations at WWDC 26, Sparking Supplier Upgrades",
            "source": "CNBC",
            "url": "https://www.cnbc.com/2026/05/25/apple-wwdc-26-ai-partnership-chips.html",
            "published_at": (start_date + timedelta(days=4)).strftime("%Y-%m-%d"),
            "tickers": ["AAPL", "NVDA"],
        },
        {
            "event_id": "EV_NEWS_004",
            "title": "US Tariff Proposals on EV Battery Inputs Create Supply Shocks for Gigafactory Logistics Teams",
            "source": "Financial Times",
            "url": "https://www.ft.com/content/us-tariffs-ev-battery-supply-tesla-2026-05-26",
            "published_at": (start_date + timedelta(days=5)).strftime("%Y-%m-%d"),
            "tickers": ["TSLA"],
        },
        {
            "event_id": "EV_NEWS_005",
            "title": "AWS Announces Multi-Billion Dollar Sovereign Cloud Facility Expansion in Frankfurt to Tackle Data Residency",
            "source": "Wall Street Journal",
            "url": "https://www.wsj.com/articles/amazon-aws-frankfurt-sovereign-cloud-2026-05-27",
            "published_at": (start_date + timedelta(days=6)).strftime("%Y-%m-%d"),
            "tickers": ["AMZN", "MSFT"],
        },
        {
            "event_id": "EV_NEWS_006",
            "title": "NVIDIA and TSMC Jointly Address CoWoS Chip Packaging Scaling Constraints at Global Semiconductor Summit",
            "source": "Reuters",
            "url": "https://www.reuters.com/technology/nvidia-tsmc-cowos-packaging-capacity-upgrade-2026-05-28/",
            "published_at": (start_date + timedelta(days=7)).strftime("%Y-%m-%d"),
            "tickers": ["NVDA", "AAPL"],
        },
        {
            "event_id": "EV_NEWS_007",
            "title": "Federal Trade Commission Extends Antitrust Review on Hyperscaler AI Strategic Partnerships and Investment Rules",
            "source": "Bloomberg",
            "url": "https://www.bloomberg.com/news/ftc-hyperscale-ai-antitrust-probe-2026-05-29",
            "published_at": (start_date + timedelta(days=8)).strftime("%Y-%m-%d"),
            "tickers": ["MSFT", "AMZN", "GOOG"],
        },
        {
            "event_id": "EV_NEWS_008",
            "title": "Google DeepMind Announces Breakthrough in Quantum Error Correction Algorithms, Accelerating Next-Gen AI Compute",
            "source": "TechCrunch",
            "url": "https://techcrunch.com/2026/05/30/google-deepmind-quantum-error-correction-ai",
            "published_at": (start_date + timedelta(days=9)).strftime("%Y-%m-%d"),
            "tickers": ["GOOG", "MSFT"],
        },
    ]
    sec_path = os.path.join(output_dir, "sec_filings.json")
    with open(sec_path, "w", encoding="utf-8") as f:
        json.dump(sec_filings, f, indent=4)
    print(f"Generated mock SEC filings at: {sec_path}")
    news_path = os.path.join(output_dir, "gdelt_events.json")
    with open(news_path, "w", encoding="utf-8") as f:
        json.dump(gdelt_news, f, indent=4)
    print(f"Generated mock GDELT news events at: {news_path}")


if __name__ == "__main__":
    base_data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    generate_local_gdelt_data(base_data_dir)
