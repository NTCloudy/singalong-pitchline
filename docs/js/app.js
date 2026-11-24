/* Page logic. Text from the user or from storage (links, song names) is only ever
 * written with textContent. Microphone audio is analysed live in this page and then
 * discarded: nothing is recorded, stored or sent anywhere. */
(function () {
  "use strict";
  var K = window.KTV;
  var RECENT_KEY = "singalong-pitchline.recent.v1";   // localStorage: [{id, name}], newest first
  var RECENT_MAX = 20;
  var HISTORY_MS = 8000;                // how much of the pitch line stays on screen
  var MIDI_LOW = 36, MIDI_HIGH = 84;    // C2 .. C6 on the graph
  var FFT_SIZE = 2048;                  // about 43 ms of audio at 48 kHz

  function $(id) { return document.getElementById(id); }
  var linkInput = $("link"), nameInput = $("song-name"), loadBtn = $("load"), message = $("message");
  var micBtn = $("mic"), micStatus = $("mic-status"), micHelp = $("mic-help");
  var noteEl = $("note"), centsEl = $("cents"), canvas = $("graph");
  var recentList = $("recent"), recentEmpty = $("recent-empty"), clearBtn = $("clear-recent");

  // playerState: "none" (not created) -> "creating" (waiting for YouTube's onReady) -> "ready".
  // The player object only has its methods once it is ready, so until then a newly chosen
  // video is just remembered in currentId and applied in onReady.
  var player = null, apiState = "none", playerState = "none", shownId = null, currentId = null, currentName = "";
  var audioCtx = null, analyser = null, micStream = null, buffer = null, rafId = 0;
  var history = [];                     // [{t, midi|null}]
  var loaded = false, failed = false, denied = false;

  // One readable page state: idle | loaded | mic | denied | error
  function refreshState() {
    var s = failed ? "error" : micStream ? "mic" : denied ? "denied" : loaded ? "loaded" : "idle";
    document.body.setAttribute("data-state", s);
  }

  // ---------- messages ---------------------------------------------------------
  function say(text) { message.textContent = text || ""; message.removeAttribute("data-error-code"); }

  // ---------- recent list --------------------------------------------------------
  function readRecent() {
    try {
      var list = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
      if (!Array.isArray(list)) return [];
      return list.filter(function (x) {
        return x && typeof x.id === "string" && /^[A-Za-z0-9_-]{11}$/.test(x.id) && typeof x.name === "string";
      }).slice(0, RECENT_MAX);
    } catch (e) { return []; }
  }
  function writeRecent(list) {
    try { localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, RECENT_MAX))); } catch (e) { /* storage unavailable */ }
  }
  // The name is whatever the user typed (may be empty). Nothing is looked up on YouTube.
  function addRecent(id, name) {
    var old = readRecent(), prev = old.filter(function (x) { return x.id === id; })[0];
    var list = old.filter(function (x) { return x.id !== id; });
    name = String(name || "").trim().slice(0, 80);
    list.unshift({ id: id, name: name || (prev ? prev.name : "") });
    writeRecent(list);
    renderRecent();
  }
  function renderRecent() {
    var list = readRecent();
    while (recentList.firstChild) recentList.removeChild(recentList.firstChild);
    list.forEach(function (item) {
      var li = document.createElement("li");
      var b = document.createElement("button");
      b.type = "button";
      b.setAttribute("data-testid", "recent-item");
      b.setAttribute("data-video-id", item.id);
      b.textContent = item.name || item.id;
      b.addEventListener("click", function () { nameInput.value = item.name; loadVideo(item.id, item.name); });
      li.appendChild(b);
      recentList.appendChild(li);
    });
    recentEmpty.hidden = list.length > 0;
    clearBtn.hidden = list.length === 0;
  }
  clearBtn.addEventListener("click", function () {
    try { localStorage.removeItem(RECENT_KEY); } catch (e) { /* ignore */ }
    renderRecent();
  });

  // ---------- YouTube player (the official IFrame API; the only third-party resource) ---
  function loadApi() {
    if (apiState !== "none") return;
    apiState = "loading";
    window.onYouTubeIframeAPIReady = function () {
      apiState = "ready";
      if (currentId) createPlayer();
    };
    var s = document.createElement("script");
    s.src = "https://www.youtube.com/iframe_api";
    s.onerror = function () {
      apiState = "none";
      say("無法載入 YouTube 播放器，請確認網路後再按一次「載入」。");
    };
    document.head.appendChild(s);
  }
  function createPlayer() {
    if (playerState !== "none") return;          // never build a second player
    playerState = "creating";
    shownId = currentId;
    player = new window.YT.Player("player", {
      width: "560", height: "315", videoId: shownId,
      playerVars: { playsinline: 1, rel: 0 },
      events: { onReady: onReady, onError: onError, onStateChange: onStateChange }
    });
  }
  function onReady() {
    playerState = "ready";
    loaded = true;
    // Another song may have been chosen while the player was still starting up.
    if (currentId && currentId !== shownId) { shownId = currentId; player.cueVideoById(currentId); }
    refreshState();
  }
  function onError(ev) {
    handlePlayerError(ev && ev.data);
  }
  function handlePlayerError(code) {
    failed = true;
    if (code === 101 || code === 150) say("這支影片不允許嵌入，請換一支");
    else if (code === 100) say("找不到這支影片，或它是私人影片");
    else if (code === 2) say("連結有問題，請重新貼上");
    else if (code === 153) say("這個頁面要用 https 或 localhost 網址開啟才能播放");
    else say("播放器無法播放這支影片，請再試一次或換一支");
    message.setAttribute("data-error-code", String(Number(code)));
    refreshState();
    linkInput.focus();
    linkInput.select();
  }
  function onStateChange(ev) {
    if (ev && ev.data === 1 && currentId) addRecent(currentId, currentName);   // 1 = playing
  }
  function loadVideo(id, name) {
    currentId = id;
    currentName = name || "";
    failed = false;
    say("");
    if (playerState === "ready") {
      shownId = id;
      player.cueVideoById(id);       // only the video id is passed: no start time, no playlist
    } else if (playerState === "none") {
      if (apiState === "ready") createPlayer(); else loadApi();
    }                                // "creating": onReady picks up currentId
    refreshState();
  }
  function onLoadClick() {
    var id = K.link.videoId(linkInput.value);
    if (!id) {
      say("看不懂這個連結。請貼上 YouTube 影片的網址，例如 https://www.youtube.com/watch?v=… 、https://youtu.be/… 或 https://www.youtube.com/shorts/… 。");
      return;
    }
    loadVideo(id, nameInput.value);
  }
  loadBtn.addEventListener("click", onLoadClick);
  linkInput.addEventListener("keydown", function (ev) { if (ev.key === "Enter") onLoadClick(); });

  // ---------- microphone ---------------------------------------------------------
  function setMic(on) {
    micStatus.setAttribute("data-mic", on ? "on" : "off");
    micStatus.textContent = on ? "麥克風已開啟" : "麥克風未開啟";
    micBtn.textContent = on ? "關閉麥克風" : "開啟麥克風";
    refreshState();
  }
  // Resolves to "on", "denied" or "nodevice".
  function openMic() {
    if (micStream) return Promise.resolve("on");
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return Promise.resolve("nodevice");
    return navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false }, video: false
    }).then(function (stream) {
      micStream = stream;
      var Ctx = window.AudioContext || window.webkitAudioContext;
      audioCtx = new Ctx();
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = FFT_SIZE;
      // The microphone goes into the analyser only. It is not connected to the speakers,
      // to a recorder or to anything that leaves this page.
      audioCtx.createMediaStreamSource(stream).connect(analyser);
      buffer = new Float32Array(analyser.fftSize);
      denied = false;
      setMic(true);
      micHelp.hidden = true;
      if (!rafId) rafId = requestAnimationFrame(tick);
      return "on";
    }).catch(function (err) {
      var n = err && err.name;
      return n === "NotFoundError" || n === "DevicesNotFoundError" || n === "OverconstrainedError" ? "nodevice" : "denied";
    });
  }
  function closeMic() {
    if (micStream) micStream.getTracks().forEach(function (t) { t.stop(); });   // releases the device
    if (audioCtx) { try { audioCtx.close(); } catch (e) { /* ignore */ } }
    micStream = null; audioCtx = null; analyser = null; buffer = null;
    if (rafId) cancelAnimationFrame(rafId);
    rafId = 0;
    history = [];
    showNote(null);
    draw(performance.now());
    setMic(false);
  }
  micBtn.addEventListener("click", function () {
    if (micStream) return closeMic();
    // The permission prompt appears only here, after the user presses the button.
    openMic().then(function (result) {
      if (result !== "on") {
        denied = true;
        refreshState();
        micHelp.hidden = false;
        micHelp.setAttribute("data-reason", result);
        micHelp.textContent = result === "nodevice"
          ? "找不到麥克風裝置。影片照常播放，但不會有音高線。請接上麥克風後再按一次「開啟麥克風」。"
          : "麥克風沒有開啟。影片照常播放，但不會有音高線。要重新允許：點網址列左邊的圖示 → 網站設定 → 麥克風 → 允許，再重新整理這個頁面。";
      }
      // The song starts once the microphone question is settled, whatever the answer was.
      if (playerState === "ready" && !failed) player.playVideo();
    });
  });

  // ---------- pitch line -----------------------------------------------------------
  function showNote(n) {
    if (!n) {
      noteEl.textContent = "—";
      noteEl.setAttribute("data-note", "");
      noteEl.setAttribute("data-voiced", "false");
      noteEl.removeAttribute("data-freq");
      noteEl.removeAttribute("data-cents");
      centsEl.textContent = "";
      centsEl.removeAttribute("data-cents");
      return;
    }
    noteEl.textContent = n.label;
    noteEl.setAttribute("data-note", n.label);
    noteEl.setAttribute("data-voiced", "true");
    noteEl.setAttribute("data-freq", n.freq.toFixed(2));
    noteEl.setAttribute("data-cents", String(n.cents));
    centsEl.textContent = (n.cents > 0 ? "+" : "") + n.cents + " 音分";
    centsEl.setAttribute("data-cents", String(n.cents));
  }
  function tick(now) {
    rafId = requestAnimationFrame(tick);
    if (!analyser) return;
    analyser.getFloatTimeDomainData(buffer);
    var p = K.pitch.detect(buffer, audioCtx.sampleRate);
    var n = null;
    if (p) { n = K.pitch.note(p.freq); n.freq = p.freq; }
    history.push({ t: now, midi: n ? n.midi : null });   // null = silence: a gap in the line
    while (history.length && now - history[0].t > HISTORY_MS) history.shift();
    showNote(n);
    draw(now);
  }
  function draw(now) {
    var dpr = window.devicePixelRatio || 1;
    var w = canvas.clientWidth, h = canvas.clientHeight;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    }
    var g = canvas.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    function y(midi) { return h - (midi - MIDI_LOW) / (MIDI_HIGH - MIDI_LOW) * h; }
    g.font = "12px system-ui, sans-serif";
    g.textBaseline = "middle";
    for (var m = MIDI_LOW; m <= MIDI_HIGH; m++) {
      var isC = m % 12 === 0;
      g.strokeStyle = isC ? "#3a4855" : "#1c252d";
      g.lineWidth = 1;
      g.beginPath(); g.moveTo(0, y(m)); g.lineTo(w, y(m)); g.stroke();
      if (isC && m < MIDI_HIGH) { g.fillStyle = "#8d9aa6"; g.fillText("C" + (m / 12 - 1), 4, y(m) - 8); }
    }
    g.strokeStyle = "#5ad1a4";
    g.lineWidth = 3;
    g.lineJoin = "round";
    g.lineCap = "round";
    var drawing = false, last = null;
    g.beginPath();
    history.forEach(function (pt) {
      if (pt.midi === null || pt.midi < MIDI_LOW || pt.midi > MIDI_HIGH) { drawing = false; last = null; return; }
      var x = w - (now - pt.t) / HISTORY_MS * w, py = y(pt.midi);
      // A jump of more than an octave between two frames starts a new stroke.
      if (!drawing || (last !== null && Math.abs(pt.midi - last) > 12)) { g.moveTo(x, py); drawing = true; }
      else g.lineTo(x, py);
      last = pt.midi;
    });
    g.stroke();
  }

  // ---------- song list (docs/js/songs.js) ---------------------------------------
  function renderSongs() {
    var list = K.link.songList(K.songs);       // a missing or broken file counts as an empty list
    var ul = $("songs");
    list.forEach(function (song) {
      var li = document.createElement("li");
      var b = document.createElement("button");
      b.type = "button";
      b.setAttribute("data-testid", "song-item");
      b.setAttribute("data-video-id", song.id);
      var title = document.createElement("span");
      title.className = "title";
      title.textContent = song.title;
      b.appendChild(title);
      if (song.artist) {
        var artist = document.createElement("span");
        artist.className = "artist";
        artist.textContent = song.artist;
        b.appendChild(artist);
      }
      // Same as pasting the link: load the video, and remember it under the list's title.
      b.addEventListener("click", function () { nameInput.value = song.title; loadVideo(song.id, song.title); });
      li.appendChild(b);
      ul.appendChild(li);
    });
    $("songs-empty").hidden = list.length > 0;
  }

  // For tests: the same function the player's onError event calls.
  K.app = { handlePlayerError: handlePlayerError };

  refreshState();
  showNote(null);
  renderSongs();
  renderRecent();
  draw(performance.now());
})();
