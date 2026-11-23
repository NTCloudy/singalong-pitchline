/* YouTube link parsing. Pure function: no DOM, no network. */
(function () {
  "use strict";
  var K = (window.KTV = window.KTV || {});
  var ID = /^[A-Za-z0-9_-]{11}$/;
  var HOSTS = { "youtube.com": 1, "www.youtube.com": 1, "m.youtube.com": 1, "music.youtube.com": 1 };

  /* videoId(text) -> the 11-character video id, or null.
   * Accepts watch?v=, youtu.be/ and /shorts/ links (with or without https://). */
  function videoId(text) {
    if (typeof text !== "string") return null;
    var s = text.trim();
    if (!s || /\s/.test(s)) return null;
    if (!/^https?:\/\//i.test(s)) s = "https://" + s;
    var u;
    try { u = new URL(s); } catch (e) { return null; }
    if (u.protocol !== "https:" && u.protocol !== "http:") return null;
    var host = u.hostname.toLowerCase(), id = null;
    if (host === "youtu.be") {
      id = u.pathname.split("/")[1] || "";
    } else if (HOSTS[host]) {
      var parts = u.pathname.split("/");
      if (u.pathname === "/watch") id = u.searchParams.get("v") || "";
      else if (parts[1] === "shorts") id = parts[2] || "";
    }
    return id && ID.test(id) ? id : null;
  }

  K.link = { videoId: videoId };
})();
