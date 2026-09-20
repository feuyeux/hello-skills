#!/usr/bin/env python3
"""Concurrency pipeline: --plan slices cover everything without overlap,
multi-file --merge folds chunks in order, meta.json can serve as --data.

Run:  python3 -m unittest discover -s tests
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, '..', 'scripts')
SPLIT = os.path.join(SCRIPTS, 'split_sentences.py')
BUILD = os.path.join(SCRIPTS, 'build_reader.py')


def run(script, *args, **kw):
    p = subprocess.run([sys.executable, script] + list(args),
                       capture_output=True, text=True, **kw)
    return p.returncode, p.stdout + p.stderr


def write_json(obj, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False)


def make_book(ids, prefix='c'):
    return {'sentences': [{'id': i, 'text': '%s%d.' % (prefix, i), 'para': 1,
                           'translation': 't%d' % i} for i in ids]}


class Plan(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix='fcr-plan-')
        fd, self.txt = tempfile.mkstemp(suffix='.txt')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(' '.join('Sentence number %d goes here.' % i
                             for i in range(1, 11)))
            f.write('\n\nAnother paragraph with one more sentence here.')

    def tearDown(self):
        import shutil
        os.unlink(self.txt)
        shutil.rmtree(self.d, ignore_errors=True)

    def plan(self, *extra):
        # --plan 的切片文件落在运行目录，用独立 cwd 隔离
        return run(SPLIT, self.txt, '--plan', '3', *extra, cwd=self.d)

    def test_plan_writes_balanced_nonoverlapping_slices(self):
        code, out = self.plan()
        self.assertEqual(code, 0, out)
        self.assertIn('total 11 sentences -> 3 slice file(s)', out)
        # 11 = 4 + 4 + 3，起止不重叠、不留缝
        self.assertIn('sentences-1.json: id 1-4', out)
        self.assertIn('sentences-2.json: id 5-8', out)
        self.assertIn('sentences-3.json: id 9-11', out)
        ids = []
        for k in (1, 2, 3):
            chunk = json.load(open('%s/sentences-%d.json' % (self.d, k),
                                   encoding='utf-8'))
            self.assertEqual(chunk['total'], 11)   # 每个切片都带全书 total
            self.assertIn('sentences', chunk)
            ids.extend(s['id'] for s in chunk['sentences'])
        self.assertEqual(sorted(ids), list(range(1, 12)))

    def test_plan_slices_match_a_full_split(self):
        """落盘切片拼起来等于全文一次切分（实例不再重切全文，id 由这里固定）。"""
        code, out = self.plan()
        self.assertEqual(code, 0, out)
        code, out = run(SPLIT, self.txt, '--out', self.d + '/full.json')
        self.assertEqual(code, 0, out)
        full = json.load(open(self.d + '/full.json', encoding='utf-8'))
        chunks = []
        for k in (1, 2, 3):
            chunk = json.load(open('%s/sentences-%d.json' % (self.d, k),
                                   encoding='utf-8'))
            chunks.extend(chunk['sentences'])
        self.assertEqual(chunks, full['sentences'])

    def test_plan_carries_language_flags(self):
        code, out = self.plan('--lang', 'ru')
        self.assertEqual(code, 0, out)
        chunk = json.load(open(self.d + '/sentences-1.json', encoding='utf-8'))
        self.assertEqual(chunk['lang'], 'ru')
        self.assertEqual(chunk['layout'], 'cyrl')

    def test_plan_prints_merge_command_with_total(self):
        code, out = self.plan()
        self.assertEqual(code, 0, out)
        # 合并命令带 --total，阅读器据此显示覆盖进度
        self.assertIn('--data data-1.json --merge data-2.json data-3.json '
                      '--total 11', out)
        # 合并命令指向 build_reader.py（不是 split_sentences 自己），可直接执行
        self.assertIn(sys.executable + ' ' + os.path.abspath(BUILD)
                      + ' --data data-1.json', out)

    def test_plan_single_chunk_has_no_merge_flag(self):
        code, out = run(SPLIT, self.txt, '--plan', '1', cwd=self.d)
        self.assertEqual(code, 0, out)
        self.assertIn('--data data-1.json --total 11', out)
        self.assertNotIn('--merge', out)


class Merge(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix='fcr-merge-')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.d, ignore_errors=True)

    def path(self, name):
        return os.path.join(self.d, name)

    def build(self, *args):
        return run(BUILD, *args)

    def test_chunks_merge_in_any_listing_order(self):
        # 三个块乱序列出，产物仍按 id 升序包含全部句子
        write_json({'title': '书', 'lang': 'en',
                    **make_book([1, 2, 3])}, self.path('data-1.json'))
        write_json({**make_book([4, 5, 6])}, self.path('data-2.json'))
        write_json({**make_book([7, 8, 9])}, self.path('data-3.json'))
        code, out = self.build('--data', self.path('data-1.json'),
                               '--merge', self.path('data-3.json'),
                               self.path('data-2.json'),
                               '--out', self.path('reader.html'))
        self.assertEqual(code, 0, out)
        self.assertIn('9 sentences', out)
        html = open(self.path('reader.html'), encoding='utf-8').read()
        for i in range(1, 10):
            self.assertIn('c%d.' % i, html)

    def test_meta_json_as_data(self):
        # 只含 title/lang 的 meta.json 当 --data：合并发生在校验之前，可行
        write_json({'title': '书名', 'lang': 'ru'}, self.path('meta.json'))
        write_json({**make_book([1, 2])}, self.path('data-1.json'))
        write_json({**make_book([3, 4])}, self.path('data-2.json'))
        code, out = self.build('--data', self.path('meta.json'),
                               '--merge', self.path('data-1.json'),
                               self.path('data-2.json'),
                               '--out', self.path('reader.html'))
        self.assertEqual(code, 0, out)
        self.assertIn('4 sentences', out)
        html = open(self.path('reader.html'), encoding='utf-8').read()
        self.assertIn('data-lang="cyrl"', html)

    def test_data_wins_over_merge_on_conflict(self):
        # 重叠切片：--data 覆盖 --merge 里的同 id 句子
        write_json({'title': '书', **make_book([1], 'data')}, self.path('data-1.json'))
        write_json({**make_book([1], 'merged')}, self.path('old.json'))
        code, out = self.build('--data', self.path('data-1.json'),
                               '--merge', self.path('old.json'),
                               '--out', self.path('reader.html'))
        self.assertEqual(code, 0, out)
        html = open(self.path('reader.html'), encoding='utf-8').read()
        self.assertIn('data1.', html)
        self.assertNotIn('merged1.', html)

    def test_later_merge_file_wins_over_earlier(self):
        # --data 里不含冲突 id，让 --merge 内部的顺序可见：后者覆盖前者
        write_json({'title': '书', **make_book([9], 'keep')}, self.path('keep.json'))
        write_json({**make_book([1], 'first')}, self.path('a.json'))
        write_json({**make_book([1], 'second')}, self.path('b.json'))
        code, out = self.build('--data', self.path('keep.json'),
                               '--merge', self.path('a.json'), self.path('b.json'),
                               '--out', self.path('reader.html'))
        self.assertEqual(code, 0, out)
        html = open(self.path('reader.html'), encoding='utf-8').read()
        self.assertIn('second1.', html)
        self.assertNotIn('first1.', html)
        self.assertIn('keep9.', html)

    def test_native_section_renders(self):
        # 🗣 母语者视角：noteList 同款容错，纯字符串也能吃
        write_json({'title': '书', 'sentences': [
            {'id': 1, 'text': 'a.', 'para': 1, 'translation': 't',
             'native': [{'t': '口语对应', 'd': 'bref, aujourd’hui on dirait plutôt…'}]},
            {'id': 2, 'text': 'b.', 'para': 1, 'translation': 't',
             'native': ['纯字符串形式也行']},
        ]}, self.path('n.json'))
        code, out = self.build('--data', self.path('n.json'),
                               '--out', self.path('rn.html'))
        self.assertEqual(code, 0, out)
        html = open(self.path('rn.html'), encoding='utf-8').read()
        self.assertIn('🗣 母语者', html)
        self.assertIn('口语对应', html)
        self.assertIn('纯字符串形式也行', html)

    def test_native_wrong_type_fails(self):
        # native 必须是 list/对象/字符串，数字应被拒
        write_json({'title': '书', 'sentences': [
            {'id': 1, 'text': 'a.', 'para': 1, 'translation': 't', 'native': 5}]},
            self.path('bad.json'))
        code, out = self.build('--data', self.path('bad.json'),
                               '--out', self.path('rb.html'))
        self.assertEqual(code, 1, out)
        self.assertIn('native', out)

    def test_total_flag_reaches_the_reader(self):
        # --total：增量生成时阅读器显示「已覆盖 X/N 句」并在结尾提示继续
        write_json({'title': '书', **make_book([1, 2])}, self.path('d.json'))
        code, out = self.build('--data', self.path('d.json'),
                               '--total', '50', '--out', self.path('r.html'))
        self.assertEqual(code, 0, out)
        self.assertIn('total=50', out)
        html = open(self.path('r.html'), encoding='utf-8').read()
        self.assertIn('"total":50', html)

    def test_total_inherited_from_merged_file(self):
        # meta.json 当 --data 且没写 total 时，从被合并文件继承
        write_json({'title': '书名'}, self.path('meta.json'))
        write_json({'total': 40, **make_book([1, 2])}, self.path('d1.json'))
        code, out = self.build('--data', self.path('meta.json'),
                               '--merge', self.path('d1.json'),
                               '--out', self.path('r.html'))
        self.assertEqual(code, 0, out)
        html = open(self.path('r.html'), encoding='utf-8').read()
        self.assertIn('"total":40', html)

    def test_unknown_lang_warns(self):
        # 拼错的语言码要明说，不能静默给出拉丁排版
        write_json({'title': '书', 'lang': 'xyz', **make_book([1])},
                   self.path('d.json'))
        code, out = self.build('--data', self.path('d.json'),
                               '--out', self.path('r.html'))
        self.assertEqual(code, 0, out)
        self.assertIn("unknown language code 'xyz'", out)
        html = open(self.path('r.html'), encoding='utf-8').read()
        self.assertIn('data-lang="latn"', html)


class ShippedSample(unittest.TestCase):
    """assets/sample_data.json 是并发实例的风格锚，必须永远能过检、能构建。"""

    def setUp(self):
        import shutil
        self.d = tempfile.mkdtemp(prefix='fcr-sample-')
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)

    def test_sample_builds_into_a_reader(self):
        sample = os.path.join(os.path.dirname(HERE), 'assets', 'sample_data.json')
        out = os.path.join(self.d, 'sample.html')
        code, log = run(BUILD, '--data', sample, '--out', out)
        self.assertEqual(code, 0, log)
        self.assertIn('2 sentences', log)
        with open(out, encoding='utf-8') as f:
            html = f.read()
        self.assertIn('Eh bien, mon prince.', html)


if __name__ == '__main__':
    unittest.main()
