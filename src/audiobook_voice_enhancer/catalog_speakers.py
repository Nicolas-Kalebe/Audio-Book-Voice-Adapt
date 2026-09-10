"""Strict catalog contract for the compact/hybrid attribution pass.

The base prompt has always described ``E`` as existing entities and ``N`` as
new entities, but its schema accepted arbitrary strings in both places.  A
constrained decoder could therefore echo catalog entries inside ``entities``
and confidently assign a newcomer to one of them.  This module turns that
natural-language convention into a machine-checkable, per-window schema.
"""
from __future__ import annotations

import copy

VERSION = "hybrid-catalog-v1"

SYSTEM_SUFFIX = """
Contrato estrito do catálogo:
- entities contém SOMENTE pessoas ausentes do catálogo E e usa IDs N0, N1...;
  nunca repita uma entidade E nessa lista.
- Se o falante não está no catálogo, proponha-o em entities e use o mesmo ID N
  na assignment. Não escolha uma pessoa conhecida só porque ela é a opção disponível.
- Uma pessoa meramente mencionada pode estar ausente. Crie/atribua somente quando
  a sequência, o sujeito narrativo, uma resposta a vocativo ou outra evidência do
  trecho sustentar que ela participa e fala.
- Um personagem dizer o próprio nome costuma ser evidência contrária à atribuição,
  exceto quando o texto realmente indica autoapresentação ou autorreferência.
Na dúvida entre inventar um vínculo e deixar sem falante, use null."""


def response_schema(base: dict, payload: dict) -> dict:
    """Return an exact-ID schema for one compact window.

    Semantic correctness still belongs to the model and runtime validator.  The
    schema only makes impossible the malformed E-as-new response observed in P4.
    """
    schema = copy.deepcopy(base)
    entity_item = schema["properties"]["entities"]["items"]
    entity_item["properties"]["id"] = {"type": "string", "pattern": r"^N[0-9]+$"}

    assignment_array = schema["properties"]["assignments"]
    assignment_array["minItems"] = len(payload["turns"])
    assignment_array["maxItems"] = len(payload["turns"])
    assignment = assignment_array["items"]["properties"]
    assignment["id"] = {"type": "string", "enum": [turn["id"] for turn in payload["turns"]]}
    existing = [entity["id"] for entity in payload["entities"]]
    choices = [{"type": "null"}, {"type": "string", "pattern": r"^N[0-9]+$"}]
    if existing:
        choices.insert(0, {"type": "string", "enum": existing})
    assignment["speaker"] = {"anyOf": choices}
    return schema
