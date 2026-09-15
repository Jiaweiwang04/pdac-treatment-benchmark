"""Check Pilot documentation alongside the unchanged upstream provenance checks."""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / 'code/src'))
from pdac_benchmark.v2_0.documentation import DOCS, check_documents


def main():
    DOCS['docs/notes/v2.0/pilot_review_protocol_v2.0.md'] = [
        '范围与审核单位', '病例与时间处理', '方案与证据',
        '独立审核与裁定', '输出与复现', '局限与后续',
    ]
    result = check_documents(BASE)
    output = BASE / 'code/results/v2.0/09_pilot_review/pilot_documentation_check_v2.0.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result['status'] != 'passed')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf8')
    raise SystemExit(main())
