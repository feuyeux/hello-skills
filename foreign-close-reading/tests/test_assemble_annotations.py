#!/usr/bin/env python3
"""assemble_annotations.py：实例只写讲解字段，text/para/ch 由切片注入。

Run:  python3 -m unittest discover -s tests
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, '..', 'scripts', 'assemble_annotations.py')

SLICE = {
    'lang': 'fr', 'total': 3,
    'chapters': [{'index': 1, 'title': 'I', 'start': 1}],
    'sentences': [
        {'id': 1, 'text': 'Aujourd’hui, maman est morte.', 'para': 1, 'ch': 1},
        {'id': 2, 'text': 'Peut-être qu’hier, oui.', 'para': 2, 'ch': 1},
        {'id': 3, 'text': 'C’est fini.', 'para': 2, 'ch': 1},
    ],
}


def run(*args, **kw):
    p = subprocess.run([sys.executable, SCRIPT] + list(args),
                       capture_output=True, text=True, **kw)
    return p.returncode, p.stdout + p.stderr


class AssembleAnnotations(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix='fcr-asm-')
        self.addCleanup(__import__('shutil').rmtree, self.d, ignore_errors=True)
        self.slice = os.path.join(self.d, 'sentences-1.json')
        with open(self.slice, 'w', encoding='utf-8') as f:
            json.dump(SLICE, f, ensure_ascii=False)

    def batch(self, name, items):
        path = os.path.join(self.d, name)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False)
        return path

    def out(self):
        return os.path.join(self.d, 'data-1.json')

    def read_out(self):
        with open(self.out(), encoding='utf-8') as f:
            return json.load(f)

    def assemble(self, *batches):
        return run('--sentences', self.slice, '--annots',
                   ' '.join(batches) if len(batches) == 1 else self.d + '/annots-1.b*.json',
                   '--out', self.out(), '--title', '局外人', '--lang', 'fr')

    def test_injects_text_para_ch_verbatim_from_slice(self):
        # 批次里即使混进了 text/para，也以切片为准——原文不可能被改坏
        code, log = self.assemble(self.batch(
            'annots-1.b1.json',
            [{'id': 1, 'translation': '今天，妈妈死了。',
              'words': [{'w': 'aujourd’hui', 'm': '今天'}],
              'text': '手打的正文', 'para': 99},
             {'id': 2, 'translation': '也许昨天，是的。'},
             {'id': 3, 'translation': '结束了。'}]))
        self.assertEqual(code, 0, log)
        d = self.read_out()
        self.assertEqual([s['text'] for s in d['sentences']],
                         [s['text'] for s in SLICE['sentences']])
        self.assertEqual([s['para'] for s in d['sentences']], [1, 2, 2])
        self.assertEqual([s['ch'] for s in d['sentences']], [1, 1, 1])
        self.assertEqual(d['chapters'], SLICE['chapters'])
        self.assertEqual(d['lang'], 'fr')

    def test_later_batch_file_overrides_earlier_for_same_id(self):
        # 断点续跑：同一 id 以文件名靠后的批次为准
        code, log = self.assemble(
            self.batch('annots-1.b1.json',
                       [{'id': 1, 'translation': '占位译文'},
                        {'id': 2, 'translation': '也许昨天。'},
                        {'id': 3, 'translation': '结束了。'}]),
            self.batch('annots-1.b2.json',
                       [{'id': 1, 'translation': '今天，妈妈死了。',
                         'native': [{'t': '听感', 'd': '极简冷峻的第一句。'}]}]))
        self.assertEqual(code, 0, log)
        d = self.read_out()
        self.assertEqual(d['sentences'][0]['translation'], '今天，妈妈死了。')
        self.assertEqual(d['sentences'][0]['native'][0]['t'], '听感')

    def test_unknown_or_untranslated_ids_fail_loudly(self):
        code, log = self.assemble(
            self.batch('annots-1.b1.json', [{'id': 99, 'translation': '?'},
                                            {'id': 2, 'translation': 'x.'}]))
        self.assertNotEqual(code, 0)
        self.assertIn('unknown id', log)
        code, log = self.assemble(
            self.batch('annots-1.b2.json', [{'id': 1, 'words': []},
                                            {'id': 2, 'translation': 'x.'}]))
        self.assertNotEqual(code, 0)
        self.assertIn('no translation', log)

    def test_missing_coverage_lists_the_gap_and_writes_nothing(self):
        code, log = self.assemble(self.batch(
            'annots-1.b1.json', [{'id': 1, 'translation': 'a.'}]))
        self.assertNotEqual(code, 0)
        self.assertIn('unannotated', log)
        self.assertIn('2', log)
        self.assertFalse(os.path.exists(self.out()))


if __name__ == '__main__':
    unittest.main()
