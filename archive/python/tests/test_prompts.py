from apidiom.llm.prompts import EXTRACTION_RESPONSE_SCHEMA


def test_extraction_schema_constrains_envelope_not_inner_properties() -> None:
    assert EXTRACTION_RESPONSE_SCHEMA["type"] == "object"
    paths_schema = EXTRACTION_RESPONSE_SCHEMA["properties"]["paths"]
    assert paths_schema == {"type": "object"}  # open — no inner shape forced
    components_schema = EXTRACTION_RESPONSE_SCHEMA["properties"]["components"]
    assert components_schema == {"type": "object"}
