#!/usr/bin/env python3
"""Split a foreign-language text file into sentences, preserving paragraphs.

Usage:
  python3 split_sentences.py INPUT.txt [--start N] [--limit N]
                            [--out sentences.json] [--lang CODE] [--para auto|blank|line]
                            [--plan N] [--plan-dir DIR]

Prints (or writes) JSON:
  {"lang":"ru","layout":"cyrl","total":M,"para_mode":"blank",
   "sentences":[{"id":1,"text":"...","para":1}]}

- id is 1-based, continuous in reading order
- para is the 1-based natural-paragraph number (the reader rebuilds layout from it)
- --start/--limit slice by sentence id (inclusive start, limit = max count)
- lang/layout drive typography in the reader: latn / cyrl / cjk / jpn / kor / rtl

Per-language handling:
  ru  аббревиатуры (т. е., т. д., г., стр., руб. …), десятичные дроби, «ёлочки»
  fr  M. / Mme / Mlle / etc. / p. ex., guillemets « », décimales 3,14, tirets de dialogue
  ja  。！？… 断句；「」『』 内短句不拆，会话语尾（「…。」と言った）与叙述合成一句
  ko  . ? ! … 断句；"…" 하고 말했다 合成一句，소수점·약어 보호
  en/de/es/it/pt  通用缩写表（Mr. Dr. e.g. bzw. p. ej. …）
"""

import argparse
import json
import os
import re
import sys

# ── 缩写表 ──────────────────────────────────────────────────────────
# 跨语言通用的缩写（多为计量、卷册、月份一类，不会与常用词撞车）。
# 「本身就是一个完整的词」的缩写（etc / al）不进这张表：它们句末出现的频率
# 远高于句中，交给「点后接小写或逗号」那条规则去拦就够了，
# 写死成缩写会把 « …, etc. He read … » 这类正常句末粘住。
BASE_ABBR = {
    'mr', 'mrs', 'ms', 'dr', 'prof', 'rev', 'hon', 'st', 'jr', 'sr', 'mt',
    'vs', 'e.g', 'i.e', 'cf', 'fig', 'figs', 'ch',
    'chap', 'sec', 'vol', 'p', 'pp', 'ed', 'eds', 'trans', 'inc', 'ltd',
    'co', 'corp', 'dept', 'univ', 'fl', 'c', 'ca', 'approx',
    'jan', 'feb', 'mar', 'apr', 'jun', 'jul', 'aug', 'sep', 'oct',
    'nov', 'dec', 'mon', 'tue', 'tues', 'wed', 'thu', 'thur', 'thurs',
    'fri', 'sat', 'sun',
}
# 只在部分语言里当缩写、在别的语言里是常用词的，按语言分开登记：
# est = established / 法语 est「是」；no, nos = number / 西语·意语 no「不」
# sept = September / 法语 sept「七」；mar = March / 西语·法语 mar「海」
ENG_ABBR = {'no', 'nos', 'est', 'sept', 'mar'}
# 法语缩写里绝不能混进常用词：art / me / mer / jeu / sept / ex / fig / vol /
# t / s / mm 都是独立的法语词或极常见的字母，一旦列入，句中出现的它们会把
# 后面的句子全都粘住（« … de l'art. Il faut … » 就再也切不开）。
# 需要跟数字的场合（t. 2、vol. 3）另有一条「缩写后紧跟数字」的规则兜底。
FRA_ABBR = {
    'mme', 'mmes', 'mlle', 'mlles', 'dr', 'pr', 'av', 'bd',
    'env', 'cf', 'tt', 'ste', 'j.-c',
    'janv', 'févr', 'fevr', 'avr', 'juill', 'déc', 'lun',
    'ven', 'sam', 'dim', 'réf', 'p.ex', 'n.b',
}
# 与常用虚词同形的单字母（в/с/н/д/п/т/е/до）一律不列入：
# «т. е.» «т. д.» 由「句点后接小写」规则拦住，«г. 1805» «стр. 45» 由「后接数字」拦住，
# 写死成缩写反而会把正常句末当成缩略而粘住下一句。
RUS_ABBR = {
    'гг', 'вв', 'см', 'стр', 'рис', 'табл', 'руб', 'коп', 'тыс', 'млн',
    'млрд', 'трлн', 'чел', 'проф', 'акад', 'доц', 'тов', 'ред', 'изд',
    'напр', 'др', 'тт', 'пп', 'яз', 'обл', 'гор', 'н.э',
    'янв', 'фев', 'февр', 'мар', 'апр', 'авг', 'сен', 'сент', 'окт', 'ноя',
    'дек', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс',
}
DEU_ABBR = {
    'bzw', 'd.h', 'evtl', 'ggf', 'inkl', 'insb', 'max', 'min', 'mio', 'mrd',
    'nr', 'o.ä', 'u.a', 'usw', 'vgl', 'z.b', 'z.zt', 'abb', 'bd', 'kap',
    'hrsg', 'zugl', 'mär', 'mrz', 'okt', 'dez', 'jh', 'jhd',
}
SPA_ABBR = {
    'sr', 'sra', 'sres', 'dra', 'ud', 'uds', 'ee.uu', 'p.ej', 'cap', 'pag',
    'pág', 'núm', 'núms', 'izq', 'avda', 'dpto', 'izqda',
}
ITA_ABBR = {'sig', 'sigg', 'dott', 'ing', 'avv', 'ecc', 'p.es', 'cap', 'pag', 'n'}
# 只留真正的缩写；예(是)、약(大约)、년/월/일 这些是常用词或量词，句末的句点就是句号
KOR_ABBR = {'등', '즉', '씨', '님', '항', '조', '호'}

# \u061f = ؟，阿拉伯语句末问号（阿拉伯语也用 . 收尾）
LATIN_END = '.!?\u2026\u203d\u061f'
SPACES = ' \t\u00a0\u202f'
# 成对引号：key 为开引号，value 为闭引号（自身成对的写同一个字符）
# 只登记「开口字形和收口字形不同」的成对符号。像 ' 这种既是撇号（C'est）
# 又是引号的字符不能进栈，否则法语/英语文本会一路误判成「引号没闭合」。
QUOTE_PAIRS = {
    '\u300c': '\u300d', '\u300e': '\u300f', '\u201c': '\u201d', '\u2018': '\u2019',
    '\u00ab': '\u00bb', '\u2039': '\u203a',
    '\uff08': '\uff09', '\u3010': '\u3011',
}
QUOTE_CHARS = set(QUOTE_PAIRS) | set(QUOTE_PAIRS.values())
# 只看字形就知道是“收尾引号”的字符——不需要配对判断
HARD_CLOSERS = '\u201d\u2019\u300d\u300f\u00bb\u203a)\uff09]\u3011'
# 开闭同形的引号（" 与 '）：可能是开引号，也可能是撇号。
# 只有在本段中此前已出现过奇数次时，才认定这一次是收尾。
SOFT_QUOTES = '"\''
LATIN_CLOSERS = HARD_CLOSERS + SOFT_QUOTES


# ── 语言识别 ────────────────────────────────────────────────────────
LATIN_STOPWORDS = {
    'en': ('the', 'and', 'of', 'to', 'in', 'that', 'it', 'was', 'he', 'she',
           'for', 'with', 'as', 'his', 'her', 'not', 'you', 'but', 'they'),
    'fr': ('le', 'la', 'les', 'des', 'une', 'est', 'que', 'qui', 'dans',
           'pour', 'avec', 'pas', 'vous', 'elle', 'ne', 'se', 'ce', 'au',
           'aux', 'du', 'plus', 'mais', 'comme', 'tout'),
    'de': ('der', 'die', 'das', 'und', 'ist', 'nicht', 'ein', 'eine', 'mit',
           'sich', 'auf', 'für', 'ich', 'sie', 'zu', 'den', 'dem', 'aber',
           'auch', 'noch', 'wie', 'wenn'),
    'es': ('el', 'la', 'los', 'las', 'que', 'de', 'en', 'un', 'una', 'es',
           'por', 'con', 'para', 'no', 'se', 'su', 'al', 'como', 'pero',
           'más', 'todo', 'sus'),
    'it': ('il', 'la', 'che', 'di', 'un', 'una', 'per', 'con', 'non', 'si',
           'sono', 'del', 'come', 'anche', 'più', 'gli', 'della'),
    'pt': ('que', 'de', 'em', 'um', 'uma', 'para', 'não', 'com', 'se',
           'do', 'da', 'mais', 'como', 'mas', 'seu', 'os', 'as'),
}


def _count(text, lo, hi):
    return sum(1 for c in text if lo <= c <= hi)


# 西里尔各语言的功能词：单靠字母表分不开俄/乌/白，必须看虚词
CYR_STOPWORDS = {
    'uk': ('що', 'але', 'цей', 'ця', 'ці', 'який', 'яка', 'які', 'дуже', 'також',
           'ще', 'вже', 'її', 'його', 'мені', 'тобі', 'вони', 'вона', 'він',
           'щоб', 'якщо', 'тому', 'тільки', 'після', 'через', 'було', 'бути',
           'немає', 'ось', 'де', 'куди', 'ніж', 'між', 'під', 'над'),
    'be': ('ў', 'што', 'гэта', 'ён', 'яна', 'яны', 'але', 'яго', 'яе', 'каб',
           'вельмі', 'таксама', 'яшчэ', 'толькі', 'пасля', 'праз', 'ёсць'),
    'ru': ('что', 'как', 'это', 'она', 'они', 'его', 'её', 'уже', 'ещё', 'тоже',
           'также', 'чтобы', 'если', 'только', 'после', 'через', 'было', 'быть',
           'нет', 'между', 'под', 'над', 'очень', 'который', 'которая', 'когда'),
}
CYR_PREFORM = ('\u0463', '\u0473', '\u0462')   # ѣ ѵ Ѣ：1918 年前的俄文正字法


def _detect_cyrillic(raw):
    sample = raw[:20000]
    low = sample.lower()
    words = re.findall(r'[\w\u0400-\u04ff]+', low)
    score = {}
    for code, stops in CYR_STOPWORDS.items():
        hits = sum(1 for w in words if w in stops)
        # ў 这种单字符特征词单独算
        hits += sum(stops.count(c) for c in stops if len(c) == 1 and c in low)
        score[code] = hits
    best = max(score, key=lambda k: score[k])
    runner = sorted(score.values(), reverse=True)
    # 虚词证据足够就采信
    if score[best] >= 3 and (runner[0] - runner[1]) >= 2:
        return best
    # 旧正字法（ѣ/ѵ）是俄文的强信号
    if any(ch in sample for ch in CYR_PREFORM):
        return 'ru'
    if '\u045e' in low:
        return 'be'
    if '\u0457' in low or '\u0454' in low:
        return 'uk'
    if best != 'ru' and score[best] >= 2 and score['ru'] == 0:
        return best
    return 'ru'


def detect_lang(text):
    """Guess a language code from script mix and stopwords."""
    raw = text[:20000]
    total = max(1, len(raw))
    kana = _count(raw, '\u3040', '\u30ff')
    hangul = _count(raw, '\uac00', '\ud7af') + _count(raw, '\u1100', '\u11ff')
    han = _count(raw, '\u3400', '\u9fff')
    cyr = _count(raw, '\u0400', '\u04ff')
    lat = _count(raw, 'a', 'z') + _count(raw, 'A', 'Z') + _count(raw, '\u00c0', '\u024f')
    arab = _count(raw, '\u0600', '\u06ff')
    hebr = _count(raw, '\u0590', '\u05ff')
    grek = _count(raw, '\u0370', '\u03ff')

    if arab * 20 > total:
        return 'ar'
    if hebr * 20 > total:
        return 'he'
    if grek * 20 > total:
        return 'el'
    if kana * 50 > total:
        return 'ja'
    if hangul * 50 > total:
        return 'ko'
    if han * 20 > total:
        # 汉字为主：有假名即日语，有谚文即韩语，否则中文
        return 'zh'
    if cyr * 20 > total:
        return _detect_cyrillic(raw)
    if lat * 20 > total:
        sample = raw.lower()
        words = re.findall(r"[a-z\u00c0-\u024f']+", sample)
        score = {}
        for code, stops in LATIN_STOPWORDS.items():
            score[code] = sum(1 for w in words if w in stops)
        best = max(score, key=lambda k: score[k]) if score else 'en'
        if score.get(best, 0) >= max(3, len(words) // 80):
            return best
        if re.search(r'[àâçéèêëîïôùûœ]', sample):
            return 'fr'
        if re.search(r'[äöüß]', sample):
            return 'de'
        if re.search(r'[ñáíóúü¿¡]', sample):
            return 'es'
        return 'en'
    return 'en'


LAYOUT = {
    'ru': 'cyrl', 'uk': 'cyrl', 'be': 'cyrl', 'bg': 'cyrl', 'sr': 'cyrl',
    'el': 'cyrl', 'mk': 'cyrl', 'kk': 'cyrl',
    'ja': 'jpn', 'ko': 'kor', 'zh': 'cjk',
    'ar': 'rtl', 'he': 'rtl', 'fa': 'rtl', 'ur': 'rtl',
}
CJK_LANGS = ('ja', 'ko', 'zh')
LANG_ALIASES = {
    'russian': 'ru', '俄语': 'ru', '俄文': 'ru',
    'japanese': 'ja', '日本語': 'ja', '日语': 'ja', '日文': 'ja', 'jp': 'ja',
    'korean': 'ko', '한국어': 'ko', '韩语': 'ko', '韩文': 'ko', 'kr': 'ko',
    'chinese': 'zh', '中文': 'zh', '汉语': 'zh', 'cn': 'zh',
    'english': 'en', 'eng': 'en', 'french': 'fr', 'français': 'fr', '法语': 'fr',
    'german': 'de', 'deutsch': 'de', '德语': 'de',
    'spanish': 'es', 'español': 'es', 'italian': 'it', 'italiano': 'it',
    'portuguese': 'pt', 'latin': 'la',
}


def layout_of(lang):
    if lang in ('latn', 'cyrl', 'cjk', 'jpn', 'kor', 'rtl'):
        return lang
    return LAYOUT.get(lang, 'latn')


def read_text(path):
    for enc in ('utf-8', 'utf-8-sig', 'shift_jis', 'cp932', 'euc-jp', 'gbk',
                'big5', 'cp1251', 'koi8-r', 'latin-1'):
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, LookupError):
            continue
    sys.exit('cannot decode file: ' + path)


# ── 拉丁 / 西里尔切分 ───────────────────────────────────────────────
def abbr_set_for(lang):
    extra = {
        'fr': FRA_ABBR, 'ru': RUS_ABBR, 'uk': RUS_ABBR, 'be': RUS_ABBR,
        'bg': RUS_ABBR, 'de': DEU_ABBR, 'es': SPA_ABBR, 'it': ITA_ABBR,
        'pt': SPA_ABBR, 'ko': KOR_ABBR, 'en': ENG_ABBR,
    }.get(lang, set())
    return BASE_ABBR | extra


def _word_before(p, i):
    """紧挨在 p[i]（一个句点）之前的那个词，用于缩写判断。"""
    m = re.search(r'([^\W\d_]+)$', p[:i], re.UNICODE)
    return m.group(1) if m else ''


def _skip_spaces(p, j, n):
    while j < n and p[j] in SPACES:
        j += 1
    return j


def split_latin(p, lang='en'):
    """Split on . ! ? … while protecting abbreviations, decimals, initials,
    and quoted speech (a full stop inside « … » does not end the sentence)."""
    abbr = abbr_set_for(lang)
    sents, start, i, n = [], 0, 0, len(p)
    stack = []
    limit = 600                       # 引号不闭合时的兜底：不让整段并成一句
    while i < n:
        c = p[i]
        act = _quote_action(c, stack, p, i) if (c in QUOTE_CHARS or c in SOFT_QUOTES) else None
        if act == 'close':
            _try_pop(stack, c)
            i += 1
            continue
        if act == 'open':
            stack.append(c)
            i += 1
            continue
        if c not in LATIN_END:
            i += 1
            continue
        # 收尾：连续终止符 + 闭引号（含法语 ". »" 这种带空格的写法）
        j = i + 1
        while j < n:
            c2 = p[j]
            act2 = _quote_action(c2, stack, p, j) if (c2 in QUOTE_CHARS or c2 in SOFT_QUOTES) else None
            if c2 in LATIN_END:
                j += 1
            elif act2 == 'close' and c2 in LATIN_CLOSERS:
                _try_pop(stack, c2)
                j += 1
            elif act2 == 'open':
                break                  # 下一句的开引号，不吞
            elif c2 in LATIN_CLOSERS:
                if c2 in SOFT_QUOTES:
                    # 开闭同形：本段里已经出现过奇数次才说明这个是收尾的
                    if p.count(c2, start, j) % 2 == 1:
                        j += 1
                    else:
                        break
                else:
                    j += 1
            elif c2 in SPACES and j + 1 < n and p[j + 1] in LATIN_CLOSERS:
                j += 1
            else:
                break
        k = _skip_spaces(p, j, n)
        if p[i] == '.' and j < n:
            # 只看紧挨着这个点的那个词，绝不能用 p[start:i+1] 整段去匹配——
            # 否则段首出现过一次缩写，后面每一句都会被当成缩写而不肯断句。
            word = _word_before(p, i)
            if word and (word.lower() in abbr or (len(word) == 1 and word.isupper())):
                i = j
                continue
            if i > 0 and p[i - 1].isdigit() and j < n and p[j].isdigit():
                i = j
                continue
            # 缩写后紧跟数字（No. 5 / г. 1805 / t. 2）一定不是句末
            if k < n and p[k].isdigit() and len(word) <= 3:
                i = j
                continue
        # 引号还没闭合 → 句号只是引用内部的一部分。
        # 注意 j 处的闭引号已在上面弹过栈，这里看的是「收尾之后」的状态：
        # 收尾字符里若含闭引号，说明引用到此结束，可以断句。
        closed_here = any(_is_closer_char(p[t]) for t in range(i + 1, j))
        if stack and not closed_here and (j - start) < limit:
            i = j
            continue
        # 「…！」他说 / « … » dit-il / — спросил он：话还没说完。
        # 必须排在“小写继续”之前——said he. 正是小写开头。
        if k < n and _attribution_follows(p, j, lang, start):
            i = j
            continue
        # 句号后接小写或逗号 → 缩写 / 省略，不是句末
        if k < n and (p[k].islower() or p[k] == ','):
            i = j
            continue
        chunk = p[start:j].strip()
        if chunk:
            sents.append(chunk)
        start = i = j
    tail = p[start:].strip()
    if tail:
        sents.append(tail)
    return sents


# ── 中日韩切分（含引号配对与会话语尾） ──────────────────────────────
JA_END = '\u3002\uff01\uff1f!\u2026\u203d'
JA_CLOSERS = '\u300d\u300f\uff09\uff3d\u3011\u3009\u300b\u201d\u2019"\')]'
KO_END = '.!?\u2026\u203d\uff01\uff1f'
KO_CLOSERS = '"\'\u201d\u2019\u300d\u300f\uff09)]'
ZH_END = '\u3002\uff01\uff1f!\u2026\u203d'
ZH_CLOSERS = '\u300d\u300f\uff09\uff3d\u3011\u201d\u2019"\')]'
QUOTE_SOFT_LIMIT = {'ja': 150, 'ko': 150, 'zh': 150}   # 引号内短于这个长度就不拆
CLOSING_QUOTES = set(QUOTE_PAIRS.values())
# 引号闭合后紧跟的“说话人标记”，此时不能断句：「…」と言った。/ "...!" 하고 말했다.
ATTRIBUTION = {
    'ja': ('と', '、と', 'と言', 'と思', 'と答', 'と怒', 'と叫', 'と呟', 'とつぶや'),
    'zh': ('说道', '说', '问', '答', '道', '喊', '叫', '想'),
    'ko': ('하고', '라고', '라며', '하며', '그리고', '고 ', '라도'),
}
# 俄语对话用破折号引出说话人：— … ? — спросил он.
RU_DASH_ATTR = ('\u2014 ', '\u2013 ', '\u2014\u00a0')
# 英/法：! » dit-il. / ?" said she. / . » murmura-t-il.
LATIN_ATTR_START = ('dit', 'dis', 'dit-il', 'dit-elle', 'r\u00e9pond', 'reprit',
                    'murmur', 'ecria', 'ajouta', 'poursuivit',
                    'said', 'asked', 'replied', 'answered', 'cried', 'whispered',
                    'muttered', 'exclaimed', 'added', 'continued', 'thought')


def _is_closer_char(c):
    """这个字符能否充当收尾引号（' 除外：它绝大多数时候是撇号）。"""
    return c in CLOSING_QUOTES or (c in SOFT_QUOTES and c != "'")


def _try_pop(stack, c):
    if stack and (QUOTE_PAIRS.get(stack[-1]) == c or stack[-1] == c):
        stack.pop()


def _quote_action(c, stack, text=None, pos=0):
    """Classify a quote char: 'close' | 'open' | None.

    · 「」『』“”«» 这类开闭不同形的：开字形入栈，闭字形弹栈。
    · " 这种开闭同形的：按本段内已出现次数的奇偶判断这一次是开还是闭。
    · ' 一律当撇号，不参与配对（C'est / don't 太常见，误判代价太大）。
    """
    if stack and QUOTE_PAIRS.get(stack[-1]) == c:
        return 'close'
    if c in QUOTE_PAIRS:
        return 'open'
    if c in SOFT_QUOTES and text is not None and c != "'":
        return 'close' if text.count(c, 0, pos) % 2 else 'open'
    if c in CLOSING_QUOTES:
        return 'close'          # 孤零零的收尾引号：当闭合处理，不入栈
    return None


# 中文的语序是「…」+ 主语 + 动词（他说。/ 张三答道。），动词前允许夹一个短主语
ZH_ATTR_VERBS = ('说道', '说', '问', '答', '道', '喊', '叫', '想', '回答', '嘟囔', '笑道')
ZH_SUBJ = ('他', '她', '我', '你', '它', '他们', '她们', '大家', '众人', '那人', '此人')


def _attribution_follows(p, j, lang, start=0):
    """句子收尾之后是否还跟着「谁说的」——是的话这句话还没完。

    只在本句确实以「闭引号」收尾时才认这条规则（俄语的破折号对话除外），
    否则「她问。老张答道：…」这种下一句会被误并进来。
    """
    chunk = p[start:j].rstrip()
    quote_closed = bool(chunk) and _is_closer_char(chunk[-1])
    k = _skip_spaces(p, j, len(p))
    rest = p[k:k + 14]
    if quote_closed and any(rest.startswith(pre) for pre in ATTRIBUTION.get(lang, ())):
        return True
    if lang == 'zh' and quote_closed:
        # 「…」他说。 / 「…」张三答道。：动词前允许夹一个短主语
        span = re.split(r'[\u3002\uff01\uff1f\u2026]', p[k:k + 12])[0]
        return any(v in span for v in ZH_ATTR_VERBS)
    if lang in ('ru', 'uk', 'be'):
        for d in RU_DASH_ATTR:
            if p.startswith(d, k):
                # 破折号后跟小写词才是归属（— спросил он）；
                # 大写开头（— Здравствуйте!）是同一行里新起的一句对白，必须断开
                m = re.match(re.escape(d) + r'\s*(\w)', p[k:])
                return bool(m) and m.group(1).islower()
        return False
    if quote_closed:
        low = rest.lower()
        return any(low.startswith(pre) for pre in LATIN_ATTR_START)
    return False


def split_cjk(p, enders, closers, abbr=frozenset(), limit=120, lang='zh'):
    """Split CJK text. Quoted speech is not torn from its attribution:
    「そんなことはない！」と怒鳴った。 / "...!" 하고 말했다. stay one sentence."""
    sents, start, i, n = [], 0, 0, len(p)
    stack = []
    while i < n:
        c = p[i]
        act = _quote_action(c, stack, p, i)
        if act == 'close':
            _try_pop(stack, c)
            i += 1
            continue
        if act == 'open':
            stack.append(c)
            i += 1
            continue
        if c not in enders:
            i += 1
            continue
        j = i + 1
        while j < n:
            c2 = p[j]
            act2 = _quote_action(c2, stack, p, j)
            if c2 in enders:
                j += 1
            elif act2 == 'close' and c2 in closers:
                _try_pop(stack, c2)
                j += 1
            elif act2 == 'open':
                break                  # 下一句的开引号，不吞
            elif c2 in closers:
                j += 1
            elif c2 in SPACES and j + 1 < n and p[j + 1] in closers:
                j += 1
            else:
                break
        if c == '.' and j < n:
            if i > 0 and p[i - 1].isdigit() and p[j].isdigit():
                i = j
                continue
            word = _word_before(p, i)
            if word and abbr and word.lower() in abbr:
                i = j
                continue
        # 「…」と彼は言った。 / "…" 하고 말했다.：引号刚闭合，后面还跟着说话人
        if _attribution_follows(p, j, lang, start):
            i = j
            continue
        closed_here = any(_is_closer_char(p[t]) for t in range(i + 1, j))
        if stack and not closed_here and (j - start) < limit:
            i = j                      # 引号内的短句不拆
            continue
        chunk = p[start:j].strip()
        if chunk:
            sents.append(chunk)
        start = i = j
    tail = p[start:].strip()
    if tail:
        sents.append(tail)
    return sents


def splitter_for(lang):
    if lang == 'ja':
        return lambda p: split_cjk(p, JA_END, JA_CLOSERS, limit=QUOTE_SOFT_LIMIT['ja'], lang='ja')
    if lang == 'ko':
        return lambda p: split_cjk(p, KO_END, KO_CLOSERS, KOR_ABBR,
                                   limit=QUOTE_SOFT_LIMIT['ko'], lang='ko')
    if lang == 'zh':
        return lambda p: split_cjk(p, ZH_END, ZH_CLOSERS, limit=QUOTE_SOFT_LIMIT['zh'], lang='zh')
    return lambda p: split_latin(p, lang)


# ── 段落与换行还原 ──────────────────────────────────────────────────
SENT_END = '.!?\u2026\u203d\u061f\u3002\uff01\uff1f'
TRAILING = '"\'\u201d\u2019\u300d\u300f)\uff09\u3011\u00bb]'


MARKUP_ONLY = re.compile(r'^[\s_*#=\u2014\u2013\-\.~\u30fc]+$')

# ── 青空文库注记（ルビ・入力者注）──────────────────────────────────
# 漢字《かんじ》 / ｜漢字《かんじ》 / ［＃「…」に傍点］ / ［＃５字下げ］
AOZORA_RUBY = re.compile(r'\u300a[^\u300a\u300b]*\u300b')
AOZORA_NOTE = re.compile(r'\uff3b\uff03[^\uff3b\uff3d]*\uff3d')
AOZORA_BAR = re.compile(r'\uff5c(?=[^\uff5c\n]*\u300a)')
AOZORA_HINT = re.compile(r'(\u300a[^\u300a\u300b]*\u300b|\uff3b\uff03|\uff5c[^\uff5c\n]*\u300a)')


def strip_aozora(text, lang='ja'):
    """去掉青空文库的ルビ与输入者注，只留正文。
    漢字《かんじ》→漢字；｜漢字《かんじ》→漢字；［＃…］整段删除。"""
    if lang not in ('ja', 'zh'):
        return text
    text = AOZORA_NOTE.sub('', text)
    text = AOZORA_RUBY.sub('', text)
    text = AOZORA_BAR.sub('', text)
    # 注记删除后可能留下成对空白/空行
    text = re.sub(r'[ \t\u3000]+(?=\n)', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


def looks_aozora(text):
    return len(AOZORA_HINT.findall(text[:200000])) >= 3


def _drop_markup_lines(lines):
    """丢掉 `_` `*` `***` `---` 这类纯排版标记行（斜体标记、分隔线）。"""
    return [ln for ln in lines if not MARKUP_ONLY.match(ln)]


def _join_para(lines, lang):
    """把折行的若干行接回一个自然段，保留该语言真正需要的空白。"""
    lines = [ln.strip() for ln in lines if ln.strip()]
    if not lines:
        return ''
    if lang in ('ja', 'zh'):
        return ''.join(lines)          # 行首行尾的空白是折行留下的；行内全角空格保留
    return re.sub(r'[ \t\u3000]+', ' ', ' '.join(lines)).strip()


def _sentence_final(line):
    """这一行是不是「一句话写完了」。行尾的引号、括号不算数，要看里面的标点。"""
    s = line.rstrip()
    while s and s[-1] in TRAILING:
        s = s[:-1]
    return bool(s) and s[-1] in SENT_END


def _short_limit(lang):
    return 22 if lang in CJK_LANGS else 44


def _should_join(cur, nxt, lang):
    """上一行没写完 → 下一行是它的继续（Gutenberg / 出版社 txt 的硬换行）。"""
    if _sentence_final(cur):
        return False
    # 短行 + 短行：标题、署名、章节号一类，各占一行，别粘成一句
    if len(cur) <= _short_limit(lang) and len(nxt) <= _short_limit(lang):
        return False
    return True


def _pairwise_paragraphs(lines, lang):
    paras = []
    for ln in lines:
        if paras and _should_join(paras[-1][-1], ln, lang):
            paras[-1].append(ln)
        else:
            paras.append([ln])
    return [_join_para(p, lang) for p in paras]


def _indent_paragraphs(lines, lang):
    """青空文库式：自然段以行首全角空格起头，续行顶格。识别不出就返回 None。"""
    if len(lines) < 3 or lang not in ('ja', 'zh'):
        return None
    body = lines[1:]
    marked = sum(1 for ln in body if ln[:1] == '\u3000')
    if marked < max(1, int(len(body) * 0.6)):
        return None
    paras = []
    for ln in lines:
        if ln[:1] == '\u3000' or not paras:
            paras.append([ln])
        else:
            paras[-1].append(ln)
    return [_join_para(p, lang) for p in paras]


def plan_chunks(sentences, meta, a):
    """把全文切成 N 块均衡切片，直接写入 sentences-K.json，并打印并发计划。

    切片由这里一次落盘、id 从此固定：并发实例只读自己的切片文件，
    不再各自重切全文——即使中途原文被改动，各实例的句子也不会错位。"""
    total = len(sentences)
    n = max(1, min(a.plan, total))
    base, extra = divmod(total, n)
    start, files, ranges = 1, [], []
    for i in range(n):
        limit = base + (1 if i < extra else 0)
        sel = [s for s in sentences if start <= s['id'] < start + limit]
        name = 'sentences-%d.json' % (i + 1)
        with open(os.path.join(a.plan_dir, name), 'w', encoding='utf-8') as f:
            json.dump(dict(meta, sentences=sel), f, ensure_ascii=False, indent=1)
        files.append(name)
        ranges.append('%s: id %d-%d' % (name, start, start + limit - 1))
        start += limit
    print('total %d sentences -> %d slice file(s) written to %s:'
          % (total, n, os.path.abspath(a.plan_dir)))
    for r in ranges:
        print('  ' + r)
    datas = ['data-%d.json' % (i + 1) for i in range(n)]
    for k in range(n):
        print('instance %d: annotate %s into %s, then check: '
              'check_data.py --data %s --sentences %s'
              % (k + 1, files[k], datas[k], datas[k], files[k]))
    merge = (' --merge ' + ' '.join(datas[1:])) if n > 1 else ''
    build = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'build_reader.py')
    print('then merge and build (the reader will show coverage):')
    print('  %s %s --data %s%s --total %d --out "书名-精读.html"'
          % (sys.executable, build, datas[0], merge, total))


def lines_to_paragraphs(lines, lang):
    """行 → 自然段。返回 (段落列表, 是否做了折行还原)。"""
    lines = _drop_markup_lines([ln.strip() for ln in lines if ln.strip()])
    if not lines:
        return [], False
    by_indent = _indent_paragraphs(lines, lang)
    if by_indent is not None:
        return by_indent, len(by_indent) < len(lines)
    paras = _pairwise_paragraphs(lines, lang)
    return paras, len(paras) < len(lines)


def paragraph_texts(text, lang, mode='auto'):
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'[ \t]+\n', '\n', text)
    blocks = [b for b in re.split(r'\n\s*\n', text) if b.strip()]
    all_lines = [ln for ln in text.split('\n') if ln.strip()]

    if mode == 'blank':
        paras, unwrapped = [], False
        for b in blocks:
            p, u = lines_to_paragraphs(b.split('\n'), lang)
            paras.extend(p)
            unwrapped = unwrapped or u
        return paras, ('blank+unwrap' if unwrapped else 'blank')

    if mode == 'line':
        paras, unwrapped = lines_to_paragraphs(all_lines, lang)
        return paras, ('line+unwrap' if unwrapped else 'line')

    # auto：有空行就按空行分段，块内再做折行还原；整篇没有空行则整体处理
    if len(blocks) > 1:
        paras, unwrapped = [], False
        for b in blocks:
            p, u = lines_to_paragraphs(b.split('\n'), lang)
            paras.extend(p)
            unwrapped = unwrapped or u
        return paras, ('blank+unwrap' if unwrapped else 'blank')
    paras, unwrapped = lines_to_paragraphs(all_lines, lang)
    if len(paras) <= 1 and len(all_lines) > 1:
        return paras, 'joined'
    return paras, ('line+unwrap' if unwrapped else 'line')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input')
    ap.add_argument('--start', type=int, default=1,
                    help='first sentence id to keep (1-based)')
    ap.add_argument('--limit', type=int, default=0,
                    help='max number of sentences to keep (0 = all)')
    ap.add_argument('--out', help='write JSON here instead of stdout')
    ap.add_argument('--lang', help='force a language code (ru/fr/ja/ko/en/zh/…)')
    ap.add_argument('--para', choices=('auto', 'blank', 'line'), default='auto',
                    help='paragraph detection: blank line / every line / auto')
    ap.add_argument('--ruby', choices=('auto', 'strip', 'keep'), default='auto',
                    help='strip Aozora ruby/editor notes (auto = strip when detected)')
    ap.add_argument('--plan', type=int, default=0, metavar='N',
                    help='write N balanced slice files (sentences-1.json … sentences-N.json) '
                         'and print the concurrent plan, then exit')
    ap.add_argument('--plan-dir', default='.', metavar='DIR',
                    help='directory for --plan slice files (default: current directory)')
    a = ap.parse_args()

    text = read_text(a.input)
    raw_lang = (a.lang or '').strip().lower()
    lang = LANG_ALIASES.get(raw_lang, raw_lang) or detect_lang(text)
    ruby = a.ruby == 'strip' or (a.ruby == 'auto' and looks_aozora(text))
    if ruby:
        text = strip_aozora(text, lang)
    split = splitter_for(lang)
    paras, para_mode = paragraph_texts(text, lang, a.para)

    sentences = []
    for pid, para in enumerate(paras):
        for s in split(para):
            s = re.sub(r'\s+', ' ', s).strip()
            # 只剩标点/引号的碎片并回上一句，别让它单独成句
            if s and not re.search(r'[^\W_]', s):
                if sentences and sentences[-1]['para'] == pid + 1:
                    sentences[-1]['text'] += ' ' + s
                continue
            if s:
                sentences.append({'id': len(sentences) + 1, 'text': s,
                                  'para': pid + 1})

    if a.plan and a.plan > 0:
        meta = {'lang': lang, 'layout': layout_of(lang), 'total': len(sentences),
                'para_mode': para_mode}
        if ruby:
            meta['ruby'] = 'stripped'
        os.makedirs(a.plan_dir, exist_ok=True)
        plan_chunks(sentences, meta, a)
        return

    selected = [s for s in sentences if s['id'] >= a.start]
    if a.limit:
        selected = selected[:a.limit]

    out = {'lang': lang, 'layout': layout_of(lang), 'total': len(sentences),
           'para_mode': para_mode, 'sentences': selected}
    if ruby:
        out['ruby'] = 'stripped'
    js = json.dumps(out, ensure_ascii=False, indent=1)
    if a.out:
        with open(a.out, 'w', encoding='utf-8') as f:
            f.write(js)
        kept = '{}-{}'.format(selected[0]['id'], selected[-1]['id']) if selected else 'none'
        print('lang={} layout={} para={}{} total={} kept sentences {} -> {}'.format(
            lang, out['layout'], para_mode, ' ruby=stripped' if ruby else '',
            len(sentences), kept, a.out))
    else:
        print(js)


if __name__ == '__main__':
    main()
