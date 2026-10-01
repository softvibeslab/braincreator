import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services/skool-guide'))
from resources import ResourceCatalogue, resources_from_markdown, safe_url, source_resource, youtube_url
from retrieval import Library


class ResourceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'data').mkdir()
        self.markdown = '''# Attract qualified leads
## Resumen en 5 líneas
Define the audience before choosing a channel.
Ask one useful qualification question.
Measure the result before adding friction.
## Fuentes
[Skool](https://www.skool.com/example/classroom/abc?md=lesson)
[Skool duplicate](https://www.skool.com/example/classroom/abc?md=lesson&utm_source=chat)
[Offer](https://laboratoriodeagencias.com/vsl-org)
[Unsafe](javascript:alert(1))
## Línea de tiempo (por bloques)
| Desde | Hasta | Qué ocurre |
| 0:00:15 | 0:01:00 | Define the audience |
| 0:01:00 | 0:02:00 | Ask a useful question |
'''
        (self.root / 'data/n.json').write_text(json.dumps({'markdown': self.markdown}))
        self.node = {'id': 'm:1', 'title': 'Attract leads', 'source': 'marketing', 'kind': 'video', 'hostedNote': 'data/n.json',
                     'graphifyId': 'lesson_course__lesson', 'originalSource': '_transcripts/course__lesson.md'}
        (self.root / 'data/graph.json').write_text(json.dumps({'nodes': [self.node], 'links': []}))

    def tearDown(self):
        self.temp.cleanup()

    def test_safe_url_rejects_credentials_local_and_signed(self):
        for url in ('file:///etc/passwd', 'javascript:alert(1)', 'http://example.com/a', 'https://user:pass@example.com/a',
                    'https://127.0.0.1/a', 'https://localhost/a', 'https://internal.local/a',
                    'https://example.com/a?token=secret', 'https://stream.mux.com/video.m3u8?token=secret',
                    'https://example.com\\@evil.com/a', 'https://example.com/a\nCookie:secret'):
            self.assertIsNone(safe_url(url), url)
        self.assertEqual(safe_url('https://docs.google.com/document/d/example/edit'), 'https://docs.google.com/document/d/example/edit')

    def test_youtube_only_actual_video_hosts_and_ids(self):
        self.assertEqual(youtube_url('https://youtu.be/abcdefghijk?si=test'), 'https://www.youtube.com/watch?v=abcdefghijk')
        for url in ('https://youtube.com.evil.com/watch?v=abcdefghijk', 'https://www.youtube.com/results?search_query=leads', 'https://youtu.be/short'):
            self.assertIsNone(youtube_url(url))

    def test_source_links_and_deduplication(self):
        links = resources_from_markdown(self.markdown)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]['type'], 'skool')
        self.assertEqual(links[0]['origin'], 'original')
        self.assertIsNone(source_resource('https://example.com/sales', context='Haz clic para ver la oferta'))

    def test_unknown_node(self):
        self.assertIsNone(ResourceCatalogue(Library(self.root)).get('invented'))

    def test_summary_skool_and_timestamps_without_invented_video(self):
        item = ResourceCatalogue(Library(self.root)).get('m:1')
        self.assertEqual(len(item['highlights']), 3)
        self.assertEqual(item['resources'][0]['type'], 'skool')
        self.assertEqual(item['timestamps'][0]['time'], '0:00:15')
        self.assertNotIn('url', item['timestamps'][0])
        self.assertIn('No hay una plantilla', item['notice'])

    def test_enriched_video_timestamps_and_document(self):
        data = {'nodes': {'m:1': {'video_url': 'https://youtu.be/abcdefghijk', 'duration_seconds': 60, 'resources': [
            {'url': 'https://youtu.be/abcdefghijk', 'title': 'Video'},
            {'url': 'https://docs.google.com/document/d/example/edit', 'title': 'Planning template'},
            {'url': 'https://bad.local/secret', 'title': 'Bad'},
        ]}}}
        (self.root / 'data/resources.json').write_text(json.dumps(data))
        item = ResourceCatalogue(Library(self.root)).get('m:1')
        self.assertEqual([x['type'] for x in item['resources']], ['skool', 'youtube', 'template'])
        self.assertEqual(item['timestamps'][0]['url'], 'https://www.youtube.com/watch?v=abcdefghijk&t=15s')
        self.assertNotIn('url', item['timestamps'][1])
        self.assertEqual(item['notice'], '')

    def test_export_uses_matching_lesson_and_keeps_private_data_out(self):
        source = self.root / 'source'
        (source / 'course').mkdir(parents=True)
        (source / '_kb').mkdir()
        (source / '_kb/catalogo.json').write_text(json.dumps([{'stem': 'course__lesson', 'duration_s': 120}]))
        (source / 'course/lesson.md').write_text('[Template](https://docs.google.com/document/d/example/edit)')
        (source / 'index.json').write_text(json.dumps({'courses': [{'lessons': [{'file': 'course/lesson.md',
            'url': 'https://www.skool.com/example/classroom/abc?md=lesson',
            'video': {'host': 'youtube', 'url': 'https://youtu.be/abcdefghijk'},
            'content_md': '[Promo](https://laboratoriodeagencias.com/vsl-org)'}]}]}))
        spec = importlib.util.spec_from_file_location('export_resources', ROOT / 'scripts/export-resources.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        report = module.export(source, self.root)
        self.assertEqual(report['lessons_enriched'], 1)
        self.assertEqual(report['lesson_resources'], {'skool': 1, 'youtube': 1, 'template': 1})
        item = ResourceCatalogue(Library(self.root)).get('m:1')
        self.assertTrue(any(x['type'] == 'youtube' for x in item['resources']))


if __name__ == '__main__':
    unittest.main()
