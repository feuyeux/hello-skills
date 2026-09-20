#!/usr/bin/env python3
"""Golden cases for split_sentences.py.

The abbreviation tables, quote stack and attribution rules regress easily —
every case here encodes a promise the SKILL.md table makes about a language.
Run:  python3 -m unittest discover -s tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'scripts'))

import split_sentences as ss  # noqa: E402


class Russian(unittest.TestCase):
    def split(self, text):
        return ss.splitter_for('ru')(text)

    def test_soft_abbreviation_stays_inside(self):
        # «т. е.» 由「点后接小写」规则保护，不被当成句末
        self.assertEqual(len(self.split('Это, т. е. данный факт, важен. Потом он ушёл.')), 2)

    def test_numbered_abbreviations(self):
        # См. / рис. / табл. 都是缩写，且后接数字时一定不是句末
        self.assertEqual(len(self.split('См. рис. 3 и табл. 4. Далее.')), 2)

    def test_dash_attribution_kept_with_speech(self):
        # — Правда? — спросил он. 是一句话
        self.assertEqual(self.split('— Правда? — спросил он. Она молчала.'),
                         ['— Правда? — спросил он.', 'Она молчала.'])

    def test_new_utterance_after_narration_is_separate(self):
        # 叙述句收尾后接大写开头的对白：必须断开，只有小写归属词才并句
        self.assertEqual(self.split('Он ушёл. — Здравствуйте! — сказала она.'),
                         ['Он ушёл.', '— Здравствуйте! — сказала она.'])

    def test_period_inside_yolochki_is_not_sentence_end(self):
        self.assertEqual(len(self.split('Он сказал: «Приду. Завтра.» и ушёл.')), 1)

    def test_pre_reform_orthography_detected_as_russian(self):
        self.assertEqual(ss.detect_lang('Онъ шёлъ по дорогѣ въ ночь.'), 'ru')


class French(unittest.TestCase):
    def split(self, text):
        return ss.splitter_for('fr')(text)

    def test_mister_initial(self):
        self.assertEqual(self.split('M. Dupont est venu. Il est parti.'),
                         ['M. Dupont est venu.', 'Il est parti.'])

    def test_decimal_comma(self):
        self.assertEqual(len(self.split('Il avait 3,14 francs. Puis il partit.')), 2)

    def test_guillemets_with_attribution(self):
        # 引号内的句号不断句；闭引号后跟 dit-il 时并成一句
        self.assertEqual(self.split('« Viens. » dit-il. Elle vint.'),
                         ['« Viens. » dit-il.', 'Elle vint.'])

    def test_two_sentences_inside_guillemets_not_torn(self):
        self.assertEqual(len(self.split('Elle dit : « Viens ici. Reste. » puis sort.')), 1)

    def test_detection(self):
        self.assertEqual(
            ss.detect_lang('Le prince vint à Paris avec une lettre. Elle était belle.'),
            'fr')


class Japanese(unittest.TestCase):
    def split(self, text):
        return ss.splitter_for('ja')(text)

    def test_attribution_stays_with_speech(self):
        self.assertEqual(len(self.split('「そうです。」と彼は言った。それから帰った。')), 2)

    def test_inner_short_sentences_not_torn(self):
        self.assertEqual(len(self.split('「うん。そうだね。」と答えた。')), 1)


class Korean(unittest.TestCase):
    def test_attribution(self):
        out = ss.splitter_for('ko')('"안녕!" 하고 말했다. 그는 웃었다.')
        self.assertEqual(len(out), 2)

    def test_fullwidth_punctuation_ends_sentence(self):
        out = ss.splitter_for('ko')('그랬다！ 그런데？')
        self.assertEqual(len(out), 2)


class Arabic(unittest.TestCase):
    def test_arabic_question_mark_ends_sentence(self):
        out = ss.splitter_for('ar')('هل أنت هنا؟ نعم أنا هنا.')
        self.assertEqual(len(out), 2)


class Paragraphs(unittest.TestCase):
    def test_hard_wrap_joined(self):
        paras, _ = ss.paragraph_texts(
            'He said that everything was going to be fine from now on\n'
            'and that they should not worry about it any more.\n'
            '\n'
            'Next paragraph begins here and it is long enough to stand alone.',
            'en')
        self.assertEqual(len(paras), 2)
        self.assertTrue(paras[0].startswith('He said that everything'))
        self.assertIn('worry about it any more.', paras[0])

    def test_short_lines_stay_separate(self):
        # 两行都短：标题/署名一类，各自成段，别粘成一句
        paras, _ = ss.paragraph_texts('Chapter I\nThe Beginning', 'en')
        self.assertEqual(paras, ['Chapter I', 'The Beginning'])


class Aozora(unittest.TestCase):
    def test_ruby_stripped(self):
        self.assertEqual(ss.strip_aozora('漢字《かんじ》のテスト', 'ja'),
                         '漢字のテスト')

    def test_editor_note_removed(self):
        self.assertEqual(ss.strip_aozora('本文［＃５字下げ］つづく', 'ja'),
                         '本文つづく')


if __name__ == '__main__':
    unittest.main()
