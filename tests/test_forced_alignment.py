"""Alinhamento forçado: janelas entre âncoras, tempos por palavra e fala inteira ou nada.

O modelo acústico não roda aqui; um alinhador falso devolve tempos por palavra e o
teste confere o que o código faz com eles.
"""
from __future__ import annotations

from audiobook_voice_enhancer.book_inventory import dialogue_inventory
from audiobook_voice_enhancer.forced_alignment import _anchors, _words, refine, whole_turn_or_nothing, windows

LABELS = {char: index for index, char in enumerate("-aiendoutsrmklghybpwcvjzf'qx*")}


def test_ancora_fora_de_ordem_fica_de_fora():
    anchors = _anchors([
        {"book_paragraph_id": 1, "audio_start": 10, "audio_end": 12, "alignment_confidence": .99},
        {"book_paragraph_id": 2, "audio_start": 900, "audio_end": 905, "alignment_confidence": .99},
        {"book_paragraph_id": 3, "audio_start": 20, "audio_end": 25, "alignment_confidence": .99},
        {"book_paragraph_id": 4, "audio_start": 30, "audio_end": 35, "alignment_confidence": .5},
    ])
    assert list(anchors) == [1, 2]


def test_janela_vai_da_ancora_anterior_ate_a_seguinte_e_junta_vizinhas():
    anchors = {10: (100.0, 105.0), 12: (110.0, 115.0), 20: (200.0, 210.0)}
    plan = windows({11, 12}, anchors, 1000.0)
    assert plan == [{"first": 10, "last": 19, "start": 99.0, "end": 200.5}]


def test_janela_longa_demais_e_descartada():
    assert windows({10}, {10: (0.0, 5.0), 11: (500.0, 505.0)}, 1000.0) == []


def test_palavras_perdem_acento_e_guardam_posicao():
    assert _words("— Não, Iara!", LABELS) == [("nao", 2, 5), ("iara", 7, 11)]


class AlinhadorFalso:
    labels = LABELS

    def __init__(self, tempos):
        self.tempos = tempos

    def align(self, path, blocks, window):
        result = {}
        for paragraph in range(window["first"], window["last"] + 1):
            for index, (_, start, end) in enumerate(_words(blocks[paragraph], LABELS)):
                begin = self.tempos[paragraph] + index
                result.setdefault(paragraph, []).append((start, end, begin, begin + .8, .9))
        return result


def test_fala_recebe_o_tempo_da_primeira_e_da_ultima_palavra():
    blocks = ["Iara entrou.", "— Abra a porta agora — disse Iara.", "Bento obedeceu."]
    alignments = [{"book_paragraph_id": p, "audio_start": t, "audio_end": t + 3, "alignment_confidence": .99}
                  for p, t in ((0, 10.0), (1, 20.0), (2, 40.0))]
    dialogue = {"id": "1-0", "source": "book", "start": 15.0, "end": 30.0, "alignment_confidence": .5}
    stats = refine(None, blocks, alignments, [dialogue], dialogue_inventory(blocks), 100.0,
                   lambda d: True, aligner=AlinhadorFalso({0: 10.0, 1: 20.0, 2: 40.0}))
    # "Abra a porta agora" são as quatro primeiras palavras do parágrafo 1.
    assert (dialogue["start"], dialogue["end"]) == (20.0, 23.8)
    assert dialogue["alignment_confidence"] == .95
    assert stats["refined"] == 1


def turno(*partes):
    return [{"turn_id": "book-7", "start": 0.0, "end": duracao, "eligible": elegivel, "skip_reason": motivo}
            for duracao, elegivel, motivo in partes]


def test_trecho_que_nao_pode_converter_veta_o_turno_inteiro():
    partes = turno((3.0, True, None), (12.0, False, "alignment confidence below threshold"))
    assert whole_turn_or_nothing(partes, .8) == 1
    assert not any(parte["eligible"] for parte in partes)


def test_trecho_curto_demais_nao_veta():
    partes = turno((0.5, False, "segment too short"), (12.0, True, None))
    assert whole_turn_or_nothing(partes, .8) == 0
    assert partes[1]["eligible"]
