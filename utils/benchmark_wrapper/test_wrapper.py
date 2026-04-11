from utils.benchmark_wrapper import to_serializable_dict, wrap_agent_for_benchmark


def fake_agent(question: str, available_databases=None, schema_info=None):
    return {
        "answer": f"Handled: {question}",
        "query_trace": [{"step": "plan"}],
        "confidence": 0.9,
        "assumptions": ["test assumption"],
        "data_sources_used": ["postgresql"],
        "transformations_applied": ["none"],
    }


def test_wrap_agent_for_benchmark() -> None:
    response = wrap_agent_for_benchmark(
        agent_callable=fake_agent,
        question="Test question",
        available_databases=["postgresql"],
        schema_info={"tables": ["customers"]},
    )

    assert response.answer == "Handled: Test question"
    assert response.confidence == 0.9
    assert response.data_sources_used == ["postgresql"]


def test_to_serializable_dict() -> None:
    response = wrap_agent_for_benchmark(agent_callable=fake_agent, question="Q")
    payload = to_serializable_dict(response)

    assert payload["answer"] == "Handled: Q"
    assert payload["query_trace"] == [{"step": "plan"}]
