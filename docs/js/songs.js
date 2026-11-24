/* The song list. To add songs, edit only this file.
 *
 * One line per song, three text fields:
 *   { title: "歌名", artist: "歌手", id: "YouTube 影片代碼" },
 *
 * - id is the 11 characters after "watch?v=" (or after "youtu.be/") in the video's address.
 * - artist may be "" (empty). title and id must not be empty.
 * - Lines that do not follow the format are skipped; the rest still show.
 */
(function () {
  "use strict";
  var K = (window.KTV = window.KTV || {});
  K.songs = [
  ];
})();
