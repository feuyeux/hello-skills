#!/usr/bin/env python3
"""Golden cases for check_data.py — chiefly the Russian stress-mark rule.

Run:  python3 -m unittest discover -s tests
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CHECK = os.path.join(HERE, '..', 'scripts', 'check_data.py')


def run_check(data, *extra):
    fd, path = tempfile.mkstemp(suffix='.json')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    try:
        p = subprocess.run([sys.executable, CHECK, '--data', path] + list(extra),
                           capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr
    finally:
        os.unlink(path)


def run_strict(data):
    return run_check(data, '--strict')


def book(lang, words):
    return {
        'title': 'test', 'lang': lang,
        'sentences': [{'id': 1, 'text': 'Он пришёл домой.', 'para': 1,
                       'translation': '他回家了。', 'words': words}],
    }


class Stress(unittest.TestCase):
    def assert_warns_about(self, data, needle):
        code, out = run_check(data)
        self.assertEqual(code, 0, out)          # 警告不改变退出码
        self.assertIn(needle, out)

    def assert_clean(self, data):
        code, out = run_check(data)
        self.assertEqual(code, 0, out)
        self.assertNotIn('warning', out)

    def test_stressed_russian_ipa_is_clean(self):
        self.assert_clean(book('ru', [
            {'w': 'придёт', 'p': 'prʲɪdʲˈʐdʲot', 'm': '将要来'},
        ]))

    def test_unstressed_russian_ipa_warns(self):
        self.assert_warns_about(book('ru', [
            {'w': 'придёт', 'p': 'prʲɪdʲʐdʲot', 'm': '将要来'},
        ]), 'carries no stress mark')

    def test_missing_russian_phonetic_warns(self):
        self.assert_warns_about(book('ru', [
            {'w': 'придёт', 'm': '将要来'},
        ]), 'has no stress-marked phonetic')

    def test_monosyllable_needs_no_stress_mark(self):
        # я → ja：单音节没有重音可言，不应报重音警告
        self.assert_clean(book('ru', [
            {'w': 'я', 'p': 'ja', 'm': '我'},
        ]))

    def test_layout_family_name_also_enforced(self):
        # lang 写成排版族名 cyrl 时同样要按俄语查重音
        self.assert_warns_about(book('cyrl', [
            {'w': 'придёт', 'p': 'prʲɪdʲʐdʲot', 'm': '将要来'},
        ]), 'carries no stress mark')

    def test_foreign_loanword_exempt_from_stress_rule(self):
        # 俄语书里的法语借词（Eh bien）不适用俄语重音规则
        self.assert_clean(book('ru', [
            {'w': 'Eh bien', 'p': 'e bjɛ̃', 'm': '那么，好吧'},
        ]))

    def test_japanese_without_kana_is_an_error(self):
        code, out = run_check(book('ja', [{'w': '無鉄砲', 'm': '鲁莽'}]))
        self.assertEqual(code, 1, out)
        self.assertIn('has no kana reading', out)


class ShippedSample(unittest.TestCase):
    def test_shipped_sample_passes_clean(self):
        """assets/sample_data.json 是并发实例的风格锚——它自己必须 0 警告过检。"""
        sample = os.path.join(HERE, '..', 'assets', 'sample_data.json')
        p = subprocess.run([sys.executable, CHECK, '--data', sample],
                           capture_output=True, text=True)
        out = p.stdout + p.stderr
        self.assertEqual(p.returncode, 0, out)
        self.assertIn('OK', out)
        self.assertNotIn('warn', out)


class Sanity(unittest.TestCase):
    def test_clean_book_passes(self):
        code, out = run_check({
            'title': 'Война и мир',
            'lang': 'ru',
            'sentences': [{
                'id': 1, 'text': '— Eh bien, mon prince.', 'para': 2,
                'translation': '“怎么样啊，公爵。”',
                'words': [{'w': 'Eh bien', 'p': 'e bjɛ̃', 'm': '那么，好吧'}],
                'grammar': [{'t': '破折号起句', 'd': '俄语对话用 — 引导。'}],
                'culture': [{'t': '贵族法语', 'd': '法语是身份的标志。'}],
            }],
        })
        self.assertEqual(code, 0, out)
        self.assertIn('OK', out)

    def test_missing_translation_is_an_error(self):
        code, out = run_check({
            'title': 't', 'lang': 'en',
            'sentences': [{'id': 1, 'text': 'He came.', 'para': 1}],
        })
        self.assertEqual(code, 1, out)
        self.assertIn('has no translation', out)

    def test_native_notes_counted(self):
        code, out = run_check({
            'title': 't', 'lang': 'fr',
            'sentences': [{'id': 1, 'text': 'Il vint.', 'para': 1,
                           'translation': '他来了。',
                           'native': [{'t': '口语对应', 'd': "aujourd'hui on dirait « il est arrivé »"}]},
                          {'id': 2, 'text': 'Il partit.', 'para': 1,
                           'translation': '他走了。'}],
        })
        self.assertEqual(code, 0, out)
        self.assertIn('1 母语者', out)
        self.assertIn('母语者 1/2 句', out)

    def test_korean_missing_ipa_warns_only_in_strict(self):
        ko = book('ko', [{'w': '무정', 'm': '无情'}])
        # 非 strict：缺 IPA 只是留待补充，不拦
        code, out = run_check(ko)
        self.assertEqual(code, 0, out)
        self.assertNotIn('warning', out)
        # strict：韩语生词缺 IPA 升级为错误
        code, out = run_strict(ko)
        self.assertEqual(code, 1, out)
        self.assertIn('has no IPA', out)


if __name__ == '__main__':
    unittest.main()
