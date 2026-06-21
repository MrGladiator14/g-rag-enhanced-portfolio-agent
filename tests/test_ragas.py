import os
import json
import pytest
import sys
import types

# Mock to bypass Ragas ImportError
module_name = 'langchain_community.chat_models.vertexai'
mock_module = types.ModuleType(module_name)
mock_module.ChatVertexAI = type('ChatVertexAI', (object,), {})
sys.modules[module_name] = mock_module

from datasets import Dataset

from ragas import evaluate
from ragas.metrics import (
    context_precision,
    context_recall,
    faithfulness,
    answer_relevancy,
    answer_correctness,
)
import pandas as pd
from src.agent import compiled_graph

# Test dataset based on data/ folder
TEST_CASES = [
    {
        "question": "What are the key supply chain risks for Apple (AAPL) according to its latest SEC filings?",
        "ground_truth": "Apple's key supply chain risks include global supply chain vulnerabilities, semiconductor supply constraints, and geopolitical friction in the Asia-Pacific region. They are highly dependent on TSMC for their proprietary Apple Silicon chips, meaning any escalation in regional disputes in the Taiwan Strait could disrupt their ability to procure high-end chips."
    },
    {
        "question": "What is NVIDIA's (NVDA) strategy to alleviate compute bottlenecks?",
        "ground_truth": "NVIDIA is expanding its networking suite, which includes InfiniBand and Spectrum-X Ethernet systems, to alleviate compute bottlenecks caused by GPU demand outpacing industry supply capability."
    },
    {
        "question": "How are new US export curbs impacting AI hardware companies like NVIDIA (NVDA) and Apple (AAPL)?",
        "ground_truth": "Stringent export control guidelines imposed by the US Department of Commerce restrict the delivery of high-bandwidth AI hardware to sovereign entities in China and parts of the Middle East, potentially impacting future growth trajectories. The Trump administration has also signaled broader curbs on high-end AI chips bound for Chinese data centers."
    },
    {
        "question": "Why are Amazon (AMZN) Web Services (AWS) net sales increasing?",
        "ground_truth": "Amazon Web Services (AWS) net sales are increasing driven by extensive migrations, enterprise AI integrations, and the roll-out of proprietary AI chips like AWS Trainium and Inferentia."
    },
    {
        "question": "How will the EU AI Act compliance audit impact hyperscalers like Microsoft (MSFT), Google (GOOG), and Amazon (AMZN)?",
        "ground_truth": "The EU Commission approved a landmark AI Act Compliance Audit that pushes for sovereign audits for major hyperscalers like Microsoft, Google, and Amazon, representing a significant regulatory step that impacts how these companies operate their cloud and AI services in Europe."
    }
]

@pytest.fixture(scope="module")
def setup_environment():
    # Ensure OPENAI_API_KEY is set
    assert "OPENAI_API_KEY" in os.environ, "OPENAI_API_KEY environment variable is required."
    
def test_ragas_evaluation(setup_environment):
    # Initialize lists for datasets
    questions = []
    answers = []
    contexts = []
    ground_truths = []

    # Run queries through the LangGraph agent
    for case in TEST_CASES:
        initial_state = {
            "query": case["question"],
            "portfolio": [],  # Agent defaults to AAPL, NVDA, AMZN
            "session_id": "test_session",
            "sec_filings": [],
            "gdelt_events": [],
            "indexed_count": 0,
            "neo4j_context": [],
            "vector_context": [],
            "insight": "",
            "logs": [],
        }
        
        final_state = compiled_graph.invoke(initial_state)
        
        insight = final_state.get("insight", "")
        # The contexts are stored as dictionaries {"text": ...} in vector_context
        v_contexts = final_state.get("vector_context", [])
        context_list = [c["text"] for c in v_contexts] if v_contexts else ["No context retrieved."]
        
        questions.append(case["question"])
        answers.append(insight)
        contexts.append(context_list)
        ground_truths.append(case["ground_truth"])

    # Create the dataset for RAGAS
    data = {
        "question": questions,
        "answer": answers,
        "contexts": contexts,
        "ground_truth": ground_truths
    }
    dataset = Dataset.from_dict(data)

    # Evaluate using the 5 metrics
    result = evaluate(
        dataset,
        metrics=[
            context_precision,
            context_recall,
            faithfulness,
            answer_relevancy,
            answer_correctness,
        ]
    )
    
    # Save results to a markdown table
    df = result.to_pandas()
    # Filter the columns to keep just the metrics for the markdown table
    metrics_cols = ["question", "context_precision", "context_recall", "faithfulness", "answer_relevancy", "answer_correctness"]
    df_metrics = df[[c for c in metrics_cols if c in df.columns]]
    
    markdown_table = df_metrics.to_markdown(index=False)
    
    output_path = os.path.join(os.path.dirname(__file__), "evaluation_results.md")
    with open(output_path, "w") as f:
        f.write("# RAGAS Evaluation Results\n\n")
        f.write(markdown_table)
        f.write("\n\n## Aggregate Scores\n\n")
        f.write(pd.DataFrame([result]).to_markdown(index=False))
        
    assert os.path.exists(output_path)
    print(f"Results saved to {output_path}")
