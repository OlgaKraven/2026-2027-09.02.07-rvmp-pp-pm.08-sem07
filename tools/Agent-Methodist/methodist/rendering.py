"""HTML design derived from the user's practice template; paginated PDF output."""
import hashlib
import html
from pathlib import Path
from urllib.parse import quote, urlsplit
from .content import source_path

ESC = html.escape


STAND_LABEL = 'Скачать CSV для предметной области'


def area_download_label(data, name, page=None):
    custom = next((item.get('label') for item in data['downloads'] if item['name'] == name), None)
    if custom:
        return custom
    if name == 'Directory-starter.zip':
        return 'Скачать неполную заготовку электронного справочника (ZIP)'
    if name == 'Directory-demo-complete.zip':
        return 'Скачать полный демонстрационный справочник для сверки (ZIP)'
    if name == 'Directory-source.zip':
        return 'Скачать исходный проект электронного справочника (ZIP)'
    if name == 'demo.csv':
        return 'Скачать демонстрационный CSV для проверки импорта'
    if name == 'ServiceDesk-fixed-example.zip':
        return 'Скачать исправленный демонстрационный проект (ZIP)'
    if name not in data.get('shared_area_downloads', []):
        if name == 'Program-starter.cs':
            return 'Скачать исходный код приложения без CSV (Program.cs)'
        if name == 'Program-fixed.cs':
            return 'Скачать код исправленного демонстрационного приложения (Program.cs)'
        if name.startswith('variant-') and page and page.get('subject'):
            return f'Скачать CSV для области «{page["subject"]}» ({name})'
        if name == 'demo.csv':
            return 'Скачать демонстрационный CSV с неполной строкой (demo.csv)'
        if name == 'demo-valid.csv':
            return 'Скачать демонстрационный CSV без дефектной строки (demo-valid.csv)'
        return f'{STAND_LABEL} ({name})'
    labels = {
        'ServiceDesk-source.zip': 'Скачать исходный проект ServiceDesk (ZIP)',
        'ServiceDesk-csv-draft.zip': 'Скачать заготовку подключения CSV (ZIP)',
        'ServiceDesk-fixed-example.zip': 'Скачать исправленный демонстрационный проект (ZIP)',
    }
    return labels.get(name, f'Скачать общий материал для всех вариантов ({name})')


def download_description(name, data=None):
    if data:
        custom = next((item.get('description') for item in data['downloads'] if item['name'] == name), None)
        if custom:
            return custom
    return {
        'Directory-starter.zip': 'Начните с неё: дополните интерфейс и функции для своей предметной области.',
        'Directory-demo-complete.zip': 'Сверяйте устройство после самостоятельной разработки; это решение другой области.',
        'Directory-source.zip': 'Начните с него: распакуйте проект, откройте index.html и проверьте импорт.',
        'ServiceDesk-source.zip': 'Начните с него: соберите и проверьте приложение без CSV.',
        'ServiceDesk-csv-draft.zip': 'Откройте после первой проверки, чтобы изучить дефекты импорта и экспорта.',
        'ServiceDesk-fixed-example.zip': 'Сверяйтесь после самостоятельной диагностики; это решение демонстрационной области.',
        'demo.csv': 'Откройте до запуска, затем загрузите для проверки качества входных строк.',
        'demo-valid.csv': 'Используйте для отдельной проверки экспорта и повторного импорта.',
    }.get(name, 'Подключите данные своего варианта после проверки исходного приложения.')


def download_url(data, name, release=False):
    base = data['meta'].get('site_url')
    if not base:
        if release:
            raise ValueError('meta.site_url is required for downloadable links in release PDFs')
        return quote(name)  # Draft PDF and its downloads share a directory.
    parsed = urlsplit(base)
    if parsed.scheme != 'https' or not parsed.netloc or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError('meta.site_url must be an HTTPS site root without query or fragment')
    return base.rstrip('/') + '/downloads/' + quote(name)


def image_name(block):
    return hashlib.sha256(block['path'].encode()).hexdigest()[:16] + Path(block['path']).suffix.lower()


def html_page(data, section, release=False):
    meta = data['meta']
    titles = {'assignment': meta['title'], 'guide': 'Инструкция и образец', 'areas': 'Список предметных областей'}
    routes = [('assignment', 'index.html', 'Задание'), ('guide', 'lessons.html', 'Инструкция и образец'), ('areas', 'areas.html', 'Предметные области')]
    nav = ''.join(f'<a href="{url}" {"aria-current=page" if key == section else ""}>{label}</a>' for key, url, label in routes)
    body = []
    if section == 'guide':
        demo = data['demonstration']
        body.append(f'<article class="lesson"><h2>{ESC(demo["title"])}</h2><p>{ESC(demo["description"])}</p></article>')
    for index, page in enumerate(data[section], 1):
        anchor = f'variant-{page["id"]:02}' if section == 'areas' else f'page-{index}'
        blocks = []
        for block in page['blocks']:
            title = f'<h3>{ESC(block["title"])}</h3>'
            if block['kind'] == 'image':
                blocks.append(f'<figure class="block screenshot">{title}<img src="assets/screenshots/{image_name(block)}" alt="{ESC(block.get("alt", block["title"]))}"><figcaption>{ESC(block["text"])}</figcaption></figure>')
            else:
                tag = 'pre' if block['kind'] == 'code' else 'p'
                text = ESC(block['text'])
                if tag == 'p':
                    text = text.replace('\n', '<br>')
                    for link in block.get('links', []):
                        text += f'<br><a href="{ESC(link["url"], quote=True)}">{ESC(link["label"])}</a> — {ESC(link["description"])}'
                blocks.append(f'<section class="block {block["kind"]}">{title}<{tag}>{text}</{tag}></section>')
        download_blocks = [f'<p class="block"><a class="button" href="downloads/{quote(name)}">{ESC(area_download_label(data, name, page))}</a><br>{ESC(download_description(name, data))}</p>' for name in page.get('downloads', [])]
        blocks = download_blocks + blocks
        body.append(f'<article class="lesson" id="{anchor}"><p class="eyebrow">{ESC(page.get("kicker", ""))}</p><h2>{ESC(page["title"])}</h2><div class="blocks">{"".join(blocks)}</div></article>')
    downloads = [('assignment.pdf', 'Скачать задание практики (PDF)'), ('guide.pdf', 'Скачать методичку и образец (PDF)'), ('report-template.md', 'Скачать общий шаблон отчёта (Markdown)')]
    links = ''.join(f'<a class="button" href="downloads/{quote(name)}">{ESC(label)}</a>' for name, label in downloads)
    assignment_index = ''
    if section == 'assignment':
        links += '<a class="button" href="areas.html#variant-01">Открыть индивидуальные задания</a>'
        variants = ''.join(f'<a class="button" href="areas.html#variant-{area["id"]:02}">Открыть задание варианта {area["id"]:02}: {ESC(area["subject"])}</a>' for area in data['areas'])
        assignment_index = f'<article class="lesson" id="variant-index"><h2>Ссылки на индивидуальные задания</h2><div class="downloads">{variants}</div></article>'
    state = 'Учебный комплект' if release else 'Черновик — проверки выпуска не завершены'
    badge = 'УП' if meta['practice_type'] == 'up' else 'ПП'
    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{ESC(titles[section])}</title><link rel="icon" href="assets/favicon.svg"><link rel="stylesheet" href="assets/style.css"></head><body><a class="skip" href="#main">Перейти к содержанию</a><header class="shell top"><a class="brand" href="index.html"><span class="emblem">{badge}</span><span><strong>Практика / Методические материалы</strong><small>{ESC(meta['subtitle'])}</small></span></a><span class="version">Версия {ESC(meta['version'])}</span></header><div class="shell"><nav>{nav}</nav><main id="main"><section class="hero"><p class="eyebrow">Учебный маршрут / {ESC(meta.get('academic_year') or 'год уточняется')}</p><h1>{ESC(titles[section])}</h1><p>{ESC(meta['subtitle'])}</p><span class="badge">{state}</span></section><div class="downloads">{links}</div>{assignment_index}{''.join(body)}</main><footer><span>{ESC(meta['module'])}</span><span>Единый учебный комплект</span></footer></div></body></html>'''


def report_markdown(data):
    font = "font-family:'Times New Roman';color:#000;"
    body = font + 'font-size:14pt;text-align:justify;line-height:1.5;text-indent:1.25cm;'
    heading = font + 'font-size:14pt;text-align:justify;line-height:1.5;page-break-after:avoid;'
    caption_style = font + 'font-size:12pt;text-align:center;line-height:1;text-indent:0;'
    def paragraph(text):
        return f'<p style="{body}">{ESC(text).replace(chr(10), "<br/>")}</p>'
    lines = [f'<div lang="ru" style="{body}">', '',
             f'<h1 style="{font}font-size:16pt;text-align:center;line-height:1.5;page-break-after:avoid;">{ESC(("Отчёт — " + data["meta"]["title"]).upper())}</h1>', '']
    fields = ['ФИО', 'Группа', 'Вариант', 'Предметная область', 'Дата', 'Версия программы']
    if data['report'].get('project_work', True):
        fields.append('Ссылка на репозиторий проекта')
    for field in fields:
        lines += [paragraph(field + ': ____________________'), '']
    number = 0
    for section in data['report']['sections']:
        lines += [f'<h2 style="{heading}">{ESC(section["title"])}</h2>', '',
                  paragraph(section['prompt']), '', paragraph('Заполните по результатам своей работы.'), '']
        for caption in section.get('screenshots', []):
            number += 1
            lines += ['<div style="page-break-inside:avoid;break-inside:avoid;">',
                      '<table width="100%" border="1" cellspacing="0" cellpadding="0" style="border-collapse:collapse;width:100%;page-break-after:avoid;">',
                      '<tr>', f'<td height="220" style="border:1px solid #000;height:220px;text-align:center;vertical-align:middle;{font}font-size:12pt;line-height:1;text-indent:0;">Вставьте скриншот</td>',
                      '</tr>', '</table>',
                      f'<p style="{caption_style}page-break-before:avoid;">Рисунок {number} — {ESC(caption)}</p>',
                      '</div>', '']
    lines += ['</div>', '']
    return '\n'.join(lines)


def fonts():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    candidates = [('C:/Windows/Fonts', 'arial.ttf', 'arialbd.ttf', 'consola.ttf'),
                  ('/usr/share/fonts/truetype/dejavu', 'DejaVuSans.ttf', 'DejaVuSans-Bold.ttf', 'DejaVuSansMono.ttf'),
                  ('/System/Library/Fonts/Supplemental', 'Arial.ttf', 'Arial Bold.ttf', 'Courier New.ttf')]
    for folder, *names in candidates:
        if all((Path(folder)/name).is_file() for name in names):
            for alias, name in zip(('Body', 'Bold', 'Mono'), names):
                pdfmetrics.registerFont(TTFont(alias, str(Path(folder)/name)))
            return
    raise ValueError('Required fonts unavailable: Arial/Consolas or DejaVu')


def pdf(root, target, data, section, release=False):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image, KeepTogether, Table, TableStyle
    fonts()
    width, height = 841.89, 595.28
    available = width - 88
    body = ParagraphStyle('Body', fontName='Body', fontSize=12, leading=17, spaceAfter=10)
    heading = ParagraphStyle('Heading', fontName='Bold', fontSize=15, leading=20, spaceAfter=8, keepWithNext=True)
    title = ParagraphStyle('Title', fontName='Bold', fontSize=23, leading=29, spaceAfter=20, keepWithNext=True)
    mono = ParagraphStyle('Code', fontName='Mono', fontSize=9, leading=12, spaceAfter=0, splitLongWords=True)
    caption = ParagraphStyle('Caption', parent=body, fontSize=10, leading=14)
    download_heading = ParagraphStyle('DownloadHeading', parent=heading, fontSize=11, leading=14, spaceAfter=4)
    download_text = ParagraphStyle('DownloadText', parent=body, fontSize=9, leading=12, spaceAfter=3)
    story = []
    meta = data['meta']
    label = 'Список предметных областей' if section == 'assignment' else 'Инструкция и образец'
    cover = ParagraphStyle('Cover', parent=title, textColor=colors.white, fontSize=28, leading=34)
    banner = Table([[Paragraph(ESC(label), cover)]], colWidths=[available-12])
    banner.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#1c1c1c')),('LEFTPADDING',(0,0),(-1,-1),22),('TOPPADDING',(0,0),(-1,-1),24),('BOTTOMPADDING',(0,0),(-1,-1),24)]))
    story += [banner, Spacer(1, 22), Paragraph(ESC(meta['title']), title)]
    for text in [meta['subtitle'], meta['specialty'], meta['module'], meta['organization']]:
        story.append(Paragraph(ESC(text), body))
    if not release:
        story.append(Paragraph('Черновик — проверки выпуска не завершены', body))
    specs = data['assignment'] + data['areas'] if section == 'assignment' else data['guide']
    if section == 'guide':
        demo = data['demonstration']
        story += [Paragraph(ESC(demo['title']), heading), Paragraph(ESC(demo['description']), body)]
    def append_downloads(page):
        if not page.get('downloads'):
            return
        group = [Paragraph('Материалы для работы', download_heading)]
        for name in page['downloads']:
            url = ESC(download_url(data, name, release))
            group.append(Paragraph(f'<link href="{url}" color="#b01010"><u>{ESC(area_download_label(data, name, page))}</u></link><br/>{ESC(download_description(name, data))}', download_text))
        story.append(KeepTogether(group))
    for page in specs:
        story += [PageBreak(), Paragraph(ESC(page['title']), title)]
        # Keep source links with the page title. Placing them after long content
        # stranded the links on a separate page from the variant they serve.
        append_downloads(page)
        # Preserve the reference's two-column teaching layout when full blocks fit.
        if all(b['kind'] in {'text', 'note'} and not b.get('links') for b in page['blocks']) and len(page['blocks']) > 1:
            col_width = (available-40)/2
            groups = [[Paragraph(ESC(b['title']), heading), Paragraph(ESC(b['text']).replace('\n','<br/>'), body)] for b in page['blocks']]
            heights = [sum(f.wrap(col_width-12, 2000)[1] + f.getSpaceAfter() for f in group) for group in groups]
            cut = min(range(1,len(groups)), key=lambda n: max(sum(heights[:n]),sum(heights[n:])))
            if max(sum(heights[:cut]),sum(heights[cut:])) < 380:
                columns = [[f for group in groups[:cut] for f in group], [f for group in groups[cut:] for f in group]]
                table = Table([[columns[0], '', columns[1]]], colWidths=[col_width,28,col_width])
                table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0)]))
                story.append(table)
                continue
        for block in page['blocks']:
            if block['kind'] == 'image':
                image = Image(str(source_path(root, block['path'])))
                image._restrictSize(available - 12, 310)
                story.append(KeepTogether([Paragraph(ESC(block['title']), heading), image, Spacer(1, 8), Paragraph(ESC(block['text']), caption)]))
            elif block['kind'] == 'code':
                story.append(Paragraph(ESC(block['title']), heading))
                # One flowable per source line: arbitrary length and multiple blocks
                # paginate naturally, without dropping subsequent explanations.
                for line in block['text'].split('\n'):
                    text = ESC(line.expandtabs(4)).replace(' ', '&#160;') or '&#160;'
                    story.append(Paragraph(text, mono))
                story.append(Spacer(1, 12))
            else:
                story.append(Paragraph(ESC(block['title']), heading))
                story.append(Paragraph(ESC(block['text']).replace('\n', '<br/>'), body))
                for link in block.get('links', []):
                    story.append(Paragraph(f'<link href="{ESC(link["url"], quote=True)}" color="#b01010"><u>{ESC(link["label"])}</u></link> — {ESC(link["description"])}', body))
    def frame(c, doc):
        c.saveState()
        c.setFillColor(colors.HexColor('#ed131c'))
        c.rect(44, height-30, 28, 5, fill=1, stroke=0)
        c.setFont('Body', 8)
        c.setFillColor(colors.HexColor('#606773'))
        c.drawString(44, 22, label)
        c.drawRightString(width-44, 22, str(doc.page))
        c.restoreState()
    doc = SimpleDocTemplate(str(target), pagesize=(width, height), leftMargin=44, rightMargin=44,
                            topMargin=48, bottomMargin=44, title=f'{label} — {meta["title"]}', author=meta['organization'])
    doc.build(story, onFirstPage=frame, onLaterPages=frame)
