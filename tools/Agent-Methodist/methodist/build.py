"""Transactional local build with output integrity and link checks."""
import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from .content import ASSETS, fingerprint, load, pages, require_release, source_path
from .rendering import html_page, image_name, pdf, report_markdown

MARKER = '.methodist-generated'
CONTROL_FILES = {MARKER, '.nojekyll'}


def check_pdf_content(site, data):
    from pypdf import PdfReader
    def compact(text):
        return re.sub(r'\s+', '', text)
    for name, specs in [('assignment', data['assignment']+data['areas']), ('guide', data['guide'])]:
        text = compact(''.join(p.extract_text() for p in PdfReader(site/f'downloads/{name}.pdf').pages))
        for page in specs:
            for block in page['blocks']:
                for line in [page['title'], block['title'], *block['text'].splitlines()]:
                    if line.strip() and compact(line) not in text:
                        raise ValueError(f'PDF lost source text ({name}): {line[:100]}')


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = set()
    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if 'id' in attributes:
            if attributes['id'] in self.ids:
                raise ValueError('Duplicate HTML anchor')
            self.ids.add(attributes['id'])
        self.links.extend(attributes[key] for key in ('href', 'src') if key in attributes)


def check_output(site):
    from pypdf import PdfReader
    site = Path(site).resolve()
    manifest = json.loads((site/'manifest.json').read_text(encoding='utf-8'))
    for name in CONTROL_FILES:
        if not (site/name).is_file():
            raise ValueError(f'Missing site control file: {name}')
    actual = {p.relative_to(site).as_posix() for p in site.rglob('*') if p.is_file() and p.name not in {'manifest.json', *CONTROL_FILES}}
    if actual != set(manifest['files']):
        raise ValueError('Unexpected or missing generated files')
    for name, digest in manifest['files'].items():
        path = (site/name).resolve()
        if not path.is_relative_to(site) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f'Output modified or outside site: {name}')
    parsers = {}
    for path in site.glob('*.html'):
        parser = Links(); parser.feed(path.read_text(encoding='utf-8')); parsers[path] = parser
    for path, parser in parsers.items():
        for link in parser.links:
            url = urlsplit(link)
            if url.scheme or url.netloc:
                if url.scheme == 'https' and url.netloc and not url.username and not url.password:
                    continue
                raise ValueError(f'Unexpected external link: {link}')
            target = (path.parent/unquote(url.path)).resolve() if url.path else path
            if not target.is_relative_to(site) or not target.is_file():
                raise ValueError(f'Broken link: {link}')
            if url.fragment and (target not in parsers or unquote(url.fragment) not in parsers[target].ids):
                raise ValueError(f'Broken anchor: {link}')
    counts = {}
    for name in ('assignment', 'guide'):
        reader = PdfReader(site/f'downloads/{name}.pdf')
        if not reader.pages:
            raise ValueError('Empty PDF')
        for page in reader.pages:
            if abs(float(page.mediabox.width)-841.89) > 1 or abs(float(page.mediabox.height)-595.28) > 1:
                raise ValueError('Expected landscape A4')
        counts[name] = len(reader.pages)
    return counts


def build(root, release=False, evidence=None):
    root = Path(root).resolve()
    raw, data = load(root)
    stamp = fingerprint(root, raw)
    if release:
        require_release(root, raw, evidence)
    output = root/'site'
    if output.is_symlink() or output.resolve() != root/'site':
        raise ValueError('Unsafe output path')
    if output.exists() and (not output.is_dir() or not (output/MARKER).is_file()):
        raise ValueError('Refusing to replace site not owned by this generator')
    with tempfile.TemporaryDirectory(prefix='methodist-', dir=root) as temporary:
        stage = Path(temporary)/'site'
        (stage/'assets/screenshots').mkdir(parents=True)
        (stage/'downloads').mkdir()
        for asset in ('style.css', 'favicon.svg'):
            shutil.copyfile(ASSETS/asset, stage/'assets'/asset)
        for page in pages(data):
            for block in page['blocks']:
                if block['kind'] == 'image':
                    shutil.copyfile(source_path(root, block['path']), stage/'assets/screenshots'/image_name(block))
        for item in data['code_files']:
            shutil.copyfile(source_path(root, item['path']), stage/'downloads'/item['name'])
        for item in data['downloads']:
            target = stage/'downloads'/item['name']
            if item['kind'] == 'file':
                shutil.copyfile(source_path(root, item['path']), target)
            else:
                with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
                    for name in item['files']:
                        archive.write(source_path(root, name), name)
        for name, section in [('index.html', 'assignment'), ('lessons.html', 'guide'), ('areas.html', 'areas')]:
            (stage/name).write_text(html_page(data, section, release), encoding='utf-8')
        (stage/'downloads/report-template.md').write_text(report_markdown(data), encoding='utf-8')
        for section in ('assignment', 'guide'):
            pdf(root, stage/f'downloads/{section}.pdf', data, section, release)
        (stage/MARKER).write_text('Agent Methodist\n', encoding='utf-8')
        (stage/'.nojekyll').touch()
        manifest = {'schema_version': 1, 'fingerprint': stamp, 'release': release,
                    'files': {p.relative_to(stage).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(stage.rglob('*')) if p.is_file() and p.name not in CONTROL_FILES}}
        (stage/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        counts = check_output(stage)
        check_pdf_content(stage, data)
        # Keep old output until the new build has passed all structural checks.
        backup = Path(temporary)/'previous-site'
        if output.exists():
            output.rename(backup)
        try:
            stage.rename(output)
        except OSError:
            if backup.exists():
                backup.rename(output)
            raise
    return {'site': str(output), 'fingerprint': stamp, 'pdf_pages': counts, 'release': release}
