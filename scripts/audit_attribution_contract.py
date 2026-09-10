"""Summarize saved runs without LLM calls, literary text or rescoring gold labels."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def summarize(report):
    review = report.get('review', {})
    turns = [turn for file in report.get('files', [])
             for turn in file.get('book_speaker_analysis', {}).get('turns', [])]
    rows = [row for turn in turns for row in turn.get('raw_decisions', []) if isinstance(row, dict)]
    # These are scoped textual turns, not the product's dublavel denominator.
    unknown_with_identity = sum(
        row.get('kind') == 'unknown' and bool(turn.get('proposal', {}).get('speaker_entity_id'))
        for turn in turns for row in turn.get('raw_decisions', []) if isinstance(row, dict))
    return {
        'method': review.get('method'),
        'contract': review.get('attribution_contract', 'not_recorded'),
        'execution_mode': report.get('execution_mode'),
        'cold_response_cache_valid': report.get('cold_response_cache_valid'),
        'input_sha256': report.get('input_sha256'),
        'cache': report.get('cache'),
        'llm_calls': review.get('total_llm_calls'),
        'review_seconds': review.get('elapsed_seconds'),
        'model_load_seconds': report.get('model_load_seconds'),
        'product_metrics': report.get('benchmark', {}).get('by_class'),
        'raw_proposal_metrics': report.get('raw_proposal_benchmark', {}).get('by_class'),
        'scoped_textual_turns': len(turns),
        'scoped_raw_kinds': dict(Counter(str(row.get('kind', 'not_present')) for row in rows)),
        'scoped_unknown_with_resolved_speaker': unknown_with_identity,
        'scoped_review_issues': dict(Counter(turn.get('review_issue', 'none') for turn in turns)),
        'all_reviewed_turns': review.get('dialogues_reviewed'),
        'all_response_contract': review.get('response_contract'),
        'accepted_entity_proposals': review.get('accepted_entity_proposals'),
        'accepted_named_entities': review.get('accepted_named_entities'),
        'accepted_anonymous_entities': review.get('accepted_anonymous_entities'),
        'created_entity_proposals': review.get('created_entity_proposals'),
        'entity_rejections_by_reason': dict(Counter(item.get('reason') for item in review.get('entity_rejections', []))),
        'errors': review.get('errors'),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis', action='append', required=True, metavar='LABEL=PATH')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Use a new output file; previous diagnostics are preserved')
    runs = {}
    for spec in args.analysis:
        label, sep, filename = spec.partition('=')
        if not sep or not label or label in runs:
            parser.error('Use unique LABEL=PATH entries')
        runs[label] = summarize(json.loads(Path(filename).read_text(encoding='utf-8')))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(runs, stream, ensure_ascii=False, indent=2)
    for label, run in runs.items():
        print(json.dumps({'label': label, 'product_metrics': run['product_metrics'],
                          'scoped_raw_kinds': run['scoped_raw_kinds'],
                          'unknown_with_identity': run['scoped_unknown_with_resolved_speaker']},
                         ensure_ascii=True))


if __name__ == '__main__':
    main()
