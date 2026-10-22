"""Inspect packaged Python code; do not mistake compressed EXE strings for code."""
import argparse
import hashlib
import json
import types
from pathlib import Path
from PyInstaller.archive.readers import CArchiveReader


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, types.CodeType):
        for item in value.co_consts:
            yield from strings(item)
    elif isinstance(value, (tuple, frozenset)):
        for item in value:
            yield from strings(item)


def audit(exe):
    archive = CArchiveReader(str(exe)).open_embedded_archive('PYZ.pyz')
    report = {'sha256':hashlib.file_digest(exe.open('rb'), 'sha256').hexdigest(), 'modules':{}}
    for name in ('desktop.transport', 'desktop.controls', 'desktop.diagnostics', 'desktop.ui'):
        code = archive.extract(name)
        values = list(strings(code))
        report['modules'][name] = {
            'old_failure_text_present':any('execution rejected/failed' in s for s in values),
            'markers':[s for s in ('category=rejected', 'native=', 'stack=', 'target_hwnd', 'foreground_hwnd', 'target_status:', '最後の操作') if any(s in value for value in values)],
        }
    assert all(not item['old_failure_text_present'] for item in report['modules'].values())
    assert 'native=' in report['modules']['desktop.diagnostics']['markers']
    assert 'target_hwnd' in report['modules']['desktop.controls']['markers']
    assert '最後の操作' in report['modules']['desktop.ui']['markers']
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--expected-sha256', required=True)
    args = parser.parse_args()
    report = audit(args.exe)
    assert report['sha256'] == args.expected_sha256.lower()
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('PASS: packaged diagnostic code audit, SHA256='+report['sha256'])


if __name__ == '__main__':
    main()
