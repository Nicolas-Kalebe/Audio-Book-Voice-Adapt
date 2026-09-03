"""Speaker embedding helper executed with the private Seed-VC Python environment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import librosa
import numpy as np
from resemblyzer import VoiceEncoder, preprocess_wav
from sklearn.cluster import AgglomerativeClustering


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path)
    parser.add_argument("chunks", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--speakers", type=int, default=0)
    args = parser.parse_args()

    audio, _ = librosa.load(args.audio, sr=16000, mono=True)
    chunks = json.loads(args.chunks.read_text(encoding="utf-8"))
    device = "cuda" if __import__("torch").cuda.is_available() else "cpu"
    encoder = VoiceEncoder(device)
    embeddings = []
    kept = []
    for chunk in chunks:
        start = max(0, round(float(chunk["start"]) * 16000))
        end = min(len(audio), round(float(chunk["end"]) * 16000))
        sample = preprocess_wav(audio[start:end], source_sr=16000)
        if len(sample) < 16000:
            continue
        embeddings.append(encoder.embed_utterance(sample))
        kept.append(chunk)
    if not embeddings:
        raise RuntimeError("Nenhum trecho de voz longo o suficiente para gerar embeddings")

    matrix = np.asarray(embeddings, dtype=np.float32)
    matrix /= np.maximum(np.linalg.norm(matrix, axis=1, keepdims=True), 1e-8)
    if len(matrix) == 1:
        labels = np.zeros(1, dtype=int)
    elif args.speakers:
        count = min(max(1, args.speakers), len(matrix))
        labels = AgglomerativeClustering(n_clusters=count, metric="cosine", linkage="average").fit_predict(matrix)
    else:
        labels = AgglomerativeClustering(n_clusters=None, distance_threshold=0.32,
                                         metric="cosine", linkage="average").fit_predict(matrix)
        if len(set(int(value) for value in labels)) > 12:
            labels = AgglomerativeClustering(n_clusters=12, metric="cosine", linkage="average").fit_predict(matrix)

    centroids = {}
    for label in set(int(value) for value in labels):
        centroid = matrix[labels == label].mean(axis=0)
        centroids[label] = centroid / max(float(np.linalg.norm(centroid)), 1e-8)
    result = []
    for chunk, label, embedding in zip(kept, labels, matrix):
        item = dict(chunk)
        item["cluster"] = int(label)
        item["similarity"] = round(float(np.dot(embedding, centroids[int(label)])), 4)
        result.append(item)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[VOICE_BANK] {len(result)} trechos agrupados em {len(centroids)} vozes ({device})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
