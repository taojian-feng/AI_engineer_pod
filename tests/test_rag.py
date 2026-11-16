from app import llm
from app.evals import rag_eval
from app.rag.pipeline import AGENT_RAG, RagConfig, answer, retrieve


def test_baseline_retrieval_is_weaker_than_tuned():
    def hit_rate(cfg):
        cases = [c for c in rag_eval.DATASET if c["answerable"]]
        return sum(bool({h["source"] for h in retrieve(c["question"], cfg)} & set(c["sources"])) for c in cases) / len(cases)

    base, tuned = hit_rate(RagConfig()), hit_rate(AGENT_RAG)
    assert tuned >= 0.9
    assert tuned >= base


def test_answer_uses_context_and_cites():
    r = answer("What is the hotel cap in San Francisco?", AGENT_RAG)
    assert r["contexts"] and "[1]" in r["answer"]


def test_eval_metrics_shape():
    llm.fake_script(*[llm.text_reply("The documents don't specify this.") for _ in range(3)])
    res = rag_eval.run(AGENT_RAG, use_judge=False, case_ids=["u1", "u2", "u3"])
    assert res["metrics"]["abstention_on_unanswerable"] == 1.0
    assert res["metrics"]["hallucination_rate"] == 0.0


def test_correctness_check():
    assert rag_eval._correct("You need Category Manager approval.", [["category manager"]])
    assert not rag_eval._correct("Director approval", [["category manager"]])
    assert rag_eval._correct("Up to $500 or 2%", [["2%"], ["$500", "500"]])
