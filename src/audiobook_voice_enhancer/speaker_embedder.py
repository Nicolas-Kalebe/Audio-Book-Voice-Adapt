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
    purities = []
    kept = []
    for chunk in chunks:
        start = max(0, round(float(chunk["start"]) * 16000))
        end = min(len(audio), round(float(chunk["end"]) * 16000))
        sample = preprocess_wav(audio[start:end], source_sr=16000)
        if len(sample) < 16000:
            continue
        embedding = encoder.embed_utterance(sample)
        embeddings.append(embedding)
        # Compare short windows inside the excerpt. A sudden second speaker tends
        # to lower this value even when the full-excerpt embedding looks plausible.
        partials = []
        window = round(1.2 * 16000)
        if len(sample) >= window * 2:
            positions = np.linspace(0, len(sample) - window, min(4, max(2, len(sample) // window))).astype(int)
            for position in positions:
                partial = sample[position:position + window]
                partials.append(encoder.embed_utterance(partial))
        if len(partials) >= 2:
            partial_matrix = np.asarray(partials, dtype=np.float32)
            partial_matrix /= np.maximum(np.linalg.norm(partial_matrix, axis=1, keepdims=True), 1e-8)
            similarities = partial_matrix @ partial_matrix.T
            purity = float(np.min(similarities[np.triu_indices(len(partial_matrix), 1)]))
            purity_verified = True
        else:
            purity = 0.75  # short excerpts rely more heavily on cluster similarity
            purity_verified = False
        purities.append(purity)
        chunk["purity_verified"] = purity_verified
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
    for chunk, label, embedding, purity in zip(kept, labels, matrix, purities):
        item = dict(chunk)
        item["cluster"] = int(label)
        item["similarity"] = round(float(np.dot(embedding, centroids[int(label)])), 4)
        item["purity"] = round(purity, 4)
        result.append(item)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[VOICE_BANK] {len(result)} trechos agrupados em {len(centroids)} vozes ({device})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
