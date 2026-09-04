from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


OVERRIDE_VERSION = 1


def _key(source: Path | str, dialogue_id: str) -> str:
    return f"{Path(source).name.casefold()}|{dialogue_id}"


def load_overrides(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"version": OVERRIDE_VERSION, "exact": {}, "rules": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"version": OVERRIDE_VERSION, "exact": dict(data.get("exact", {})),
            "rules": list(data.get("rules", []))}


def apply_overrides(source: Path, dialogues: list[dict[str, Any]], path: Path) -> int:
    data = load_overrides(path)
    applied = 0
    for item in dialogues:
        speaker = data["exact"].get(_key(source, str(item["id"])))
        if not speaker:
            for rule in data["rules"]:
                if Path(rule.get("source", "")).name.casefold() != source.name.casefold():
                    continue
                if int(rule.get("scene_id", -999)) != int(item.get("scene_id", -1)):
                    continue
                signature = rule.get("signature")
                value = (item.get("acoustic_suggestion") if str(signature).startswith("acoustic:")
                         else item.get("attribution_role") if str(signature).startswith("role:") else None)
                if value and str(signature).split(":", 1)[1].casefold() == str(value).casefold():
                    speaker = rule.get("speaker")
                    break
        if speaker:
            item["speaker"] = speaker
            item["speaker_confidence"] = 1.0
            item["reason"] = "confirmação manual do usuário"
            item["manually_confirmed"] = True
            applied += 1
    return applied


def confirm(report_path: Path, overrides_path: Path, source: str, dialogue_id: str,
            speaker: str, propagate: bool) -> int:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    selected = next((dialogue for file in report.get("files", []) if Path(file.get("input", "")).name == Path(source).name
                     for dialogue in file.get("dialogues", []) if str(dialogue.get("id")) == str(dialogue_id)), None)
    if not selected:
        raise ValueError("Fala não encontrada no relatório atual")
    data = load_overrides(overrides_path)
    data["exact"][_key(source, dialogue_id)] = speaker
    signature = None
    if (propagate and selected.get("acoustic_suggestion") == speaker
            and float(selected.get("acoustic_margin", 0)) >= 0.08):
        signature = f"acoustic:{selected['acoustic_suggestion']}"
    elif propagate and selected.get("attribution_role"):
        signature = f"role:{selected['attribution_role']}"
    if signature:
        rule = {"source": Path(source).name, "scene_id": int(selected.get("scene_id", -1)),
                "signature": signature, "speaker": speaker}
        data["rules"] = [item for item in data["rules"] if not (
            Path(item.get("source", "")).name.casefold() == Path(source).name.casefold()
            and int(item.get("scene_id", -999)) == rule["scene_id"] and item.get("signature") == signature)]
        data["rules"].append(rule)
    overrides_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = overrides_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(overrides_path)
    changed = 0
    for file in report.get("files", []):
        if Path(file.get("input", "")).name != Path(source).name:
            continue
        for item in file.get("dialogues", []):
            exact = str(item.get("id")) == str(dialogue_id)
            same_scene = int(item.get("scene_id", -1)) == int(selected.get("scene_id", -1))
            same_signature = (signature == f"acoustic:{item.get('acoustic_suggestion')}" or
                              signature == f"role:{item.get('attribution_role')}")
            if exact or (signature and same_scene and same_signature):
                item.update({"speaker": speaker, "speaker_confidence": 1.0,
                             "reason": "confirmação manual do usuário", "manually_confirmed": True})
                changed += 1
    report["characters_detected"] = dict(Counter(
        item.get("speaker") or "unknown" for file in report.get("files", []) for item in file.get("dialogues", [])))
    temporary_report = report_path.with_suffix(".tmp")
    temporary_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary_report.replace(report_path)
    return changed
