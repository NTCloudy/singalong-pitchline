"""Developer self-test. Needs Playwright and its headless Chromium (not needed to use the site).

Starts the preview server on 127.0.0.1, checks the listening address, runs the
checks, and stops the server by the PID it started.

  python3 -m tools.selftest            pure logic + page behaviour with a stand-in player
                                        (no request leaves this machine)
  python3 -m tools.selftest --youtube  additionally loads the real YouTube player once
                                        (connects to YouTube's own hosts only)
"""
import json
import math
import os
import pathlib
import random
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHOTS = ROOT / "preview"
PORT = 8771
BASE = f"http://127.0.0.1:{PORT}"
REAL_VIDEO = "M7lc1UVf-VE"            # the sample video used in YouTube's own player documentation
YT_HOSTS = ("youtube.com", "ytimg.com", "googlevideo.com", "ggpht.com", "youtube-nocookie.com")
failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def write_tone(path, freq, seconds=20, rate=48000, amp=0.5):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(32767 * amp * math.sin(2 * math.pi * freq * i / rate)))
                               for i in range(int(seconds * rate))))


def start_server():
    proc = subprocess.Popen([sys.executable, "-m", "tools.serve", str(PORT)], cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            urllib.request.urlopen(BASE + "/site/", timeout=0.5).read()
            break
        except OSError:
            time.sleep(0.1)
    lines = [ln.split()[3] for ln in subprocess.run(["ss", "-ltnH"], capture_output=True, text=True).stdout.splitlines()
             if f":{PORT} " in ln]
    check("preview server listens on 127.0.0.1 only", lines == [f"127.0.0.1:{PORT}"], str(lines))
    return proc


def stop_server(proc):
    proc.terminate()
    proc.wait(timeout=10)
    out = subprocess.run(["ss", "-ltnH"], capture_output=True, text=True).stdout
    check("preview server stopped", f":{PORT} " not in out)


# A stand-in for YouTube's script, used so that most checks need no network at all.
FAKE_API = r"""
(function () {
  function Player(id, opts) {
    var self = this, holder = document.getElementById(id), frame = document.createElement('iframe');
    frame.id = id; frame.width = opts.width; frame.height = opts.height; frame.setAttribute('data-fake-player', '1');
    holder.parentNode.replaceChild(frame, holder);
    this.opts = opts; this.id = opts.videoId; this.calls = [];
    window.__fake = this;
    this.emit = function (name, data) { if (opts.events[name]) opts.events[name]({data: data, target: self}); };
    this.cue = function (vid) { self.id = vid; self.calls.push('cue:' + vid);
      if (vid.indexOf('ERR101') === 0) setTimeout(function () { self.emit('onError', 101); }, 0);
      else if (vid.indexOf('ERR150') === 0) setTimeout(function () { self.emit('onError', 150); }, 0);
      else if (vid.indexOf('ERR100') === 0) setTimeout(function () { self.emit('onError', 100); }, 0); };
    setTimeout(function () { self.emit('onReady'); self.cue(opts.videoId); }, 0);
  }
  Player.prototype.cueVideoById = function (vid) { this.cue(vid); };
  Player.prototype.playVideo = function () { this.calls.push('play'); this.emit('onStateChange', 1); };
  Player.prototype.getVideoData = function () { return {video_id: this.id, title: '<img src=x onerror=window.__xss=1><b>標題</b> ' + this.id}; };
  window.YT = {Player: Player, PlayerState: {PLAYING: 1}};
  if (window.onYouTubeIframeAPIReady) window.onYouTubeIframeAPIReady();
})();
"""


def logic_tests(page):
    page.goto(BASE + "/harness/harness.html")
    rate = 48000

    def tone(freqs_amps, n=2048, noise=0.0, seed=1, phase=0.3):
        rnd = random.Random(seed)
        return [sum(a * math.sin(2 * math.pi * f * i / rate + phase * k) for k, (f, a) in enumerate(freqs_amps))
                + (rnd.uniform(-noise, noise) if noise else 0.0) for i in range(n)]

    def detect(samples, sr=rate):
        return page.evaluate("([s, r]) => KTV.pitch.detect(Float32Array.from(s), r)", [samples, sr])

    def cents(f, target):
        return 1200 * math.log2(f / target)

    r = detect(tone([(440, 0.5)]))
    n = page.evaluate("f => KTV.pitch.note(f)", r["freq"])
    check(f"440 Hz sine -> A4 within 20 cents (got {r['freq']:.2f} Hz, {n['label']} {n['cents']:+d})",
          n["label"] == "A4" and abs(cents(r["freq"], 440)) <= 20)
    worst = 0
    for f in [82.4, 110, 146.8, 196, 220, 261.6, 329.6, 392, 440, 523.3, 659.3, 784, 880, 987.8, 1046.5]:
        got = detect(tone([(f, 0.4)]))
        worst = max(worst, abs(cents(got["freq"], f)) if got else 9999)
    check(f"pure tones 82 Hz to 1047 Hz: worst error {worst:.1f} cents (<= 10)", worst <= 10)
    for sr in (44100, 48000):
        got = detect([0.5 * math.sin(2 * math.pi * 440 * i / sr) for i in range(2048)], sr)
        check(f"sample rate {sr}: 440 Hz within 5 cents", got and abs(cents(got["freq"], 440)) <= 5)
    bad = []
    for f in (110, 165, 220, 330, 440, 660):
        for name, mix in (("strong 2nd harmonic", [(f, 0.2), (2 * f, 0.5), (3 * f, 0.2)]),
                          ("weak fundamental", [(f, 0.05), (2 * f, 0.4), (3 * f, 0.4), (4 * f, 0.2)]),
                          ("voice-like", [(f, 0.4), (2 * f, 0.3), (3 * f, 0.2), (4 * f, 0.15), (5 * f, 0.1)])):
            got = detect(tone(mix))
            if not got or abs(cents(got["freq"], f)) > 30:
                bad.append((f, name, got and round(got["freq"], 1)))
    check("no octave errors on 18 harmonic mixes (strong 2nd harmonic, weak fundamental, voice-like)", not bad, str(bad))
    bad = []
    for seed in range(20):
        got = detect(tone([(440, 0.5), (880, 0.2)], noise=0.1, seed=seed))
        if not got or abs(cents(got["freq"], 440)) > 20:
            bad.append((seed, got))
    check("440 Hz with noise (20 seeds): within 20 cents every time", not bad, str(bad[:3]))
    check("silence -> no pitch", detect([0.0] * 2048) is None and detect(tone([(440, 0.004)])) is None)
    hits = sum(detect([random.Random(s * 7919 + i).uniform(-0.3, 0.3) for i in range(2048)]) is not None for s in range(40))
    check(f"white noise -> no pitch (false detections: {hits} of 40, allowed <= 2)", hits <= 2)
    vib = [0.5 * math.sin(2 * math.pi * 440 * i / rate + 3 * math.sin(2 * math.pi * 5.5 * i / rate)) for i in range(2048)]
    got = detect(vib)
    check("vibrato around 440 Hz stays within a semitone", got and abs(cents(got["freq"], 440)) < 100)
    notes = page.evaluate("fs => fs.map(f => { const n = KTV.pitch.note(f); return [n.label, n.cents]; })",
                          [440, 261.626, 466.164, 452.89, 65.406, 1046.5])
    check("note names", notes == [["A4", 0], ["C4", 0], ["A#4", 0], ["A4", 50], ["C2", 0], ["C6", 0]] or
          notes == [["A4", 0], ["C4", 0], ["A#4", 0], ["A#4", -50], ["C2", 0], ["C6", 0]], str(notes))
    ms = page.evaluate("""() => { const s = Float32Array.from({length: 2048}, (_, i) => 0.5 * Math.sin(2 * Math.PI * 233 * i / 48000));
        const t = performance.now(); for (let k = 0; k < 50; k++) KTV.pitch.detect(s, 48000); return (performance.now() - t) / 50; }""")
    check(f"one detection takes {ms:.1f} ms (must be well under a 16 ms frame)", ms < 12)

    good = {"https://www.youtube.com/watch?v=M7lc1UVf-VE": "M7lc1UVf-VE", "https://youtu.be/M7lc1UVf-VE?t=10": "M7lc1UVf-VE",
            "https://www.youtube.com/shorts/abcdefghijk": "abcdefghijk", "youtube.com/watch?v=abc_DEF-123&list=x": "abc_DEF-123",
            "  https://m.youtube.com/watch?feature=share&v=abcdefghijk  ": "abcdefghijk", "http://youtu.be/abcdefghijk": "abcdefghijk",
            "https://music.youtube.com/watch?v=abcdefghijk": "abcdefghijk"}
    bad_links = ["", "hello", "https://example.com/watch?v=abcdefghijk", "https://www.youtube.com/watch?v=short",
                 "https://www.youtube.com/watch?v=abcdefghijkl", "https://youtube.com.evil.example/watch?v=abcdefghijk",
                 "https://www.youtube.com/watch", "javascript:alert(1)", "https://youtu.be/", "https://www.youtube.com/watch?v=abc<efghijk",
                 "https://www.youtube.com/playlist?list=PLabcdefghijk", "abcdefghijk", "https://www.youtube.com/watch?v=abcdefghijk x"]
    got = page.evaluate("ls => ls.map(l => KTV.link.videoId(l))", list(good) + bad_links)
    check("link parsing: watch, youtu.be, shorts accepted; 13 bad inputs rejected",
          got == list(good.values()) + [None] * len(bad_links), str(got))


def new_page(browser, external, allow_youtube=False, size=(1280, 800)):
    ctx = browser.new_context(viewport={"width": size[0], "height": size[1]})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "127.0.0.1" in (m.location or {}).get("url", "") else None)

    def route(r):
        host = urlparse(r.request.url).hostname or ""
        if host == "127.0.0.1":
            return r.continue_()
        external.append(r.request.url)
        if not allow_youtube and r.request.url == "https://www.youtube.com/iframe_api":
            return r.fulfill(status=200, content_type="text/javascript", body=FAKE_API)
        if allow_youtube and any(host == h or host.endswith("." + h) for h in YT_HOSTS):
            return r.continue_()
        return r.abort()
    ctx.route("**/*", route)
    return ctx, page, errors


def tid(page, name):
    return page.locator(f'[data-testid="{name}"]')


def ui_tests(pw, tmp):
    wav = pathlib.Path(tmp) / "a440.wav"
    write_tone(wav, 440)
    fake_mic = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream", f"--use-file-for-fake-audio-capture={wav}",
                "--autoplay-policy=no-user-gesture-required"]
    browser = pw.chromium.launch(args=fake_mic)
    external = []
    ctx, page, errors = new_page(browser, external)
    mic_calls = "window.__gum = 0; const o = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices); navigator.mediaDevices.getUserMedia = c => { window.__gum++; return o(c); };"
    page.add_init_script(mic_calls)
    page.goto(BASE + "/site/")
    check("opening the page makes no third-party request and does not ask for the microphone",
          external == [] and page.evaluate("window.__gum") == 0, str(external))
    check("headphones tip is shown", "請戴耳機" in tid(page, "headphones-tip").inner_text())
    check("1280x800: no horizontal scroll", page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
    check("start button disabled before a video is loaded; page state is idle",
          tid(page, "start-button").is_disabled() and page.get_attribute("body", "data-state") == "idle"
          and tid(page, "note").get_attribute("data-voiced") == "false")
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=str(SHOTS / "01_empty.png"), full_page=True)

    tid(page, "link-input").fill("not a link")
    tid(page, "load-button").click()
    check("bad link: explanation shown, nothing loaded", "看不懂這個連結" in tid(page, "message").inner_text() and external == [])

    tid(page, "link-input").fill("https://youtu.be/AAAAAAAAAAA")
    tid(page, "load-button").click()
    page.wait_for_selector('[data-testid="start-button"]:not([disabled])')
    check("valid link: the only external request is YouTube's player script", external == ["https://www.youtube.com/iframe_api"], str(external))
    check("no microphone request before pressing start", page.evaluate("window.__gum") == 0)
    box = page.locator("#player").bounding_box()
    check(f"player is at least 480x270 (is {box['width']:.0f}x{box['height']:.0f})", box["width"] >= 480 and box["height"] >= 270)

    tid(page, "start-button").click()
    page.wait_for_selector('[data-testid="mic-status"][data-mic="on"]')
    page.wait_for_selector('[data-testid="note"]:not([data-note=""])', timeout=8000)
    page.wait_for_timeout(1500)
    samples = page.evaluate("""async () => { const out = []; for (let i = 0; i < 40; i++) { const n = document.querySelector('[data-testid=note]');
        out.push([n.dataset.note, parseFloat(n.dataset.freq), parseInt(document.querySelector('[data-testid=cents]').dataset.cents)]); await new Promise(r => setTimeout(r, 50)); } return out; }""")
    ok = all(s[0] == "A4" and abs(s[2]) <= 20 for s in samples)
    freqs = [s[1] for s in samples]
    check(f"fake microphone playing 440 Hz: shows A4 within 20 cents on all 40 readings ({min(freqs):.1f} to {max(freqs):.1f} Hz)", ok, str(samples[:5]))
    check("start pressed: microphone requested once, then the video is told to play",
          page.evaluate("window.__gum") == 1 and page.evaluate("window.__fake.calls.includes('play')"))
    drawn = page.evaluate("""() => { const c = document.querySelector('[data-testid=graph]'), d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
        let n = 0; for (let i = 0; i < d.length; i += 4) if (d[i] === 90 && d[i + 1] === 209 && d[i + 2] === 164) n++; return n; }""")
    check("pitch line is drawn on the graph", drawn > 200, str(drawn))
    over = page.evaluate("""() => { const p = document.querySelector('#player').getBoundingClientRect();
        const pts = []; for (let x = p.left + 5; x < p.right; x += 40) for (let y = p.top + 5; y < p.bottom; y += 40) pts.push([x, y]);
        const hit = pts.filter(([x, y]) => document.elementFromPoint(x, y) !== document.querySelector('#player')).length;
        const g = document.querySelector('[data-testid=pitch-area]').getBoundingClientRect();
        return {hit, total: pts.length, below: g.top >= p.bottom}; }""")
    check(f"nothing covers the player ({over['total']} sample points) and the pitch area is below it", over["hit"] == 0 and over["below"], str(over))
    check("1280x800 with player: no horizontal scroll", page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
    page.screenshot(path=str(SHOTS / "02_singing_a440_standin_player.png"), full_page=True)

    item = tid(page, "recent-item")
    check("recent list: one entry; the title is shown as plain text",
          item.count() == 1 and "<b>標題</b>" in item.first.inner_text() and page.evaluate("window.__xss === undefined")
          and page.locator('[data-testid="recent"] img, [data-testid="recent"] b').count() == 0)
    for code in ("ERR101", "ERR150"):
        tid(page, "link-input").fill(f"https://www.youtube.com/watch?v={code}xxxxx")
        tid(page, "load-button").click()
        page.wait_for_selector('[data-testid="message"]:not(:empty)')
        check(f"player error {code[3:]}: message shown, link box ready for the next link",
              tid(page, "message").inner_text() == "這支影片不允許嵌入，請換一支。" and page.evaluate("document.activeElement.id") == "link"
              and tid(page, "start-button").is_disabled())
    tid(page, "link-input").fill("https://www.youtube.com/shorts/BBBBBBBBBBB")
    tid(page, "load-button").click()
    page.wait_for_selector('[data-testid="start-button"]:not([disabled])')
    check("after an error, the next link loads and the message clears", tid(page, "message").inner_text() == "")
    page.evaluate("KTV.app.handlePlayerError(150)")
    check("error handler can be called directly; page state is error", page.get_attribute("body", "data-state") == "error"
          and tid(page, "message").get_attribute("data-error-code") == "150")
    tid(page, "load-button").click()
    page.wait_for_selector('body[data-state="mic"]')
    check("page state returns to mic after loading again; voiced reading carries note, freq and cents",
          tid(page, "note").get_attribute("data-voiced") == "true" and tid(page, "note").get_attribute("data-cents") is not None)
    page.screenshot(path=str(SHOTS / "03_after_error_next_link.png"), full_page=True)

    page.evaluate("""() => { const l = []; for (let i = 0; i < 25; i++) l.push({id: ('v' + i + 'xxxxxxxxxxx').slice(0, 11), title: 'T' + i});
        localStorage.setItem('ktv.recent.v1', JSON.stringify(l)); }""")
    page.reload()
    check("recent list survives a reload and shows at most 20", tid(page, "recent-item").count() == 20)
    tid(page, "link-input").fill("https://youtu.be/CCCCCCCCCCC")
    tid(page, "load-button").click()
    page.wait_for_selector('[data-testid="start-button"]:not([disabled])')
    tid(page, "start-button").click()
    page.wait_for_selector('[data-testid="recent-item"][data-video-id="CCCCCCCCCCC"]')
    stored = json.loads(page.evaluate("localStorage.getItem('ktv.recent.v1')"))
    check("recent list keeps the newest 20, newest first, storing only id and title",
          len(stored) == 20 and stored[0]["id"] == "CCCCCCCCCCC" and all(sorted(x) == ["id", "title"] for x in stored))
    tid(page, "mic-off-button").click()
    check("microphone can be turned off; the note display clears",
          tid(page, "mic-status").get_attribute("data-mic") == "off" and tid(page, "note").inner_text() == "—")
    tid(page, "clear-recent").click()
    check("clear empties the list and the storage", tid(page, "recent-item").count() == 0 and page.evaluate("localStorage.getItem('ktv.recent.v1')") is None)
    keys = page.evaluate("[Object.keys(localStorage), Object.keys(sessionStorage), document.cookie]")
    check("nothing else is stored in the browser", keys == [[], [], ""], str(keys))
    check("only request to a third party in the whole run: YouTube's player script",
          set(external) == {"https://www.youtube.com/iframe_api"}, str(set(external)))
    check("no page errors", not errors, str(errors[:3]))
    ctx.close()
    browser.close()

    # Silence: a fake microphone that plays a silent file must draw nothing.
    silent = pathlib.Path(tmp) / "silent.wav"
    write_tone(silent, 440, amp=0.0)
    browser = pw.chromium.launch(args=fake_mic[:2] + [f"--use-file-for-fake-audio-capture={silent}"])
    ctx, page, errors = new_page(browser, [])
    page.goto(BASE + "/site/")
    tid(page, "link-input").fill("https://youtu.be/AAAAAAAAAAA")
    tid(page, "load-button").click()
    page.wait_for_selector('[data-testid="start-button"]:not([disabled])')
    tid(page, "start-button").click()
    page.wait_for_selector('[data-testid="mic-status"][data-mic="on"]')
    page.wait_for_timeout(1500)
    drawn = page.evaluate("""() => { const c = document.querySelector('[data-testid=graph]'), d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
        let n = 0; for (let i = 0; i < d.length; i += 4) if (d[i] === 90 && d[i + 1] === 209 && d[i + 2] === 164) n++; return n; }""")
    check("silent microphone: no note shown and no line drawn", tid(page, "note").inner_text() == "—" and drawn == 0, str(drawn))
    ctx.close()
    browser.close()

    # Permission denied: no fake-permission flag, so the browser refuses the microphone.
    browser = pw.chromium.launch()
    ctx, page, errors = new_page(browser, [])
    page.goto(BASE + "/site/")
    tid(page, "link-input").fill("https://youtu.be/AAAAAAAAAAA")
    tid(page, "load-button").click()
    page.wait_for_selector('[data-testid="start-button"]:not([disabled])')
    tid(page, "start-button").click()
    page.wait_for_selector('[data-testid="mic-help"]:not([hidden])', timeout=8000)
    check("microphone refused: video still told to play, help text explains how to allow it",
          page.evaluate("window.__fake.calls.includes('play')") and "重新允許" in tid(page, "mic-help").inner_text()
          and tid(page, "mic-status").get_attribute("data-mic") == "off" and page.get_attribute("body", "data-state") == "denied")
    page.screenshot(path=str(SHOTS / "04_mic_refused.png"), full_page=True)
    check("no page errors (refused)", not errors, str(errors[:3]))
    ctx.close()
    browser.close()
    return fake_mic


def youtube_test(pw, fake_mic):
    """One run against the real YouTube player. Only YouTube's own hosts are allowed."""
    browser = pw.chromium.launch(args=fake_mic)
    external = []
    ctx, page, errors = new_page(browser, external, allow_youtube=True)
    states = []
    page.goto(BASE + "/site/")
    tid(page, "link-input").fill(f"https://www.youtube.com/watch?v={REAL_VIDEO}")
    tid(page, "load-button").click()
    try:
        page.wait_for_selector('[data-testid="start-button"]:not([disabled])', timeout=30000)
        ready = True
    except Exception:
        ready = False
    check("real YouTube: player script loads under the page's content security policy and the player becomes ready", ready,
          "message=" + tid(page, "message").inner_text())
    if ready:
        frame = page.locator("#player")
        box = frame.bounding_box()
        check(f"real YouTube: the player is an iframe from www.youtube.com, {box['width']:.0f}x{box['height']:.0f}",
              frame.evaluate("e => e.tagName") == "IFRAME" and (frame.get_attribute("src") or "").startswith("https://www.youtube.com/embed/")
              and box["width"] >= 480 and box["height"] >= 270, str(frame.get_attribute("src")))
        tid(page, "start-button").click()
        try:
            page.wait_for_selector('[data-testid="recent-item"]', timeout=30000)
            playing = True
        except Exception:
            playing = False
        check("real YouTube: playback starts (player reports 'playing') and the song appears in the recent list with its title", playing,
              "message=" + tid(page, "message").inner_text())
        if playing:
            print("     title from YouTube:", tid(page, "recent-item").first.inner_text()[:80])
            page.wait_for_timeout(2500)
            check("real YouTube: pitch line still works beside the real player (A4 from the fake microphone)",
                  tid(page, "note").get_attribute("data-note") == "A4")
        page.screenshot(path=str(SHOTS / "05_real_youtube_player.png"), full_page=True)
    hosts = sorted({urlparse(u).hostname for u in external})
    allowed = [h for h in hosts if any(h == y or h.endswith("." + y) for y in YT_HOSTS)]
    print("     hosts contacted:", allowed)
    print("     hosts requested by the player but blocked by this test:", [h for h in hosts if h not in allowed])
    top = [u for u in external if urlparse(u).hostname not in ("www.youtube.com",)]
    page_level = page.evaluate("performance.getEntriesByType('resource').map(e => e.name).filter(n => !n.startsWith(location.origin))")
    check("real YouTube: the page itself loads nothing from outside except www.youtube.com (player script and iframe)",
          all(urlparse(n).hostname == "www.youtube.com" for n in page_level), str(page_level[:5]))
    ours = [e for e in errors if "network error" not in e.lower()]     # requests this test blocks show up as network errors
    check("real YouTube: no page errors from our own scripts", not ours, str(ours[:3]))
    ctx.close()
    browser.close()


def main():
    proc = start_server()
    try:
        with tempfile.TemporaryDirectory() as tmp, sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            logic_tests(page)
            browser.close()
            fake_mic = ui_tests(pw, tmp)
            if "--youtube" in sys.argv:
                youtube_test(pw, fake_mic)
    finally:
        stop_server(proc)
    print(f"\n{len(failures)} failed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
