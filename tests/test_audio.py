from pathlib import Path

from audiobook_voice_enhancer.audio import discover_audio, reconstruct


def test_natural_chapter_order(tmp_path):
    for name in ("Chapter 10.mp3", "Chapter 2.mp3", "Chapter 01.mp3", "ignore.txt"):
        (tmp_path / name).touch()
    assert [item.name for item in discover_audio(tmp_path)] == ["Chapter 01.mp3", "Chapter 2.mp3", "Chapter 10.mp3"]


def test_no_replacements_preserves_original_bytes(tmp_path):
    source, target = tmp_path / "source.mp3", tmp_path / "target.mp3"
    source.write_bytes(b"not decoded because copy is intentional")
    reconstruct(source, [], target, "320k")
    assert target.read_bytes() == source.read_bytes()


def test_reconstrucao_com_centenas_de_falas_nao_estoura_a_linha_de_comando(tmp_path):
    """A Parte 03 tinha 187 falas convertidas e o Windows recusou o comando do FFmpeg
    (WinError 206). O grafo vai em arquivo e as entradas ganham nomes curtos."""
    import shutil

    import numpy as np
    import pytest
    import soundfile as sf

    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg ausente")
    sr = 8000
    source = tmp_path / "fonte.wav"
    sf.write(source, np.zeros((sr * 260, 1), dtype="float32"), sr)
    pasta = tmp_path / ("um_caminho_bem_comprido_para_simular_o_cache_" * 3)
    pasta.mkdir()
    replacements = []
    for index in range(250):
        clip = pasta / f"{index:04d}-{'x' * 40}.wav"
        sf.write(clip, np.full((sr // 2, 1), 0.5, dtype="float32"), sr)
        replacements.append((index + 1.0, index + 1.5, clip))
    target = tmp_path / "saida.wav"
    reconstruct(source, replacements, target, "320k")
    audio, _ = sf.read(target)
    assert abs(len(audio) - sr * 260) < sr // 10
    assert audio[int(sr * 1.2)].max() > 0.3 and abs(audio[int(sr * 0.5)]).max() < 0.01
