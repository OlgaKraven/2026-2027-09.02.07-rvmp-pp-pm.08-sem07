import argparse
import json
from pathlib import Path
from .content import fingerprint, load


def main():
    parser = argparse.ArgumentParser(description='Agent Methodist: local practice generator')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('validate', 'fingerprint', 'build', 'check'):
        child = sub.add_parser(name)
        child.add_argument('project', type=Path)
        if name == 'build':
            child.add_argument('--release', action='store_true')
            child.add_argument('--evidence', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'build':
            from .build import build
            result = build(args.project, args.release, args.evidence)
        elif args.command == 'check':
            from .build import check_output, check_pdf_content
            result = check_output(args.project/'site')
            raw, data = load(args.project)
            manifest = json.loads((args.project/'site/manifest.json').read_text(encoding='utf-8'))
            if manifest['fingerprint'] != fingerprint(args.project, raw):
                raise ValueError('Build is stale; rebuild after source or generator changes')
            check_pdf_content(args.project/'site', data)
        else:
            raw, _ = load(args.project)
            result = fingerprint(args.project, raw) if args.command == 'fingerprint' else {'valid': True, 'areas': len(raw['areas'])}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, OSError, ImportError) as error:
        parser.exit(1, f'Error: {error}\n')


if __name__ == '__main__':
    main()
