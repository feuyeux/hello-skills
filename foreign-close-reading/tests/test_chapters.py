#!/usr/bin/env python3
"""Chapter detection, outline navigation and 500 KB volume packing.

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

sys.path.insert(0, SCRIPTS)

import split_sentences as ss  # noqa: E402

# 模板本身就有 ~44 KB，所以体积上限必须设在它之上才有意义：
# 每章再加 ~6 KB 的讲解，两章一卷就正好在两章处封顶。
TEMPLATE_KB = 44
CAP_KB = 56


def run(script, *args, **kw):
    p = subprocess.run([sys.executable, script] + list(args),
                       capture_output=True, text=True, **kw)
    return p.returncode, p.stdout + p.stderr


def write_json(obj, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False)


def read_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


class ChapterLine(unittest.TestCase):
    """标题行的形状判定：认得出来，也不能把正文误当标题。"""

    def test_recognizes_numbered_titles(self):
        for line in ('Chapter I', 'CHAPTER 12', 'Chapter One: The Fall',
                     'Глава первая', 'ЧАСТЬ ВТОРАЯ', 'Chapitre premier',
                     'Capítulo 3', 'Kapitel VII', '第一部', '第三章',
                     '第十二回', '第一章 风雪夜', 'Part Two', 'Book the Third',
                     'The First Book', '序章', '楔子', 'Prologue', 'EPILOGUE'):
            self.assertTrue(ss.looks_chapter_line(line), line)

    def test_ordinary_sentences_are_not_titles(self):
        # 每一条都是真书里会出现的一整句：被吞掉就等于读者少读一句
        for line in ('The chapter of accidents is long.',
                     'Part of the reason was simple.',
                     'Chapter and verse were quoted.',
                     'It was a dark and stormy night.',
                     'Глава была длинной и скучной.',
                     'He opened the book.',
                     'Acting was his life.',
                     'The book was on the table.',
                     'A part of me wanted to stay.',
                     'Book the room for tonight, please.',
                     'Another chapter opens with a perfectly ordinary sentence.',
                     'The second part of the story is better.',
                     'She read the first chapter slowly.',
                     'The First Book was published in 1890 and sold well.',
                     '第三章。'):
            self.assertIsNone(ss.looks_chapter_line(line), line)

    def test_short_period_terminated_titles_are_still_titles(self):
        # 独立成段的 "Chapter One." 只可能是标题，不会是正文
        self.assertIsNotNone(ss.looks_chapter_line('Chapter One.'))

    def test_titles_with_accents_match_stems(self):
        # capítulo / chapitre 的重音不该妨碍词干匹配
        self.assertIsNotNone(ss.looks_chapter_line('Capítulo XII'))
        self.assertIsNotNone(ss.looks_chapter_line('Chapitre II'))

    def test_bare_numeral_is_a_chapter_title(self):
        # 光杆编号独立成段（加缪《局外人》整本都是 I–VI）：几乎不可能是正文
        for line in ('I', 'II', 'IV', 'VI', 'XIII', 'I.', 'III.', '3', '12.', 'XX'):
            self.assertTrue(ss.looks_chapter_line(line), line)

    def test_bare_lowercase_or_long_digits_are_not_titles(self):
        # 独行的小写词、四位年份都不是章号，不能被吞掉
        for line in ('i', 'v', 'a', '1900', 'Vive la France.'):
            self.assertIsNone(ss.looks_chapter_line(line), line)

    def test_quoted_lines_are_never_titles(self):
        # 带引号起头的独行短句是对白/电报/引文，哪怕碰巧以标题词开头
        # （海明威《太阳照常升起》里的电报 "Letter to-day."、"Day after to-morrow."）
        for line in ('“Letter to-day.”', '“Day after to-morrow.”',
                     '"The Book of the Dead."', '«Lettre reçue.»', '「第一章到。」'):
            self.assertIsNone(ss.looks_chapter_line(line), line)

    def test_part_and_chapter_numbers_merge_into_one_title(self):
        # "Première Partie" 紧挨 "I"：部标题不能被章号吞掉
        self.assertEqual(
            ss.detect_chapters(['Première Partie', 'I', 'Maman est morte aujourd’hui.']),
            {1: 'Première Partie', 2: 'I'})
        sentences = [{'id': 1, 'text': 'Maman est morte aujourd’hui.', 'para': 3}]
        chapters = ss.build_chapters(sentences, {1: 'Première Partie', 2: 'I'})
        self.assertEqual(chapters, [{'index': 1, 'title': 'Première Partie · I',
                                     'start': 1}])


class ChaptersInSplit(unittest.TestCase):
    BOOK = (
        'Chapter I\n'
        '\n'
        'The first sentence of the book stands here alone.\n'
        '\n'
        'The second sentence follows it and is long enough to stand alone.\n'
        '\n'
        'Chapter II\n'
        '\n'
        'Another chapter opens with this perfectly ordinary sentence.\n'
    )

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix='fcr-chap-')
        self.addCleanup(__import__('shutil').rmtree, self.d, ignore_errors=True)
        self.txt = os.path.join(self.d, 'book.txt')
        with open(self.txt, 'w', encoding='utf-8') as f:
            f.write(self.BOOK)

    def split(self, *extra):
        out = os.path.join(self.d, 'sentences.json')
        code, log = run(SPLIT, self.txt, '--out', out, *extra)
        self.assertEqual(code, 0, log)
        return read_json(out)

    def test_title_paragraph_is_consumed_not_annotated(self):
        d = self.split()
        texts = [s['text'] for s in d['sentences']]
        self.assertEqual(len(texts), 3)
        self.assertFalse(any(t.startswith('Chapter') for t in texts), texts)

    def test_every_sentence_carries_a_chapter_number(self):
        d = self.split()
        self.assertEqual([s['ch'] for s in d['sentences']], [1, 1, 2])
        self.assertEqual([c['start'] for c in d['chapters']], [1, 3])
        self.assertEqual([c['title'] for c in d['chapters']], ['Chapter I', 'Chapter II'])
        self.assertEqual([c['index'] for c in d['chapters']], [1, 2])

    def test_chapters_off_keeps_titles_as_text(self):
        d = self.split('--chapters', 'off')
        self.assertNotIn('chapters', d)
        self.assertTrue(any(t.startswith('Chapter I') for t in
                            [s['text'] for s in d['sentences']]))

    def test_no_titles_means_no_chapters(self):
        plain = os.path.join(self.d, 'plain.txt')
        with open(plain, 'w', encoding='utf-8') as f:
            f.write('One ordinary sentence goes here.\n\n'
                    'Another ordinary sentence goes here too.\n')
        out = os.path.join(self.d, 'plain.json')
        code, log = run(SPLIT, plain, '--out', out)
        self.assertEqual(code, 0, log)
        d = read_json(out)
        self.assertNotIn('chapters', d)
        self.assertEqual([s['ch'] for s in d['sentences']], [0, 0])

    def test_slice_keeps_chapter_starts_inside_the_selection(self):
        out = os.path.join(self.d, 'slice.json')
        code, log = run(SPLIT, self.txt, '--start', '3', '--out', out)
        self.assertEqual(code, 0, log)
        d = read_json(out)
        # 从第 3 句（第二章开头）切进来：只留这一章，起点对齐到选区首句
        self.assertEqual([c['start'] for c in d['chapters']], [3])
        self.assertEqual([c['title'] for c in d['chapters']], ['Chapter II'])
        self.assertEqual([c['index'] for c in d['chapters']], [1])

    def test_slice_from_midchapter_gets_an_untitled_opening(self):
        out = os.path.join(self.d, 'slice.json')
        code, log = run(SPLIT, self.txt, '--start', '2', '--limit', '2', '--out', out)
        self.assertEqual(code, 0, log)
        d = read_json(out)
        self.assertEqual([s['id'] for s in d['sentences']], [2, 3])
        self.assertEqual([c['title'] for c in d['chapters']], ['', 'Chapter II'])
        self.assertEqual([c['start'] for c in d['chapters']], [2, 3])


class ChaptersInPlan(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix='fcr-chapplan-')
        self.addCleanup(__import__('shutil').rmtree, self.d, ignore_errors=True)
        self.txt = os.path.join(self.d, 'book.txt')
        with open(self.txt, 'w', encoding='utf-8') as f:
            f.write('Глава первая\n\nПервое предложение стоит здесь одно.\n\n'
                    'Второе предложение тоже достаточно длинное, чтобы быть отдельным.\n\n'
                    'Глава вторая\n\nНачало второй главы выглядит как обычное предложение.\n')

    def test_plan_slices_carry_the_whole_chapter_list(self):
        code, log = run(SPLIT, self.txt, '--plan', '2', cwd=self.d)
        self.assertEqual(code, 0, log)
        for k in (1, 2):
            chunk = read_json(os.path.join(self.d, 'sentences-%d.json' % k))
            self.assertEqual([c['title'] for c in chunk['chapters']],
                             ['Глава первая', 'Глава вторая'])


class Volumes(unittest.TestCase):
    """500 KB 上限：以章回为单位向下取整，同一章绝不跨卷。"""

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix='fcr-vol-')
        self.addCleanup(__import__('shutil').rmtree, self.d, ignore_errors=True)

    def path(self, name):
        return os.path.join(self.d, name)

    def make_book(self, n_chapters=4, per_chapter=3, pad=1400):
        """每句都塞一点讲解文本，好把体积撑到模板之上。"""
        sents, chapters, sid = [], [], 0
        for c in range(1, n_chapters + 1):
            chapters.append({'title': 'Chapter %d' % c,
                             'start': sid + 1})
            for _ in range(per_chapter):
                sid += 1
                sents.append({
                    'id': sid, 'text': 'Sentence %d of chapter %d.' % (sid, c),
                    'para': sid, 'ch': c,
                    'translation': '第 %d 句的中文译文。' % sid,
                    'grammar': [{'t': '语法点 %d' % sid, 'd': 'x' * pad}],
                })
        return {'title': '体积测试书', 'subtitle': '作者', 'lang': 'en',
                'chapters': chapters, 'sentences': sents}

    def build(self, data, out, *extra):
        src = self.path('data.json')
        write_json(data, src)
        code, log = run(BUILD, '--data', src, '--out', self.path(out), *extra)
        return code, log

    def test_no_chapters_still_writes_one_file(self):
        data = {'title': '无章书', 'sentences': [
            {'id': 1, 'text': 'a.', 'para': 1, 'translation': 't'},
            {'id': 2, 'text': 'b.', 'para': 1, 'translation': 't'}]}
        code, log = self.build(data, 'plain.html')
        self.assertEqual(code, 0, log)
        self.assertTrue(os.path.exists(self.path('plain.html')))
        self.assertFalse(os.path.exists(self.path('plain-1.html')))

    def test_volumes_are_split_at_chapter_boundaries(self):
        data = self.make_book(4, 3, 1400)
        code, log = self.build(data, 'book.html', '--max-kb', str(CAP_KB))
        self.assertEqual(code, 0, log)
        vols = [p for p in sorted(os.listdir(self.d)) if p.startswith('book-')]
        self.assertGreater(len(vols), 1, log)

        seen, ch_seen = set(), set()
        for name in vols:
            d = read_json_of_embedded(self.path(name))
            self.assertLessEqual(os.path.getsize(self.path(name)),
                                 CAP_KB * 1024,
                                 '%s exceeds the cap' % name)
            chs = [c['index'] for c in d.get('chapters', [])]
            # 每一章在整本书里只属于一卷，绝不被劈成两半
            key = lambda c: d['chapters'][c - 1]['start']   # 卷内 index 会重排
            self.assertFalse(ch_seen & set(key(c) for c in chs),
                             '%s re-splits a chapter' % name)
            ch_seen |= set(key(c) for c in chs)
            # 卷内每一句都属于本卷的章，逐句数加起来正好是这个章的数量
            per = {}
            for s in d['sentences']:
                ci = max((c['index'] for c in d['chapters']
                          if float(s['id']) >= float(c['start'])), default=None)
                per[ci] = per.get(ci, 0) + 1
                seen.add(s['id'])
            self.assertEqual(sorted(per), sorted(chs))
            for ci, n in per.items():
                # 每一章在本卷里必须是完整的（fixture 每章 3 句）
                self.assertEqual(n, 3, 'chapter %s is cut short' % ci)
        self.assertEqual(seen, set(range(1, 13)))
        self.assertEqual(ch_seen, {1, 4, 7, 10})   # 四章各自的起始句 id

    def test_volume_is_floor_rounded_to_whole_chapters(self):
        """上限只用来决定「还能不能再塞进一章」，不切句子也不切章。"""
        data = self.make_book(4, 3, 1400)
        code, log = self.build(data, 'book.html', '--max-kb', str(CAP_KB))
        self.assertEqual(code, 0, log)
        vols = [p for p in sorted(os.listdir(self.d)) if p.startswith('book-')]
        sizes = [os.path.getsize(self.path(v)) for v in vols]
        counts = [len(read_json_of_embedded(self.path(v))['sentences']) for v in vols]
        # 每卷都是 3 的整数倍 = 整章；且每卷都在上限内、再加一章就会超
        for n, size in zip(counts, sizes):
            self.assertEqual(n % 3, 0, counts)
            self.assertLessEqual(size, CAP_KB * 1024)
        # 任一卷再加一章都会超限（否则贪心就没装满）
        self.assertEqual(sum(counts), 12)
        self.assertLess(max(sizes), CAP_KB * 1024)

    def test_first_volume_links_forward_and_last_links_back(self):
        data = self.make_book(4, 3, 1400)
        code, log = self.build(data, 'book.html', '--max-kb', str(CAP_KB))
        self.assertEqual(code, 0, log)
        vols = [p for p in sorted(os.listdir(self.d)) if p.startswith('book-')]
        first = read_json_of_embedded(self.path(vols[0]))
        last = read_json_of_embedded(self.path(vols[-1]))
        self.assertEqual(first['nav']['prev'], '')
        self.assertEqual(first['nav']['next'], vols[1])
        self.assertEqual(first['nav']['index'], 1)
        self.assertEqual(first['nav']['total'], len(vols))
        self.assertEqual(last['nav']['next'], '')
        self.assertEqual(last['nav']['prev'], vols[-2])
        self.assertIn('（1/%d）' % len(vols), read(self.path(vols[0])))

    def test_single_flag_ignores_the_cap(self):
        data = self.make_book(4, 3, 1400)
        code, log = self.build(data, 'one.html', '--max-kb', str(CAP_KB),
                               '--single')
        self.assertEqual(code, 0, log)
        self.assertTrue(os.path.exists(self.path('one.html')))
        self.assertEqual([p for p in os.listdir(self.d) if p.startswith('one-')], [])
        d = read_json_of_embedded(self.path('one.html'))
        self.assertEqual(len(d['sentences']), 12)

    def test_oversized_single_chapter_gets_its_own_volume_and_a_warning(self):
        data = self.make_book(3, 1, 40000)      # 每章自己就超过上限
        code, log = self.build(data, 'big.html', '--max-kb', str(CAP_KB))
        self.assertEqual(code, 0, log)
        self.assertIn('上限', log)
        vols = [p for p in sorted(os.listdir(self.d)) if p.startswith('big-')]
        self.assertEqual(len(vols), 3, log)

    def test_book_without_a_single_chapter_boundary_warns(self):
        # 全书只有一个章回边界 = 无处可拆：整本写进一个文件并说明原因
        data = self.make_book(1, 3, 12000)
        code, log = self.build(data, 'solo.html', '--max-kb', str(CAP_KB))
        self.assertEqual(code, 0, log)
        self.assertGreater(os.path.getsize(self.path('solo.html')), CAP_KB * 1024)
        self.assertIn('无法在章与章之间拆开', log)
        self.assertTrue(os.path.exists(self.path('solo.html')))

    def test_chapters_merge_from_earlier_batches(self):
        # 增量生成：data.json 只有句子，章回清单由早先的切片带过来
        write_json({'title': '书', 'lang': 'en', 'sentences': [
            {'id': 3, 'text': 'c.', 'para': 1, 'translation': 't'}]},
            self.path('data.json'))
        write_json({'title': '书', 'chapters': [
            {'title': 'Chapter I', 'start': 1},
            {'title': 'Chapter II', 'start': 3}],
            'sentences': [{'id': 1, 'text': 'a.', 'para': 1, 'translation': 't'},
                          {'id': 2, 'text': 'b.', 'para': 1, 'translation': 't'}]},
            self.path('old.json'))
        code, log = run(BUILD, '--data', self.path('data.json'),
                        '--merge', self.path('old.json'),
                        '--out', self.path('r.html'))
        self.assertEqual(code, 0, log)
        d = read_json_of_embedded(self.path('r.html'))
        self.assertEqual([c['title'] for c in d['chapters']],
                         ['Chapter I', 'Chapter II'])
        # 起点不在本书里的章被吸附到下一句，而不是把导航指空
        self.assertEqual([c['start'] for c in d['chapters']], [1, 3])

    def test_per_sentence_ch_is_the_fallback(self):
        # data.json 只写了每句的 ch（split 的输出）也要能长出章回边界
        data = self.make_book(2, 2, 10)
        data.pop('chapters')
        code, log = self.build(data, 'ch.html')
        self.assertEqual(code, 0, log)
        d = read_json_of_embedded(self.path('ch.html'))
        self.assertEqual([c['start'] for c in d['chapters']], [1, 3])

    def test_explicit_chapters_in_data_win(self):
        data = self.make_book(2, 2, 10)
        data['chapters'] = [{'title': '全书', 'start': 1}]
        code, log = self.build(data, 'one-ch.html')
        self.assertEqual(code, 0, log)
        d = read_json_of_embedded(self.path('one-ch.html'))
        self.assertEqual([c['title'] for c in d['chapters']], ['全书'])

    def test_minify_shrinks_the_file_and_keeps_the_data(self):
        data = self.make_book(2, 2, 10)
        code, log = self.build(data, 'plain.html')
        self.assertEqual(code, 0, log)
        code, log = self.build(data, 'mini.html', '--minify')
        self.assertEqual(code, 0, log)
        self.assertLess(os.path.getsize(self.path('mini.html')),
                        os.path.getsize(self.path('plain.html')))
        d = read_json_of_embedded(self.path('mini.html'))
        self.assertEqual(len(d['sentences']), 4)


def read_json_of_embedded(path):
    """把阅读器内联的 data JSON 抠出来（build 之后唯一可信的产物）。"""
    html = read(path)
    start = html.index('id="data">') + len('id="data">')
    end = html.index('</script>', start)
    return json.loads(html[start:end].replace('<\\/', '</'))


if __name__ == '__main__':
    unittest.main()
