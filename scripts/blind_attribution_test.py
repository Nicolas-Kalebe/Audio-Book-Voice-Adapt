"""Prova cega de atribuicao: o gabarito vem do proprio livro, nao de um anotador.

Metade das atribuicoes explicitas ("— ... — disse Fulano") de um trecho e
apagada do texto; o modelo atribui todos os turnos sem saber quais serao
corrigidos, e so os apagados entram no placar. Os nomes dos personagens sao
trocados por pseudonimos para que a memoria do livro nao ajude.

    prepare -> input.txt (vai ao modelo) e key.json (fica fora do alcance dele)
    score   -> corrige as respostas contra key.json
"""
from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path

from audiobook_voice_enhancer.benchmark import _role_key
from audiobook_voice_enhancer.book import load_book, paragraphs
from audiobook_voice_enhancer.book_speakers import build_book
from audiobook_voice_enhancer.dialogue import book_character_names

PSEUDONYMS = [
    "Avel", "Brin", "Cael", "Dorin", "Elis", "Fenn", "Garr", "Hale", "Iven", "Joss",
    "Kerr", "Lio", "Maro", "Nils", "Orin", "Perr", "Quen", "Rask", "Sael", "Tarn",
    "Ulle", "Vane", "Wren", "Xan", "Yeli", "Zorr", "Abri", "Bex", "Cido", "Dren",
    "Emre", "Fis", "Gwil", "Huro", "Ilke", "Jaro", "Kesh", "Lune", "Mirr", "Nao",
    "Odo", "Pim", "Ruel", "Siv", "Tobe", "Ubi", "Vesk", "Wim", "Yorr", "Zeb",
    "Alder", "Bramm", "Coll", "Dace", "Edro", "Falk", "Gise", "Harl", "Isk", "Jem",
    "Kade", "Lorr", "Mabe", "Nesk", "Ollo", "Prae", "Rook", "Seff", "Tull", "Urs",
    "Vell", "Wyle", "Yarr", "Zim", "Arro", "Belk", "Corr", "Duvo", "Esk", "Firn",
    "Gorm", "Hesk", "Imo", "Jusk", "Kiv", "Lask", "Moll", "Nurr", "Opp", "Quil",
]
FUNCTION_WORDS = {"de", "da", "do", "das", "dos", "e", "a", "o", "von", "van", "of"}
MASK = "[…]"

INSTRUCTIONS = """\
Tarefa: para cada turno de fala listado, diga QUEM fala, usando apenas o texto abaixo.

- Alguns trechos de narracao foram apagados e aparecem como [...]; deduza pelo contexto.
- Responda com o nome do personagem como ele aparece no texto.
- Se a fala vem de um papel sem nome (ex.: "um guarda"), descreva o papel.
- Se nao houver certeza razoavel, responda null. Abster e seguro; trocar a voz
  errada e o unico defeito que conta. Mas abster em excesso tambem reprova.

Saida: um unico objeto JSON {"<turn_key>": "<nome>" | null, ...} com TODAS as
chaves listadas em TURNOS, e nada mais.
"""


def _name_tokens(names: set[str]) -> list[str]:
    tokens = {token for name in names for token in re.findall(r"[^\W\d_]+", name)
              if token[:1].isupper() and token.lower() not in FUNCTION_WORDS and len(token) > 2}
    return sorted(tokens, key=lambda value: (-len(value), value))


def prepare(args: argparse.Namespace) -> int:
    blocks = paragraphs(load_book(args.book))
    model = build_book(blocks, {})
    first, last = args.first, args.last
    in_range = [turn for turn in model["turns"]
                if first <= turn["fragments"][0]["paragraph"] <= last and turn["kind"] == "speech"]
    explicit = [turn for turn in in_range if turn["status"] == "explicit"]
    rng = random.Random(args.seed)
    masked = sorted(rng.sample(explicit, round(len(explicit) * args.mask_ratio)),
                    key=lambda turn: turn["fragments"][0]["paragraph"])

    edited = {index: blocks[index] for index in range(first, last + 1)}
    spans: dict[int, list[tuple[int, int]]] = {}
    for turn in masked:
        for span in turn["evidence"]:
            spans.setdefault(span["paragraph"], []).append((span["start"], span["end"]))
    for paragraph, ranges in spans.items():
        text = edited[paragraph]
        for start, end in sorted(set(ranges), reverse=True):
            text = text[:start] + MASK + text[end:]
        edited[paragraph] = text

    names = book_character_names(blocks, {}) | {entity["name"] for entity in model["entities"].values()
                                                if entity["kind"] == "named"}
    tokens = set(_name_tokens(names))
    # Sobrenome que segue um nome conhecido em qualquer ponto do livro ("Fulana Tal")
    # tambem e nome: o trecho pode usar so o sobrenome ("a senhora Tal").
    window = " ".join(blocks)
    for token in list(tokens):
        for match in re.finditer(rf"\b{re.escape(token)}\s+([A-ZÀ-Ý][^\W\d_]{{2,}})", window):
            if match.group(1).lower() not in FUNCTION_WORDS:
                tokens.add(match.group(1))
    # Grafia variante do mesmo nome ("Fulanx" por "Fulano") tambem vazaria a identidade.
    # Tudo em ordem fixa: iterar um set muda a cada execucao do Python, e foi assim
    # que um blocks.json regenerado saiu com pseudonimos diferentes da chave.
    known = sorted(tokens)
    variants = set()
    for word in sorted(set(re.findall(r"\b[A-ZÀ-Ý][^\W\d_]{4,}\b", window))):
        base = next((token for token in known if len(token) >= 5 and token[:5] == word[:5]), None)
        if base and word not in tokens and abs(len(word) - len(base)) <= 1:
            variants.add(word)
    tokens |= variants
    # Palavra comum capitalizada em inicio de frase nao e nome: trocar "Primeiro"
    # por um pseudonimo inventaria um personagem.
    lowercase = set(re.findall(r"\b[a-zà-ÿ][^\W\d_]*\b", window))
    tokens = sorted((token for token in tokens if token.lower() not in lowercase),
                    key=lambda value: (-len(value), value))
    if len(tokens) > len(PSEUDONYMS):
        rng.shuffle(tokens)
    pool = PSEUDONYMS[:]
    rng.shuffle(pool)
    mapping = dict(zip(tokens, pool + [f"Nome{index}" for index in range(len(tokens) - len(pool))]))
    frozen_key = args.key_dir / "key.json"
    if args.blocks_only:
        # Regerar o pacote nunca pode reinventar pseudonimos: usa os da chave congelada.
        frozen = json.loads(frozen_key.read_text(encoding="utf-8"))
        if sorted(frozen["masked_gold"]) != sorted(turn["id"] for turn in masked):
            raise SystemExit("As falas apagadas nao batem com a chave congelada")
        mapping = {real: fake for fake, real in frozen["pseudonyms"].items()}
    pattern = re.compile(r"\b(" + "|".join(map(re.escape, mapping)) + r")\b")

    def disguise(value: str) -> str:
        return pattern.sub(lambda match: mapping[match.group(1)], value)

    lines = [INSTRUCTIONS, "", f"TEXTO (paragrafos {first}-{last}):", ""]
    lines += [f"[{index}] {disguise(edited[index])}" for index in range(first, last + 1)]
    lines += ["", "TURNOS (chave | paragrafo | inicio da fala):", ""]
    for turn in in_range:
        part = turn["fragments"][0]
        snippet = " ".join(disguise(part["text"]).split())[:90]
        lines.append(f"{turn['id']} | {part['paragraph']} | {snippet}")
    package = "\n".join(lines)
    unmasked_names = [token for token in mapping if re.search(rf"\b{re.escape(token)}\b", package)]
    if unmasked_names:
        raise SystemExit(f"Nome original vazou para o pacote: {unmasked_names[:5]}")

    gold = {turn["id"]: model["entities"][turn["speaker_entity_id"]]["name"] for turn in masked}
    args.input_dir.mkdir(parents=True, exist_ok=True)
    # Os mesmos paragrafos disfarcados, para o protocolo frontier montar o proprio pedido.
    disguised = [disguise(edited[index]) if first <= index <= last else "" for index in range(len(blocks))]
    (args.input_dir / "blocks.json").write_text(json.dumps(disguised, ensure_ascii=False), encoding="utf-8")
    if args.blocks_only:
        print(f"blocks.json -> {args.input_dir}")
        return 0
    args.key_dir.mkdir(parents=True, exist_ok=True)
    (args.input_dir / "input.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (args.key_dir / "key.json").write_text(json.dumps({
        "range": [first, last], "seed": args.seed, "masked_gold": gold,
        "pseudonyms": {fake: real for real, fake in mapping.items()},
        "turns": [turn["id"] for turn in in_range],
        "explicit_visible": [turn["id"] for turn in explicit if turn["id"] not in gold],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(in_range)} turnos; {len(explicit)} explicitos; {len(gold)} apagados e corrigidos; "
          f"{len(mapping)} nomes disfarcados")
    return 0


def score(args: argparse.Namespace) -> int:
    key = json.loads(args.key.read_text(encoding="utf-8"))
    reverse = key["pseudonyms"]
    pattern = re.compile(r"\b(" + "|".join(map(re.escape, reverse)) + r")\b")
    rows = []
    for path in args.answers:
        answers = json.loads(path.read_text(encoding="utf-8"))
        missing = [turn for turn in key["turns"] if turn not in answers]
        correct = wrong = abstained = 0
        errors = []
        for turn, expected in key["masked_gold"].items():
            raw = answers.get(turn)
            if not raw:
                abstained += 1
                continue
            predicted = pattern.sub(lambda match: reverse[match.group(1)], raw)
            predicted_words, expected_words = set(_role_key(predicted).split()), set(_role_key(expected).split())
            # "Fulana" e "Fulana Tal" sao a mesma pessoa; o livro usa as duas formas.
            if predicted_words and (predicted_words <= expected_words or expected_words <= predicted_words):
                correct += 1
            else:
                wrong += 1
                errors.append((turn, expected, predicted))
        total = len(key["masked_gold"])
        assigned = correct + wrong
        rows.append((path.stem, correct, wrong, abstained, total, missing, errors))
        print(f"\n## {path.stem}")
        print(f"precisao {correct / assigned:.2%} | cobertura {assigned / total:.2%} | "
              f"{correct} certos, {wrong} errados, {abstained} abstencoes de {total} apagados")
        if missing:
            print(f"turnos sem resposta: {len(missing)}")
        for turn, expected, predicted in errors:
            print(f"  ERRO {turn}: esperado {expected}, respondeu {predicted}")
    if len(args.answers) == 2:
        first, second = (json.loads(path.read_text(encoding="utf-8")) for path in args.answers)
        unscored = [turn for turn in key["turns"] if turn not in key["masked_gold"]]
        same = sum(1 for turn in unscored
                   if _role_key(first.get(turn) or "") == _role_key(second.get(turn) or ""))
        print(f"\nConcordancia entre os dois nos {len(unscored)} turnos nao corrigidos: {same / len(unscored):.2%}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--book", type=Path, required=True)
    prep.add_argument("--first", type=int, required=True)
    prep.add_argument("--last", type=int, required=True)
    prep.add_argument("--input-dir", type=Path, required=True)
    prep.add_argument("--key-dir", type=Path, required=True)
    prep.add_argument("--seed", type=int, default=20261018)
    prep.add_argument("--mask-ratio", type=float, default=0.5)
    prep.add_argument("--blocks-only", action="store_true",
                      help="So regrava blocks.json; nao toca na chave nem no input.txt ja congelados")
    sc = sub.add_parser("score")
    sc.add_argument("--key", type=Path, required=True)
    sc.add_argument("answers", type=Path, nargs="+")
    args = parser.parse_args()
    return prepare(args) if args.command == "prepare" else score(args)


if __name__ == "__main__":
    raise SystemExit(main())
