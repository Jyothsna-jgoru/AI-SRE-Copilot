from simulator.generator import SCENARIOS, build_dataset


def test_dataset_has_required_scale_and_coverage():
    data = build_dataset()
    assert len(data["services"]) == 5
    assert len(data["incidents"]) == 50
    assert len(data["logs"]) >= 1000
    assert len(data["knowledge_documents"]) >= 15
    assert {item["scenario"] for item in data["incidents"]} == set(SCENARIOS)


def test_ground_truth_is_not_embedded_in_observable_incidents():
    data = build_dataset()
    forbidden = {"expected_root_cause", "expected_root_cause_category", "required_evidence_ids"}
    for incident in data["incidents"]:
        assert forbidden.isdisjoint(incident)
    assert len(data["evaluation_cases"]) == len(data["incidents"])


def test_dataset_is_deterministic():
    first = build_dataset(seed=7)
    second = build_dataset(seed=7)
    assert first["incidents"] == second["incidents"]
    assert first["logs"] == second["logs"]

