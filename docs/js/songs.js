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
    { title: "甲乙丙丁Strangers", artist: "李佳薇", id: "YacpC7sUXMM" },
    { title: "欲落未落", artist: "DIOR大穎", id: "XyNHhf1cklQ" },
    { title: "沒有人像我一樣", artist: "宇宙人", id: "dRSZhZT6r-Y" },
    { title: "離開我的依賴", artist: "王艷薇", id: "p13tH7Etlzc" },
    { title: "幸福在歌唱", artist: "A-Lin", id: "jeRu6h4XbUU" },
    { title: "跳樓機", artist: "LBI利比", id: "HegSBovl24I" },
    { title: "擱淺", artist: "周杰倫", id: "YJfHuATJYsQ" },
    { title: "太陽與地球", artist: "盧廣仲", id: "i5YRIjxyJP8" },
    { title: "晴天", artist: "周杰倫", id: "DYptgVvkVLQ" },
    { title: "我不難過", artist: "孫燕姿", id: "GDsyUtdS1YM" },
    { title: "APT.", artist: "ROSÉ & Bruno Mars", id: "ekr2nIex040" },
    { title: "Training Season", artist: "Dua Lipa", id: "ZjBZ8MUnB0E" },
    { title: "Love Story", artist: "Taylor Swift", id: "8xg3vE8Ie_E" },
    { title: "Lemon", artist: "米津玄師", id: "SX_ViT4Ra7k" },
    { title: "群青", artist: "YOASOBI", id: "Y4nEEZwckuU" },
    { title: "NIGHT DANCER", artist: "imase", id: "kagoEGKHZvU" },
    { title: "紅蓮華", artist: "LiSA", id: "x1FV6IrjZCY" },
    { title: "Love Options", artist: "BESTie", id: "NPqtL1dtrlA" },
    { title: "Looks Can Kill", artist: "IVE", id: "rsNhWkC4neE" },
    { title: "Golden", artist: "HUNTR/X", id: "yebNIHKAC4A" },
  ];
})();
