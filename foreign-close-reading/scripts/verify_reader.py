#!/usr/bin/env python3
"""Open the built reader in a headless browser and check that it actually works.

Usage:
  python3 verify_reader.py READER.html [READER.html ...] [--shots DIR]

Checks (pure stdlib — drives Chrome/Chromium via CDP over a tiny built-in
WebSocket client; installs nothing. If the `websockets` package happens to be
installed it is used instead, but nothing is required):
  · no JS errors, and no "undefined" / "[object Object]" / "不支持" in any card
  · every sentence opens exactly one card, and the card sits directly under the
    clicked sentence (also inside a very long paragraph)
  · learned sentences carry no underline/highlight, only a dimmed colour
  · ←/→/Esc keyboard navigation
  · every theme applies, and the size/leading/measure controls work
  · progress is written to localStorage
  · partial coverage: data.total > sentence count announces "已覆盖 X/N 句"

If no Chrome/Chromium binary is found the script exits 0 with a warning, so it
can sit in a pipeline on machines without a browser.
"""

import argparse
import base64
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request

CHROME_CANDIDATES = [
    'google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser',
    'chrome', 'msedge', 'microsoft-edge',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
]

FAILS = []
PASSES = [0]


def check(name, cond, detail=''):
    if cond:
        PASSES[0] += 1
        print('  ok    ' + name)
    else:
        FAILS.append('%s :: %s' % (name, detail))
        print('  FAIL  ' + name + (('  -> ' + str(detail)) if detail else ''))


def find_chrome():
    for c in CHROME_CANDIDATES:
        p = shutil.which(c) if os.sep not in c else (c if os.path.exists(c) else None)
        if p:
            return p
    return None


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


class MiniWS:
    """极简 WebSocket 文本客户端（纯标准库），让验收在没有 pip 的机器上也能跑。

    只实现 CDP 需要的部分：HTTP 升级握手、带掩码的发送、分片/大帧接收、
    ping→pong。接口与 websockets.sync.client 的连接对象一致（send/recv/close）。
    """

    def __init__(self, url, timeout=60):
        m = re.match(r'ws://([^/:]+):(\d+)(/.*)$', url)
        if not m:
            raise RuntimeError('unsupported ws url: ' + url)
        host, port, path = m.group(1), int(m.group(2)), m.group(3)
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((
            'GET %s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\n'
            'Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n'
            'Sec-WebSocket-Version: 13\r\n\r\n' % (path, host, key)).encode())
        head = b''
        while b'\r\n\r\n' not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError('websocket handshake failed (no response)')
            head += chunk
        status = head.split(b'\r\n', 1)[0]
        if b' 101 ' not in status + b' ':
            raise RuntimeError('websocket handshake refused: '
                               + status.decode(errors='replace'))
        self.buf = head.split(b'\r\n\r\n', 1)[1]

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise RuntimeError('websocket closed by peer')
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def _send_frame(self, op, data):
        mask = os.urandom(4)
        header = bytearray([0x80 | op])
        n = len(data)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack('>H', n)
        else:
            header.append(0x80 | 127)
            header += struct.pack('>Q', n)
        masked = bytes(b ^ mask[i & 3] for i, b in enumerate(data))
        self.sock.sendall(bytes(header) + mask + masked)

    def send(self, text):
        self._send_frame(0x1, text.encode())

    def recv(self):
        msg = b''
        while True:
            b1, b2 = self._read(2)
            fin, op = b1 & 0x80, b1 & 0x0F
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack('>H', self._read(2))[0]
            elif n == 127:
                n = struct.unpack('>Q', self._read(8))[0]
            if b2 & 0x80:
                mask = self._read(4)
                payload = bytearray(self._read(n))
                for i in range(n):
                    payload[i] ^= mask[i & 3]
            else:
                payload = self._read(n)
            if op == 0x8:                       # close
                self.close()
                raise RuntimeError('websocket closed by peer')
            if op == 0x9:                       # ping → pong
                self._send_frame(0xA, bytes(payload))
                continue
            if op == 0xA:
                continue
            if op in (0x1, 0x2, 0x0):
                msg += payload
            if fin:
                return msg.decode('utf-8', 'replace')

    def close(self):
        try:
            self._send_frame(0x8, b'')
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


def connect_ws(url):
    """优先用 websockets 包（若装了），否则落到内置的 MiniWS。
    设 FCR_VERIFY_WS=stdlib 可强制走 MiniWS（测试回退路径用）。"""
    if os.environ.get('FCR_VERIFY_WS') != 'stdlib':
        try:
            from websockets.sync.client import connect
            return connect(url, max_size=64 * 1024 * 1024)
        except ImportError:
            pass
    return MiniWS(url)


class Browser:
    """Just enough CDP to navigate and evaluate JS."""

    def __init__(self, binary, width=1100, height=900):
        self.port = free_port()
        self.profile = tempfile.mkdtemp(prefix='fcr-verify-')
        self.proc = subprocess.Popen(
            [binary, '--headless=new', '--no-first-run', '--no-default-browser-check',
             '--disable-gpu', '--hide-scrollbars', '--force-device-scale-factor=1',
             '--remote-debugging-port=%d' % self.port,
             '--user-data-dir=' + self.profile,
             '--window-size=%d,%d' % (width, height), 'about:blank'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.ws = None
        self._id = 0
        for _ in range(120):
            try:
                data = json.load(urllib.request.urlopen(
                    'http://127.0.0.1:%d/json' % self.port, timeout=1))
                pages = [t for t in data if t['type'] == 'page']
                if pages:
                    self.ws = connect_ws(pages[0]['webSocketDebuggerUrl'])
                    break
            except Exception:
                time.sleep(0.25)
        if self.ws is None:
            raise RuntimeError('could not attach to the browser')
        self.cmd('Page.enable')
        self.cmd('Runtime.enable')

    def cmd(self, method, **params):
        self._id += 1
        self.ws.send(json.dumps({'id': self._id, 'method': method, 'params': params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get('id') == self._id:
                if 'error' in msg:
                    raise RuntimeError(method + ': ' + json.dumps(msg['error']))
                return msg.get('result', {})

    def goto(self, url):
        self.cmd('Page.navigate', url=url)
        time.sleep(0.9)

    def js(self, expr):
        r = self.cmd('Runtime.evaluate', expression=expr, returnByValue=True,
                     awaitPromise=True, userGesture=True)
        if r.get('exceptionDetails'):
            raise RuntimeError('JS error: ' + json.dumps(r['exceptionDetails'])[:600])
        return r.get('result', {}).get('value')

    def shot(self, path):
        d = self.cmd('Page.captureScreenshot', format='png')
        with open(path, 'wb') as f:
            f.write(base64.b64decode(d['data']))

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()
        shutil.rmtree(self.profile, ignore_errors=True)


def audit(path, b, shots_dir=None):
    print('\n== ' + os.path.basename(path))
    b.goto('file://' + os.path.abspath(path))
    lang = b.js("document.documentElement.getAttribute('data-lang')")
    n_sent = b.js("document.querySelectorAll('.s').length")
    if not n_sent:
        check('reader has sentences', False, 'no .s elements found')
        return

    txt = b.js('document.body.innerText')
    # 句子 id 列表：键盘导航的期望位置要按实际句数算，小册子不能假失败
    ids = b.js("Array.prototype.map.call(document.querySelectorAll('.s'), "
               "function (s) { return s.dataset.id; })")
    card = b.js("""(() => {
      let h = '';
      for (const s of document.querySelectorAll('.s')) { s.click(); h += s._holder.innerHTML; }
      const x = document.querySelector('.card .x'); if (x) x.click();
      return h;
    })()""")
    for bad in ('undefined', '[object Object]', 'NaN', '不支持'):
        check('[%s] %r never reaches the page' % (lang, bad), bad not in txt and bad not in card)

    holders = b.js("document.querySelectorAll('.holder').length")
    check('[%s] one annotation slot per sentence' % lang, holders == n_sent,
          '%s slots / %s sentences' % (holders, n_sent))

    place = b.js("""(() => {
      const out = {gap: -1e9, tail: [], empty: [], outside: 0};
      const col = document.querySelector('main').getBoundingClientRect();
      for (const s of document.querySelectorAll('.s')) {
        window.scrollTo(0, 0);
        s.click();
        const c = s._holder.querySelector('.card');
        if (!c) { out.empty.push(s.dataset.id); continue; }
        const sr = s.getBoundingClientRect(), cr = c.getBoundingClientRect();
        const para = s.closest('p.par').getBoundingClientRect();
        out.gap = Math.max(out.gap, cr.top - sr.bottom);
        if (cr.left < col.left - 2 || cr.right > col.right + 2) out.outside++;
        if (para.height > 400 && cr.top > para.bottom - 30) out.tail.push(s.dataset.id);
      }
      return out;
    })()""")
    check('[%s] every sentence opens a card' % lang, not place['empty'], place['empty'])
    check('[%s] card hugs the clicked sentence' % lang, place['gap'] < 24,
          'largest gap %.1fpx' % place['gap'])
    check('[%s] card never slides to a long paragraph\'s tail' % lang, not place['tail'],
          place['tail'])
    check('[%s] card stays inside the text column' % lang, place['outside'] == 0,
          place['outside'])

    one = b.js("""(() => {
      const s = [...document.querySelectorAll('.s')];
      s[0].click(); s[Math.min(3, s.length - 1)].click();
      const openCards = document.querySelectorAll('.card').length;
      document.querySelector('.card .x').click();
      return {openCards, after: document.querySelectorAll('.card').length};
    })()""")
    check('[%s] only one card open at a time' % lang, one['openCards'] == 1, one)
    check('[%s] the ✕ button closes the card' % lang, one['after'] == 0, one)

    learned = b.js("""(() => {
      const s = document.querySelectorAll('.s')[0];
      s.click(); document.querySelector('.card .x').click();
      const cs = getComputedStyle(s);
      return {cls: s.className, deco: cs.textDecorationLine, shadow: cs.boxShadow,
              color: cs.color, body: getComputedStyle(document.body).color};
    })()""")
    check('[%s] learned sentence is marked' % lang, 'seen' in learned['cls'], learned['cls'])
    check('[%s] learned sentence has no underline or highlight' % lang,
          'none' in learned['deco'] and learned['shadow'] == 'none', learned)
    check('[%s] learned sentence is dimmed' % lang, learned['color'] != learned['body'],
          learned['color'])

    kb = b.js("""(() => {
      const fire = k => document.dispatchEvent(new KeyboardEvent('keydown', {key: k, bubbles: true}));
      const s = document.querySelectorAll('.s');
      s[0].click();
      for (let i = 0; i < 4; i++) fire('ArrowRight');
      const fwd = (document.querySelector('.s.open') || {dataset: {}}).dataset.id;
      fire('ArrowLeft');
      const back = (document.querySelector('.s.open') || {dataset: {}}).dataset.id;
      const cards = document.querySelectorAll('.card').length;
      fire('Escape');
      return {fwd, back, cards, afterEsc: document.querySelectorAll('.card').length};
    })()""")
    fwd_expected = str(ids[min(4, len(ids) - 1)])
    back_expected = str(ids[max(min(4, len(ids) - 1) - 1, 0)])
    check('[%s] → advances one sentence' % lang, kb['fwd'] == fwd_expected, kb)
    check('[%s] ← goes back one sentence' % lang, kb['back'] == back_expected, kb)
    check('[%s] keyboard nav keeps a single card' % lang, kb['cards'] == 1, kb)
    check('[%s] Esc closes the card' % lang, kb['afterEsc'] == 0, kb)

    themes = b.js("""(() => {
      const ids = [...document.querySelectorAll('#sw button')].map(b => b.dataset.v);
      const bad = [];
      for (const id of ids) {
        document.querySelector('#sw button[data-v="' + id + '"]').click();
        const rs = getComputedStyle(document.documentElement);
        if (document.documentElement.getAttribute('data-theme') !== id) bad.push(id);
        if (!rs.getPropertyValue('--paper').trim() || !rs.getPropertyValue('--ink').trim())
          bad.push(id + ':vars');
      }
      document.querySelector('#sw button[data-v="sepia"]').click();
      return {ids, bad, saved: localStorage.getItem('fcr-prefs') || '',
              theme: document.documentElement.getAttribute('data-theme')};
    })()""")
    check('[%s] at least 10 themes' % lang, len(themes['ids']) >= 10, themes['ids'])
    check('[%s] every theme applies' % lang, not themes['bad'], themes['bad'])
    check('[%s] theme choice is remembered' % lang,
          '"theme":"sepia"' in themes['saved'].replace(' ', ''), themes['saved'])

    ctl = b.js("""(() => {
      document.querySelector('#seg-size button[data-v="23"]').click();
      const size = getComputedStyle(document.documentElement).getPropertyValue('--size').trim();
      document.querySelector('#seg-lead button[data-v="2.5"]').click();
      const lead = getComputedStyle(document.documentElement).getPropertyValue('--lead').trim();
      document.querySelector('#seg-measure button[data-v="900"]').click();
      const width = Math.round(document.querySelector('main').getBoundingClientRect().width);
      document.querySelector('#seg-reset button').click();
      return {size, lead, width,
              reset: getComputedStyle(document.documentElement).getPropertyValue('--measure').trim()};
    })()""")
    check('[%s] font size control works' % lang, ctl['size'] == '23px', ctl)
    check('[%s] line-height control works' % lang, ctl['lead'] == '2.5', ctl)
    check('[%s] column-width control works' % lang, abs(ctl['width'] - 900) < 60, ctl)
    check('[%s] reset restores the defaults' % lang, ctl['reset'] == '680px', ctl)

    prog = b.js("document.querySelectorAll('.s.seen').length")
    check('[%s] reading progress is tracked' % lang, prog > 0, prog)

    # 增量生成：data.total 大于已生成句数时，必须向读者说明覆盖进度
    cov = b.js("""(() => {
      const d = JSON.parse(document.getElementById('data').textContent);
      const total = Number(d.total) || 0, have = d.sentences.length;
      return {total, partial: total > have,
              note: !!document.querySelector('p.more'),
              meta: document.getElementById('meta').textContent};
    })()""")
    if cov['total']:
        if cov['partial']:
            check('[%s] partial coverage is announced' % lang,
                  cov['note'] and '已覆盖' in cov['meta'], cov)
        else:
            check('[%s] full coverage shows no continue note' % lang,
                  not cov['note'], cov)

    if shots_dir:
        os.makedirs(shots_dir, exist_ok=True)
        b.js("document.querySelectorAll('.s')[1].click()")
        b.shot(os.path.join(shots_dir, os.path.basename(path) + '.png'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('readers', nargs='+')
    ap.add_argument('--shots', help='also write a screenshot per reader into this directory')
    a = ap.parse_args()

    binary = find_chrome()
    if not binary:
        print('verify_reader: no Chrome/Chromium found — skipping the browser check')
        return 0

    b = Browser(binary)
    try:
        for p in a.readers:
            if not os.path.exists(p):
                check('reader exists: ' + p, False, 'file not found')
                continue
            audit(p, b, a.shots)
    finally:
        b.close()

    print('\n%d checks passed' % PASSES[0])
    if FAILS:
        print('%d FAILED:' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('reader verified')
    return 0


if __name__ == '__main__':
    sys.exit(main())
