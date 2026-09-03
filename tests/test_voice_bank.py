import json

import numpy as np
import soundfile as sf

from audiobook_voice_enhancer.voice_bank import _montage, save_voice


def test_montage_and_save_voice_reference(tmp_path):
    sample_rate = 16000
    seconds = 8
    timeline = np.arange(sample_rate * seconds) / sample_rate
    audio = (0.15 * np.sin(2 * np.pi * 220 * timeline)).astype("float32")
    normalized = tmp_path / "normalized.wav"
    sf.write(normalized, audio, sample_rate)
    segments = [
        {"start": 0, "end": 3, "duration": 3, "quality": .9, "similarity": .95},
        {"start": 4, "end": 7, "duration": 3, "quality": .8, "similarity": .9},
    ]
    preview = tmp_path / "preview.wav"
    assert _montage(normalized, segments, preview, 5) == 5
    assert preview.is_file()

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "source": str(tmp_path / "source.mp3"),
        "normalized_audio": str(normalized),
        "voices": [{"id": "voice-01", "segments": segments,
                    "candidates": [{**segments[0], "included": True}, {**segments[1], "included": False}],
                    "cohesion": .92}],
    }), encoding="utf-8")
    characters = tmp_path / "config" / "characters.json"
    target = save_voice(tmp_path, manifest, "voice-01", "Ana", characters)
    saved = json.loads(characters.read_text(encoding="utf-8"))
    assert target.is_file()
    assert saved["Ana"]["mode"] == "convert"
    assert saved["Ana"]["voice_reference"] == "voices/ana_ref.wav"
    assert saved["Ana"]["voice_bank"]["reference_seconds"] == 3
