#!/usr/bin/env python3
"""Merge per-sentence annotations into the interactive reader template.

Usage:
  python3 build_reader.py --data data.json --out reader.html [--template PATH]

data.json schema (all strings, ids must match split_sentences.py output):
{
  "title": "Pride and Prejudice · Chapter 1",
  "subtitle": "Jane Austen",            # optional
  "lang": "latin"|"cjk",                 # controls inter-sentence spacing
  "sentences": [
    {
      "id": 1, "text": "...", "para": 1, "translation": "...",
      "words":   [{"w": "word", "p": "phonetic", "m": "meaning", "n": "note"}],
      "grammar": [{"t": "point", "d": "explanation"}],
      "culture": [{"t": "topic", "d": "content"}]
    }
  ]
}
words/grammar/culture and every sub-field except w/m/d are optional.
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TEMPLATE = os.path.join(HERE, '..', 'assets', 'reader_template.html')


def fail(msg):
    sys.exit('build_reader: ' + msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--template', default=DEFAULT_TEMPLATE)
    a = ap.parse_args()

    with open(a.data, encoding='utf-8') as f:
        data = json.load(f)

    if not isinstance(data.get('sentences'), list) or not data['sentences']:
        fail('data.json needs a non-empty "sentences" list')
    if not data.get('title'):
        fail('data.json needs a "title"')
    for i, s in enumerate(data['sentences']):
        for k in ('id', 'text', 'para'):
            if k not in s:
                fail('sentences[%d] is missing "%s"' % (i, k))
        if not str(s['text']).strip():
            fail('sentences[%d] (id=%s) has empty text' % (i, s.get('id')))

    with open(a.template, encoding='utf-8') as f:
        tpl = f.read()
    for token in ('__DATA__', '__TITLE__'):
        if token not in tpl:
            fail('template is missing the %s placeholder' % token)

    js = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    # keep the inline JSON from prematurely closing its <script> tag
    js = js.replace('</', '<\\/')

    html = tpl.replace('__TITLE__', str(data['title']).replace('<', ''))
    html = html.replace('__DATA__', js)

    out = os.path.abspath(a.out)
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print('reader written: %s (%d sentences)' % (out, len(data['sentences'])))


if __name__ == '__main__':
    main()
