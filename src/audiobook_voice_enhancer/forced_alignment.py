"""Alinhamento forçado do texto do livro contra o áudio (CTC, MMS_FA do torchaudio).

O livro é o roteiro: em vez de procurar cada fala numa transcrição imperfeita, o
alinhador recebe o texto exato e devolve o tempo de cada palavra. O Whisper só
serve de âncora — o alinhamento por segmento diz, a cada poucos minutos, onde um
parágrafo está — e um token curinga em cada ponta da janela absorve o áudio que
sobra. Medido na cena da Yennefer da Parte 01 (18/10/2026): o método antigo
começava falas curtas até 4 s antes (convertendo narração) e falas longas até
14 s depois (no meio da frase); este pega do primeiro ao último som.
"""
from __future__ import annotations

import re
import subprocess
import unicodedata
from pathlib import Path
from typing import Any

VERSION = "forced-alignment-mms-v1"
ANCHOR_CONFIDENCE = 0.9
MAX_WINDOW_SECONDS = 180.0
MIN_WORD_SCORE = 0.25


def _words(text: str, labels: dict[str, int]) -> list[tuple[str, int, int]]:
    result = []
    for match in re.finditer(r"[\wÀ-ÿ']+", text):
        plain = unicodedata.normalize("NFKD", match.group(0).lower())
        plain = "".join(char for char in plain if char in labels and char not in "-*")
        if plain:
            result.append((plain, match.start(), match.end()))
    return result


def _anchors(alignments: list[dict[str, Any]]) -> dict[int, tuple[float, float]]:
    spans: dict[int, list[float]] = {}
    for item in alignments:
        paragraph = item.get("book_paragraph_id")
        if paragraph is None or float(item.get("alignment_confidence", 0)) < ANCHOR_CONFIDENCE:
            continue
        span = spans.setdefault(int(paragraph), [float(item["audio_start"]), float(item["audio_end"])])
        span[0], span[1] = min(span[0], float(item["audio_start"])), max(span[1], float(item["audio_end"]))
    # Âncora fora de ordem é engano do alinhamento por texto; fica de fora.
    ordered, last = {}, -1.0
    for paragraph in sorted(spans):
        start, end = spans[paragraph]
        if start >= last:
            ordered[paragraph] = (start, end)
            last = start
    return ordered


def windows(needed: set[int], anchors: dict[int, tuple[float, float]], duration: float) -> list[dict[str, Any]]:
    """Para cada parágrafo necessário, da âncora anterior até a seguinte; janelas que se tocam viram uma."""
    keys = sorted(anchors)
    raw = []
    for paragraph in sorted(needed):
        before = [key for key in keys if key <= paragraph]
        after = [key for key in keys if key > paragraph]
        if not before:
            continue
        first = before[-1]
        last = (after[0] - 1) if after else paragraph
        start = anchors[first][0] - 1.0
        end = (anchors[after[0]][0] + 0.5) if after else min(duration, anchors[first][1] + 60.0)
        raw.append([first, last, max(0.0, start), min(duration, end)])
    merged: list[list[Any]] = []
    for item in raw:
        if merged and item[0] <= merged[-1][1] + 1 and item[3] - merged[-1][2] <= MAX_WINDOW_SECONDS:
            merged[-1][1], merged[-1][3] = max(merged[-1][1], item[1]), max(merged[-1][3], item[3])
        else:
            merged.append(item)
    return [{"first": a, "last": b, "start": s, "end": e} for a, b, s, e in merged
            if 0 < e - s <= MAX_WINDOW_SECONDS]


class Aligner:
    def __init__(self, device: str = "cuda"):
        import torch
        import torchaudio

        self.torch, self.torchaudio = torch, torchaudio
        bundle = torchaudio.pipelines.MMS_FA
        self.sample_rate = bundle.sample_rate
        self.device = device if device == "cpu" or torch.cuda.is_available() else "cpu"
        self.model = bundle.get_model(with_star=True).to(self.device).eval()
        self.labels = bundle.get_dict(star="*")

    def _audio(self, path: Path, start: float, end: float):
        import numpy as np

        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(path),
                              "-ac", "1", "-ar", str(self.sample_rate), "-f", "s16le", "-"],
                             capture_output=True, check=True).stdout
        return self.torch.from_numpy(np.frombuffer(raw, dtype=np.int16).astype("float32") / 32768.0).unsqueeze(0)

    def align(self, path: Path, blocks: list[str], window: dict[str, Any]) -> dict[int, list[tuple[int, int, float, float, float]]]:
        """Tempo de cada palavra dos parágrafos da janela: (início_char, fim_char, início_s, fim_s, nota)."""
        torch = self.torch
        waveform = self._audio(path, window["start"], window["end"])
        emissions, step = [], self.sample_rate * 30
        with torch.inference_mode():
            for offset in range(0, waveform.shape[1], step):
                part = waveform[:, offset:offset + step]
                if part.shape[1] >= 400:
                    emissions.append(self.model(part.to(self.device))[0].cpu())
        if not emissions:
            return {}
        emission = torch.cat(emissions, dim=1)
        tokens, index = [self.labels["*"]], []
        for paragraph in range(window["first"], window["last"] + 1):
            for word, char_start, char_end in _words(blocks[paragraph], self.labels):
                index.append((paragraph, char_start, char_end, len(tokens), len(tokens) + len(word)))
                tokens += [self.labels[char] for char in word]
        tokens.append(self.labels["*"])
        if len(tokens) > emission.shape[1]:
            return {}
        targets = torch.tensor([tokens], dtype=torch.int32)
        aligned, scores = self.torchaudio.functional.forced_align(emission.to(self.device), targets.to(self.device),
                                                                  blank=0)
        aligned, scores = aligned[0].cpu().tolist(), scores[0].exp().cpu().tolist()
        seconds = waveform.shape[1] / self.sample_rate / emission.shape[1]
        frames: dict[int, list[tuple[int, float]]] = {}
        position, previous = -1, None
        for frame, token in enumerate(aligned):
            if token != 0 and token != previous:
                position += 1
            if token != 0:
                frames.setdefault(position, []).append((frame, scores[frame]))
            previous = token
        result: dict[int, list[tuple[int, int, float, float, float]]] = {}
        for paragraph, char_start, char_end, first_token, last_token in index:
            hits = [hit for position in range(first_token, last_token) for hit in frames.get(position, [])]
            if hits:
                result.setdefault(paragraph, []).append((
                    char_start, char_end, window["start"] + min(f for f, _ in hits) * seconds,
                    window["start"] + (max(f for f, _ in hits) + 1) * seconds, sum(s for _, s in hits) / len(hits)))
        return result


def refine(path: Path, blocks: list[str], alignments: list[dict[str, Any]], dialogues: list[dict[str, Any]],
           inventory: list[dict[str, Any]], duration: float, wanted, aligner: Aligner | None = None) -> dict[str, Any]:
    """Troca início e fim das falas pedidas pelos tempos do alinhamento forçado.

    `wanted(dialogue)` diz quais falas importam (as que podem ser convertidas); só
    as janelas que as contêm são alinhadas. Fala cujo texto não foi alinhado com
    nota suficiente mantém os tempos antigos.
    """
    spans = {part["candidate_id"]: (part["paragraph"], part["char_start"], part["char_end"])
             for part in inventory if part.get("style") == "dash"}
    targets = [d for d in dialogues if d.get("source") == "book" and str(d.get("id")) in spans and wanted(d)]
    stats = {"version": VERSION, "requested": len(targets), "refined": 0, "kept": 0, "windows": 0}
    if not targets:
        return stats
    plan = windows({spans[str(d["id"])][0] for d in targets}, _anchors(alignments), duration)
    stats["windows"] = len(plan)
    aligner = aligner or Aligner()
    words: dict[int, list[tuple[int, int, float, float, float]]] = {}
    for window in plan:
        for paragraph, items in aligner.align(path, blocks, window).items():
            words.setdefault(paragraph, items)
    for dialogue in targets:
        paragraph, char_start, char_end = spans[str(dialogue["id"])]
        inside = [w for w in words.get(paragraph, []) if w[0] >= char_start and w[1] <= char_end]
        expected = len(_words(blocks[paragraph][char_start:char_end], aligner.labels))
        score = sum(w[4] for w in inside) / len(inside) if inside else 0.0
        if not inside or len(inside) < expected or score < MIN_WORD_SCORE:
            stats["kept"] += 1
            continue
        dialogue.update(start=round(inside[0][2], 3), end=round(inside[-1][3], 3), timing_method=VERSION,
                        alignment_confidence=0.95, forced_alignment_score=round(score, 3))
        stats["refined"] += 1
    return stats


def whole_turn_or_nothing(dialogues: list[dict[str, Any]], minimum_duration: float) -> int:
    """Uma fala não troca de voz pela metade: se um trecho do turno não pode ser
    convertido, nenhum é. Trecho curto demais não veta — ele fica na voz original
    de qualquer jeito, e é a narração entre travessões que o separa do resto."""
    turns: dict[str, list[dict[str, Any]]] = {}
    for dialogue in dialogues:
        if dialogue.get("turn_id"):
            turns.setdefault(str(dialogue["turn_id"]), []).append(dialogue)
    vetoed = 0
    for parts in turns.values():
        if not any(part.get("eligible") for part in parts):
            continue
        blockers = [part for part in parts if not part.get("eligible")
                    and part["end"] - part["start"] >= minimum_duration
                    and "segment too short" not in str(part.get("skip_reason") or "")]
        if blockers:
            for part in parts:
                if part.get("eligible"):
                    part["eligible"] = False
                    part["skip_reason"] = "fala inteira ou nada: outro trecho do mesmo turno não pôde ser convertido"
                    vetoed += 1
    return vetoed
