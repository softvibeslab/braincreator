#!/usr/bin/env python3
"""Export approved source links to PRIVATE hosting/data/resources.json.

Usage: python3 scripts/export-resources.py --source /path/to/elite-digital --hosting /path/to/hosting
Reads source metadata and pages without modifying them. Never exports signed
streams, cookies, course text, or the promotional sales call to action.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'services/skool-guide'))
from resources import deduplicate, resources_from_markdown, source_resource, youtube_url


def read_json(path, default):
    return json.loads(path.read_text()) if path.is_file() else default


def export(source, hosting):
    source, hosting = Path(source).resolve(), Path(hosting).resolve()
    graph = read_json(hosting / 'data/graph.json', {})
    if not graph.get('nodes'):
        raise ValueError('Hosting export is missing data/graph.json')
    index = read_json(source / 'index.json', {})
    catalogue = read_json(source / '_kb/catalogo.json', [])
    durations = {row['stem']: row.get('duration_s') for row in catalogue}
    videos = {str(Path(row['out']).with_suffix('.md')): row for row in read_json(source / 'videos.json', []) if row.get('out')}
    lessons = {}
    for course in index.get('courses', []):
        for lesson in course.get('lessons', []):
            relative = lesson.get('file')
            if not relative:
                continue
            path = (source / relative).resolve()
            if not path.is_relative_to(source):
                raise ValueError('Lesson source path escapes source directory')
            stem = str(Path(relative).with_suffix('')).replace('/', '__')
            items = []
            original = source_resource(lesson.get('url'), 'Abrir lección en Skool', source='source-export', label='index.json: página original de la lección')
            if original:
                items.append(original)
            video = lesson.get('video') or videos.get(relative) or {}
            actual_video = youtube_url(video.get('url', '')) if video.get('host') == 'youtube' else None
            if video.get('host') in {'youtube', 'loom'}:
                item = source_resource(video.get('url'), 'Ver vídeo en YouTube' if actual_video else 'Ver vídeo original en Loom',
                                       source='source-export', label='index.json / videos.json: vídeo de esta lección')
                if item:
                    items.append(item)
            content = lesson.get('content_md', '')
            if path.is_file():
                content += '\n' + path.read_text()
            items.extend(resources_from_markdown(content, source='source-export', label=relative + ': enlace en la página original'))
            for item in lesson.get('resources', []):
                if isinstance(item, dict):
                    link = source_resource(item.get('url') or item.get('href'), item.get('title') or item.get('name') or '',
                                           source='source-export', label='index.json: recursos de la lección')
                    if link:
                        items.append(link)
            lessons[stem] = {'resources': deduplicate(items), 'duration_seconds': durations.get(stem)}
            if actual_video:
                lessons[stem]['video_url'] = actual_video
    nodes = {}
    for node in graph['nodes']:
        gid = node.get('graphifyId', '')
        original = node.get('originalSource', '')
        if gid.startswith('lesson_'):
            stem = gid.removeprefix('lesson_')
        elif original.startswith('_transcripts/') and original.endswith('.md'):
            stem = Path(original).stem
        else:
            continue
        if stem in lessons:
            nodes[node['id']] = lessons[stem]
    destination = hosting / 'data/resources.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps({'schema_version': 1, 'nodes': nodes}, ensure_ascii=False, indent=2) + '\n')
    lesson_ids = [n['id'] for n in graph['nodes'] if n.get('graphifyId', '').startswith('lesson_')]
    counts = Counter(item['type'] for node_id in lesson_ids for item in nodes.get(node_id, {}).get('resources', []))
    report = {'lessons': len(lesson_ids), 'lessons_enriched': sum(n in nodes for n in lesson_ids),
              'nodes_enriched': len(nodes), 'lesson_resources': dict(counts), 'output': str(destination)}
    print(json.dumps(report, ensure_ascii=False))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--hosting', required=True, type=Path)
    args = parser.parse_args()
    export(args.source, args.hosting)
