#!/usr/bin/env python3
"""从 explorateur/personas/personas.json 蒸馏出阅读器用的声音花名册。

人设目录是人设与 voiceId 的唯一事实源；这里只做**读取与裁剪**，
不新增、不改写任何人物参数——人设那边改了，重跑本脚本即可。
生成物：assets/voices.json
"""
import json
import os
import re
import sys

SRC = '/Users/han/coding/personal/explorateur/personas/personas.json'
CASTING = '/Users/han/coding/personal/explorateur/personas/casting.md'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'voices.json')


def pct(s):
    """'+7%' / '-6%' → 0.07 / -0.06"""
    m = re.match(r'^([+-]?)(\d+(?:\.\d+)?)%$', (s or '').strip())
    if not m:
        return 0.0
    v = float(m.group(2)) / 100.0
    return -v if m.group(1) == '-' else v


def hz(s):
    """'+5Hz' / '-3Hz' → 5.0 / -3.0"""
    m = re.match(r'^([+-]?)(\d+(?:\.\d+)?)Hz$', (s or '').strip(), re.I)
    if not m:
        return 0.0
    v = float(m.group(2))
    return -v if m.group(1) == '-' else v


def main():
    if not os.path.exists(SRC):
        sys.exit('personas.json not found: %s' % SRC)
    d = json.load(open(SRC, encoding='utf-8'))
    src = d['personas']

    personas, locales = {}, {}
    for p in src:
        pid = p['id']
        v = p['voice']
        locales.setdefault(p['locale'], {})[p['energy']] = pid
        personas[pid] = {
            'locale': p['locale'],
            'gender': p['gender'],
            'energy': p['energy'],
            'name': p['name']['native'],
            'gloss': p['name'].get('gloss', ''),
            'archetype': p.get('archetype', ''),
            'quirk': p.get('quirk', ''),
            'voiceId': v['voiceId'],
            'rate': pct(v.get('rate', '0%')),
            'pitch': hz(v.get('pitch', '0Hz')),
            'timbre': v.get('timbre', ''),
        }

    # casting.md 的槽位约定：活泼者当 A（求知者/学习者视角），沉稳者当 B（向导/母语者视角）
    roles = {'lively': 'A', 'steady': 'B'}
    for loc, pair in locales.items():
        for energy, pid in pair.items():
            personas[pid]['role'] = roles[energy]

    out = {
        '$comment': (
            '阅读器人设花名册，由 %s 蒸馏而来，不要手工编辑——'
            '改人设请改 personas.json 后重跑 scripts/build_voices.py。'
            '人设目录是人设与 voiceId 的唯一事实源。' % SRC),
        'source': SRC,
        'engine': 'edge-tts',
        'note': (
            'voiceId 是 edge-tts（微软 Neural 声库）的 id，只在**离线烘焙音频**时直接可用。'
            '静态阅读器默认走浏览器 SpeechSynthesis，此时按 locale+gender 在系统声库里选最接近的音色，'
            '并套用该人设的语速/音高增量；界面会如实显示「人设 → 实际使用的系统音色」。'),
        # 情绪增量沿用 voice.md §1：有效参数 = 个人基线 + 情绪增量
        'moods': {
            'neutral': {'rate': 0.00, 'pitch': 0.0, 'label': '平叙'},
            'teach': {'rate': -0.15, 'pitch': 0.0, 'label': '领读'},
            'encouraging': {'rate': -0.05, 'pitch': 2.0, 'label': '鼓励'},
        },
        # 场景 → 该读哪个人设、什么情绪
        'scenes': {
            'text': {'locale': '@book', 'mood': 'neutral',
                     'label': '原文',
                     'hint': '由这本书的原文语种人设朗读，叙述与对白同声。'},
            'gloss': {'locale': 'zh-CN', 'mood': 'teach',
                      'label': '译文',
                      'hint': '由中文人设领读，语速放慢便于跟读。'},
        },
        'locales': locales,
        'personas': personas,
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('wrote %s: %d personas across %d locales'
          % (OUT, len(personas), len(locales)))


if __name__ == '__main__':
    main()
