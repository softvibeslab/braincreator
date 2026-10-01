"""Source-backed resource cards; never accept URLs supplied by the chat model.

Optional data/resources.json is a private export and must not be committed.
Links are attributed to their source, not advertised as live-access verified.
"""
import html
import ipaddress
import json
import re
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit


YOUTUBE_HOSTS = {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be', 'www.youtu.be'}
VIDEO_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')
TIME = re.compile(r'(?<!\d)(\d{1,2}:\d{2}:\d{2})(?!\d)')
SECRET_KEYS = re.compile(r'token|signature|secret|credential|password|authorization|api.?key|x-amz|x-goog', re.I)
PROMOTIONAL = re.compile(r'oferta comercial|contenido promocional|ver la oferta|haz clic.*oferta|vsl-org|vsl[_-]org', re.I)


def safe_url(value):
    """Only credential-free public HTTPS links; exclude signed stream URLs."""
    if not isinstance(value, str) or len(value) > 2048:
        return None
    value = html.unescape(value.strip()).rstrip('.,;')
    if any(ord(c) < 33 for c in value) or '\\' in value:
        return None
    try:
        p = urlsplit(value)
        host = (p.hostname or '').lower().rstrip('.')
        if p.scheme != 'https' or not host or p.username or p.password or p.port not in (None, 443):
            return None
        if '.' not in host or host.endswith(('.local', '.localhost', '.internal', '.test', '.invalid')):
            return None
        try:
            ipaddress.ip_address(host)
            return None  # Course resources should use a public named host.
        except ValueError:
            pass
        if host in {'localhost', 'stream.mux.com'} or p.path.lower().endswith(('.m3u8', '.m3u')):
            return None
        if any(SECRET_KEYS.search(k) for k, _ in parse_qsl(p.query, keep_blank_values=True)):
            return None
        return urlunsplit(('https', host, p.path or '/', p.query, p.fragment))
    except (ValueError, UnicodeError):
        return None


def youtube_url(url):
    """Canonicalise a real video URL, never a channel or search result."""
    url = safe_url(url)
    if not url:
        return None
    p = urlsplit(url)
    if p.hostname not in YOUTUBE_HOSTS:
        return None
    pieces = p.path.strip('/').split('/')
    if p.hostname in {'youtu.be', 'www.youtu.be'}:
        video = pieces[0] if len(pieces) == 1 else ''
    elif p.path == '/watch':
        video = parse_qs(p.query).get('v', [''])[0]
    elif len(pieces) == 2 and pieces[0] in {'embed', 'shorts', 'live'}:
        video = pieces[1]
    else:
        video = ''
    return 'https://www.youtube.com/watch?v=' + video if VIDEO_ID.fullmatch(video) else None


def clean_text(value, limit=300):
    value = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', str(value or ''))
    value = re.sub(r'[*_`#>]', '', value)
    value = re.sub(r'\s+', ' ', html.unescape(value)).strip(' -•')
    return value if len(value) <= limit else value[:limit - 1].rsplit(' ', 1)[0] + '…'


def source_resource(url, title='', context='', source='node-note', label='Ficha del nodo'):
    """Classify an evidenced URL, excluding promotional calls to action."""
    url = safe_url(url)
    if not url or PROMOTIONAL.search(url + ' ' + title + ' ' + context):
        return None
    p = urlsplit(url)
    host = p.hostname
    # This commercial sales destination is not an educational resource.
    if host in {'laboratoriodeagencias.com', 'www.laboratoriodeagencias.com'}:
        return None
    if host in {'skool.com', 'www.skool.com'}:
        if '/classroom/' not in p.path:
            return None
        kind, fallback = 'skool', 'Abrir lección en Skool'
    elif host in YOUTUBE_HOSTS:
        url = youtube_url(url)
        if not url:
            return None
        kind, fallback = 'youtube', 'Ver vídeo en YouTube'
    elif ((host == 'docs.google.com' and re.match(r'^/(document|spreadsheets|presentation|forms)/d/', p.path))
          or (host == 'drive.google.com' and re.match(r'^/file/d/', p.path))
          or re.search(r'\.(pdf|docx?|xlsx?|pptx?|csv|odt|ods)$', p.path, re.I)):
        kind, fallback = 'template', 'Abrir documento original'
    else:
        kind, fallback = 'link', 'Abrir recurso original'
    clean_title = clean_text(title, 140)
    if not clean_title or clean_title.lower() in {'esta', 'aquí', 'aqui', 'link', 'enlace', 'skool', 'video', 'vídeo'}:
        clean_title = fallback
    access = 'Puede requerir acceso a la comunidad de Skool.' if kind == 'skool' else 'Enlace de la fuente; disponibilidad no comprobada.'
    return {'type': kind, 'title': clean_title, 'url': url, 'origin': 'original',
            'provenance': {'source': source, 'label': clean_text(label, 160)}, 'access_note': access}


def resources_from_markdown(markdown, source='node-note', label='Ficha del nodo'):
    found = []
    for line in markdown.splitlines():
        if PROMOTIONAL.search(line):
            continue
        occupied = []
        for match in re.finditer(r'\[([^\]\n]+)\]\((https://[^\s)]+)\)', line):
            item = source_resource(match[2], match[1], line, source, label)
            if item:
                found.append(item)
            occupied.append(match.span())
        for match in re.finditer(r'https://[^\s<>\]"`]+', line):
            if any(start <= match.start() < end for start, end in occupied):
                continue
            item = source_resource(match[0].rstrip(')'), '', line, source, label)
            if item:
                found.append(item)
    return deduplicate(found)


def deduplicate(resources):
    output, seen = [], set()
    for item in resources:
        # Ignore tracking parameters when identifying duplicate resource links.
        p = urlsplit(item['url'])
        key = urlunsplit((p.scheme, p.netloc.removeprefix('www.'), p.path.rstrip('/'),
                         urlencode(sorted((k, v) for k, v in parse_qsl(p.query) if not k.startswith('utm_') and k not in {'usp', 'si'})), ''))
        if key not in seen:
            seen.add(key)
            output.append(item)
    return output


def section(markdown, heading):
    match = re.search(r'^##\s+' + heading + r'[^\n]*\n(.*?)(?=^##\s|\Z)', markdown, re.M | re.S | re.I)
    return match[1].strip() if match else ''


def seconds(timestamp):
    if not TIME.fullmatch(timestamp):
        return None
    hours, minutes, secs = map(int, timestamp.split(':'))
    return hours * 3600 + minutes * 60 + secs if minutes < 60 and secs < 60 else None


class ResourceCatalogue:
    def __init__(self, library):
        self.library = library
        self.extra = {}
        path = (library.root / 'data/resources.json').resolve()
        if path.is_relative_to(library.root) and path.is_file():
            raw = json.loads(path.read_text())
            if isinstance(raw, dict):
                self.extra = raw.get('nodes', raw)
        self.cache = {}

    def get(self, node_id):
        if node_id not in self.library.nodes:
            return None
        if node_id in self.cache:
            return self.cache[node_id]
        node = self.library.nodes[node_id]
        markdown = self.library.read(node['hostedNote']) if node.get('hostedNote') else ''
        extra = self.extra.get(node_id, {})
        if not isinstance(extra, dict):
            extra = {}
        resources = resources_from_markdown(markdown)
        for raw in extra.get('resources', []):
            if not isinstance(raw, dict):
                continue
            provenance = raw.get('provenance') or {}
            item = source_resource(raw.get('url'), raw.get('title', ''), source='source-export',
                                   label=provenance.get('label', 'Página original de la lección'))
            if item:
                resources.append(item)
        resources = deduplicate(resources)
        summary_lines = [clean_text(line, 300) for line in section(markdown, r'Resumen').splitlines() if line.strip()]
        summary_lines = [line for line in summary_lines if line]
        highlights = summary_lines[:3]
        summary = clean_text(' '.join(summary_lines[:2]) or node.get('summary', ''), 440)
        timeline = []
        for line in section(markdown, r'L[ií]nea de tiempo').splitlines():
            cells = [part.strip() for part in line.strip().strip('|').split('|')]
            if len(cells) >= 3 and seconds(cells[0]) is not None:
                timeline.append({'time': cells[0], 'label': clean_text(cells[-1], 150)})
        if not timeline and node.get('sourceLocation') and seconds(node['sourceLocation']) is not None:
            timeline.append({'time': node['sourceLocation'], 'label': 'Fragmento de la fuente'})
        videos = [item['url'] for item in resources if item['type'] == 'youtube']
        assigned = youtube_url(extra.get('video_url', ''))
        # Only the exporter may assign a lesson video to timestamps. Merely
        # mentioning a YouTube link in a note is not evidence of that mapping.
        if assigned in videos:
            duration = extra.get('duration_seconds')
            for point in timeline:
                at = seconds(point['time'])
                if isinstance(duration, (int, float)) and at >= duration:
                    continue
                point['url'] = assigned + '&t=' + str(at) + 's'
        notice = ''
        if not resources:
            notice = 'Esta ficha no contiene recursos externos enlazados.'
        elif not any(item['type'] == 'template' for item in resources):
            notice = 'No hay una plantilla descargable enlazada en esta ficha.'
        result = {'node_id': node_id, 'title': node['title'], 'summary': summary,
                  'highlights': highlights, 'resources': resources, 'timestamps': timeline[:8], 'notice': notice}
        self.cache[node_id] = result
        return result
