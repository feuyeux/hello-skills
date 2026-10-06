#!/usr/bin/env python3
"""TTS must actually *use* the persona, not just print its name next to a button.

The persona file records a gender (``female`` / ``male``) and a neural voiceId.
The browser, however, can only offer whatever voices the machine happens to
have. These tests pin down the two ways that goes wrong:

1. the persona gender never reaching the picker -- ``female`` compared against
   ``f`` fails silently, so every voice looks "wrong" and the persona-first
   switch becomes a no-op;
2. the picker grabbing a 1980s Eloquence robot voice, or a voice of the wrong
   gender, while the UI still claims Chloé is reading.

The template's TTS block is evaluated for real against a stubbed voice list,
so the assertions below exercise shipped code rather than a re-implementation.
Requires node; skipped (not failed) when node is absent.

Run:  python3 -m unittest discover -s tests
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, '..', 'assets')
TEMPLATE = os.path.join(ASSETS, 'reader_template.html')
VOICES = os.path.join(ASSETS, 'voices.json')

# 模拟一台典型的 macOS：法语只有男声（另有加拿大法语女声），
# 中文只有女声，且两类机器人都装着 Eloquence。
STUB_VOICES = [
    ('Amélie', 'fr-CA', False),
    ('Thomas (French (France))', 'fr-FR', False),
    ('Eddy (French (France))', 'fr-FR', True),
    ('Tingting (Chinese (China mainland))', 'zh-CN', False),
    ('Grandpa (Chinese (China mainland))', 'zh-CN', True),
]

PROBE = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const voices = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const sys = JSON.parse(fs.readFileSync(process.argv[4], 'utf8'));
var DATA = {voices: voices};
var ttsPrefs = {textVoice: 'A', glossVoice: 'A', rate: '正常', voicePick: '人设'};
function esc(x) { return String(x == null ? '' : x); }
var vinfo = {textContent: '', innerHTML: ''};
var document = {getElementById: (id) => id === 'voiceinfo' ? vinfo : null,
                querySelectorAll: () => [], addEventListener: () => {}};
var window = {speechSynthesis: {getVoices: () => sys, cancel() {}, speak() {},
               addEventListener() {}, speaking: false, paused: false}};
var TTS = eval(src + '\n;TTS');
if (!TTS) { console.log(JSON.stringify({fatal: 'TTS block returned null'})); process.exit(1); }
TTS.load();
const out = {picks: {}};
for (const mode of ['人设', '标准']) {
  for (const pid of ['chloe', 'theo', 'xiaoman', 'jiangyuan']) {
    ttsPrefs.voicePick = mode;
    const p = TTS.V.personas[pid];
    if (!p) continue;
    const g = p.gender === 'female' ? 'f' : 'm';
    const r = TTS.pickVoice(p.locale, g);
    out.picks[pid + '/' + mode] = {
      lang: p.locale, gender: p.gender, want: g,
      voice: r.v ? r.v.name : null, vlang: r.v ? r.v.lang : null,
      miss: r.miss.slice()};
  }
}
ttsPrefs.voicePick = '人设'; TTS.paint();
out.info = vinfo.innerHTML;
console.log(JSON.stringify(out));
"""


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def extract_tts_block():
    src = read(TEMPLATE)
    i = src.index('var TTS = (function () {')
    j = src.index('})();', i) + len('})();')
    return src[i:j]


@unittest.skipIf(shutil.which('node') is None, 'node not installed')
class PersonaVoicePicking(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='fcr-tts-')
        cls.js = os.path.join(cls.tmp, 'tts.js')
        with open(cls.js, 'w', encoding='utf-8') as f:
            f.write(extract_tts_block())
        voices_path = os.path.join(cls.tmp, 'voices.json')
        shutil.copy(VOICES, voices_path)
        sysv = []
        for name, lang, robot in STUB_VOICES:
            base = 'com.apple.voice.eloquence' if robot else 'com.apple.voice.compact'
            sysv.append({'name': name, 'lang': lang, 'localService': True,
                         'default': False, 'voiceURI': '%s.%s.%s' % (base, lang, name)})
        sysv_path = os.path.join(cls.tmp, 'sysvoices.json')
        with open(sysv_path, 'w', encoding='utf-8') as f:
            json.dump(sysv, f, ensure_ascii=False)
        probe = os.path.join(cls.tmp, 'probe.js')
        with open(probe, 'w', encoding='utf-8') as f:
            f.write(PROBE)
        p = subprocess.run(['node', probe, cls.js, voices_path, sysv_path],
                           capture_output=True, text=True)
        cls.raw = p.stdout + p.stderr
        try:
            cls.res = json.loads(p.stdout)
        except ValueError:
            raise AssertionError('probe did not return JSON:\n' + cls.raw)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def pick(self, pid, mode):
        return self.res['picks']['%s/%s' % (pid, mode)]

    # --- the persona gender has to survive the trip ------------------------

    def test_persona_first_finds_a_matching_gender(self):
        """A female fr-FR persona must reach a female voice.

        `female` vs `f` failing to compare is the bug this pins: it made every
        voice look mismatched, so persona-first and region-first behaved
        identically and the switch was dead.
        """
        r = self.pick('chloe', '人设')
        self.assertEqual(r['want'], 'f')
        self.assertEqual(r['voice'], 'Amélie')
        self.assertEqual(r['miss'], ['region'])       # 女声找对了，只是跨了地区

    def test_persona_first_keeps_an_exact_match_when_it_exists(self):
        r = self.pick('theo', '人设')
        self.assertEqual(r['voice'], 'Thomas (French (France))')
        self.assertEqual(r['vlang'], 'fr-FR')
        self.assertEqual(r['miss'], [])

    def test_chinese_personas_map_onto_the_real_voice(self):
        self.assertEqual(self.pick('xiaoman', '人设')['voice'].split(' (')[0],
                         'Tingting')
        self.assertEqual(self.pick('xiaoman', '人设')['miss'], [])

    def test_an_unavailable_gender_is_flagged_not_hidden(self):
        """本机没有中文男声，江远只能落到女声——必须说出来。"""
        r = self.pick('jiangyuan', '人设')
        self.assertEqual(r['want'], 'm')
        self.assertIn('gender', r['miss'])

    def test_robot_voices_never_win_over_real_ones(self):
        """Eloquence 即使碰巧猜对性别也不能赢。"""
        for pid in ('chloe', 'theo', 'xiaoman', 'jiangyuan'):
            for mode in ('人设', '标准'):
                r = self.pick(pid, mode)
                self.assertNotIn('Eddy', r['voice'] or '')
                self.assertNotIn('Grandpa', r['voice'] or '')

    # --- region-first is a real, different mode ----------------------------

    def test_region_first_prefers_the_book_locale(self):
        r = self.pick('chloe', '标准')
        self.assertEqual(r['voice'], 'Thomas (French (France))')
        self.assertIn('gender', r['miss'])            # 明说这是男声
        self.assertNotEqual(self.pick('chloe', '人设')['voice'],
                            self.pick('chloe', '标准')['voice'])

    # --- the panel must expose the choice ---------------------------------

    def test_panel_offers_the_pick_mode_switch(self):
        self.assertIn('id="seg-pick"', read(TEMPLATE))

    # --- and the reader must say what it ended up with --------------------

    def test_voiceinfo_names_the_reader_gender_and_the_real_voice(self):
        info = self.res['info']
        self.assertIn('Chloé', info)
        self.assertIn('女', info)
        self.assertIn('Amélie', info)
        self.assertIn('fr-CA', info)

    def test_voiceinfo_does_not_claim_the_neural_voice_it_cannot_produce(self):
        """界面必须把「系统音」和「人设指定的神经音色」分开说。"""
        info = self.res['info']
        self.assertIn('DeniseNeural', info)            # 目标，如实标出
        self.assertIn('烘焙', info)                    # 并说明它当前没被用上


if __name__ == '__main__':
    unittest.main()