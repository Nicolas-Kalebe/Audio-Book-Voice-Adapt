from audiobook_voice_enhancer.book_speakers import build_book, review_book
from audiobook_voice_enhancer.cache import Cache
from audiobook_voice_enhancer.llm import LLMProvider


class CatalogProvider(LLMProvider):
    model = "catalog-fixture"

    def __init__(self):
        self.schemas = []
        self.prompts = []

    def infer(self, payload):
        self.schemas.append(self.response_schema)
        self.prompts.append(self.system_prompt)
        turn = payload["turns"][0]
        return {
            "entities": [{"id": "N0", "kind": "named", "mention": "Unist", "paragraph": 0}],
            "assignments": [{"id": turn["id"], "speaker": "N0", "kind": "speech", "confidence": .96}],
        }


def test_hybrid_catalog_enforces_ids_and_accepts_a_missing_speaker(tmp_path):
    provider = CatalogProvider()
    model = build_book(["— Unist, responda."])

    result = review_book(model, provider, Cache(tmp_path), protocol="hybrid-catalog",
                         turn_consistency=False)

    schema = provider.schemas[0]
    entity_id = schema["properties"]["entities"]["items"]["properties"]["id"]
    assignment = schema["properties"]["assignments"]
    speaker_choices = assignment["items"]["properties"]["speaker"]["anyOf"]
    assert entity_id["pattern"] == r"^N[0-9]+$"
    assert assignment["minItems"] == assignment["maxItems"] == 1
    assert assignment["items"]["properties"]["id"]["enum"] == ["T0"]
    assert {choice.get("pattern") for choice in speaker_choices} >= {r"^N[0-9]+$"}
    assert "SOMENTE pessoas ausentes" in provider.prompts[0]
    assert result["attribution_protocol"] == "hybrid-catalog-v1"
    turn = result["turns"][0]
    assert turn["status"] == "contextual"
    assert result["entities"][turn["speaker_entity_id"]]["name"] == "Unist"
    assert result["review"]["accepted_named_entities"] == 1
    assert result["review"]["created_entity_proposals"] == 1


def test_hybrid_catalog_schema_allows_only_existing_e_ids(tmp_path):
    class ExistingProvider(LLMProvider):
        model = "existing-fixture"

        def __init__(self):
            self.schemas = []

        def infer(self, payload):
            self.schemas.append(self.response_schema)
            return {"entities": [], "assignments": [{
                "id": payload["turns"][0]["id"], "speaker": payload["entities"][0]["id"],
                "kind": "speech", "confidence": .99,
            }]}

    provider = ExistingProvider()
    result = review_book(build_book(["— Sim — disse Iara."]), provider, Cache(tmp_path),
                         protocol="hybrid-catalog")
    choices = provider.schemas[0]["properties"]["assignments"]["items"]["properties"]["speaker"]["anyOf"]
    assert choices[0]["enum"] == ["E0"]
    assert result["turns"][0]["status"] == "explicit"
