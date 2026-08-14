"""Protocol YAML normalization: the invalid-YAML repair, the structured versus
unstructured split, and the fallback concept mining."""
import os

from protocol_sorter import classify_criterion, fix_and_load_yaml, normalize_protocol


def test_classify_value_bearing_criteria_as_structured():
    assert classify_criterion({"value": 8.0}) == "structured"
    assert classify_criterion({"metric": "FEV1_percent", "value": [50, 80]}) == "structured"


def test_classify_typed_criteria():
    assert classify_criterion({"type": "age"}) == "structured"
    assert classify_criterion({"type": "lab_test"}) == "structured"
    assert classify_criterion({"type": "medical_history"}) == "unstructured"
    assert classify_criterion({"concepts": ["cancer"]}) == "unstructured"


def test_unknown_type_defaults_to_unstructured():
    assert classify_criterion({"type": "motivational_assessment"}) == "unstructured"


def test_fix_and_load_yaml_wraps_dangling_list(tmp_path):
    p = tmp_path / "proto.yaml"
    p.write_text(
        'protocol_id: T-1\nstudy_name: "T"\n\n'
        '  - description: "c1"\n    type: "age"\n    condition: "between"\n'
        '    value: [50, 70]\n',
        encoding="utf-8")
    raw = fix_and_load_yaml(str(p))
    assert raw["protocol_id"] == "T-1"
    assert isinstance(raw["criteria"], list) and len(raw["criteria"]) == 1


def test_normalize_splits_and_mines_fallback_concepts():
    raw = {
        "protocol_id": "T-1",
        "criteria": [
            {"description": "age gate", "type": "age", "condition": "between",
             "value": [50, 70]},
            {"description": "Occupational or environmental smoke exposure history.",
             "type": "exposure_history", "condition": "documented_exposure"},
        ],
    }
    clean = normalize_protocol(raw, "T-1")
    assert len(clean["structured_criteria"]) == 1
    assert len(clean["unstructured_criteria"]) == 1
    mined = clean["unstructured_criteria"][0]["concepts"]
    assert mined == ["occupational", "environmental", "smoke", "exposure", "history."]


def test_both_shipped_protocols_normalize(data_dir):
    from protocol_sorter import sort_protocols
    protos = {p["protocol_id"]: p for p in sort_protocols(data_dir)}
    assert set(protos) == {"ONC-003-Prevention", "RESP-005-Cessation"}
    onc = protos["ONC-003-Prevention"]
    resp = protos["RESP-005-Cessation"]
    assert len(onc["structured_criteria"]) + len(onc["unstructured_criteria"]) == 9
    assert len(resp["structured_criteria"]) + len(resp["unstructured_criteria"]) == 13
