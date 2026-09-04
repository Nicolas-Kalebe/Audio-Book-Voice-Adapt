from __future__ import annotations

import argparse
import json
from pathlib import Path

from audiobook_voice_enhancer.benchmark import evaluate_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Compara a analise da Parte 01 com o gabarito auditado")
    parser.add_argument("--gold", type=Path, default=Path("benchmarks/part01_gold.yaml"))
    parser.add_argument("--analysis", type=Path, default=Path("output/analysis.json"))
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args()
    result, markdown = evaluate_files(args.gold, args.analysis)
    print(markdown)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(markdown, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

