"""Text-first dialogue candidates; missing audio must not erase the denominator.

These are parser candidates, not a human gold standard. Quotes may be thoughts or
citations, and a matched candidate does not prove correct timing or attribution.
"""
from __future__ import annotations

from typing import Any

from .dialogue import QUOTE, TextMatch, _continued_dash_turn, _dash_speech_fragments


def dialogue_inventory(blocks: list[str]) -> list[dict[str, Any]]:
    inventory = []
    for paragraph, text in enumerate(blocks):
        continuation = _continued_dash_turn(blocks, paragraph)
        matches = _dash_speech_fragments(text)
        style = "dash"
        if continuation is not None:
            matches = [TextMatch(text.strip(), len(text) - len(text.lstrip()), len(text.rstrip()), style="dash")]
        if not matches:
            matches = list(QUOTE.finditer(text))
            style = "quote"
        for index, match in enumerate(matches):
            inventory.append({
                "candidate_id": f"{paragraph}-{index}", "paragraph": paragraph,
                "turn_id": f"book-{continuation if continuation is not None else paragraph}"
                if style == "dash" else f"book-{paragraph}-{index}",
                "style": style, "text": match.group(1),
                "char_start": match.start(1), "char_end": match.end(1),
                "requires_speech_validation": style == "quote",
            })
    return inventory


def audio_coverage(inventory: list[dict[str, Any]], alignments: list[dict[str, Any]],
                   dialogues: list[dict[str, Any]]) -> dict[str, Any]:
    anchors = [int(item["book_paragraph_id"]) for item in alignments
               if float(item.get("alignment_confidence", 0)) >= .5]
    scope = [min(anchors), max(anchors)] if anchors else None
    scoped = [item for item in inventory if scope and scope[0] <= item["paragraph"] <= scope[1]]
    located = {str(item["id"]): item for item in dialogues if item.get("source") == "book"}
    candidates = []
    for item in scoped:
        match = located.get(item["candidate_id"])
        candidates.append({**item, "audio_status": "located" if match else "not_detected",
                           "dialogue_id": match["id"] if match else None})
    count = sum(item["audio_status"] == "located" for item in candidates)
    return {
        "scope": "aligned_paragraph_envelope" if scope else "unknown",
        "paragraph_range": scope, "book_candidates_total": len(inventory),
        "candidates_in_scope": len(candidates), "candidates_located": count,
        "candidates_not_detected": len(candidates) - count,
        "candidate_location_rate": round(count / len(candidates), 4) if candidates else None,
        "caveat": ("Cobertura de candidatos do parser, não acurácia. Aspas podem ser pensamentos. "
                   "O intervalo depende do alinhamento; início e fim fora dele não são avaliados. "
                   "Localizado não garante falante nem limites de áudio corretos."),
        "candidates": candidates,
    }
