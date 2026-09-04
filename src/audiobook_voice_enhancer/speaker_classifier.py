"""Extract dialogue speaker embeddings in the private Seed-VC environment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import librosa
import numpy as np
from resemblyzer import VoiceEncoder, preprocess_wav


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path)
    parser.add_argument("dialogues", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    audio, _ = librosa.load(args.audio, sr=16000, mono=True)
    dialogues = json.loads(args.dialogues.read_text(encoding="utf-8"))
    device = "cuda" if __import__("torch").cuda.is_available() else "cpu"
    encoder = VoiceEncoder(device)
    result = []
    for item in dialogues:
        start = max(0, round(float(item["start"]) * 16000))
        end = min(len(audio), round(float(item["end"]) * 16000))
        if end - start > 12 * 16000:
            end = start + 12 * 16000
        sample = preprocess_wav(audio[start:end], source_sr=16000)
        if len(sample) < 0.8 * 16000:
            continue
        embedding = encoder.embed_utterance(sample).astype(np.float32)
        embedding /= max(float(np.linalg.norm(embedding)), 1e-8)
        result.append({"id": item["id"], "embedding": embedding.tolist()})
    args.output.write_text(json.dumps(result), encoding="utf-8")
    print(f"[ACOUSTIC] {len(result)} assinaturas extraídas ({device})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
