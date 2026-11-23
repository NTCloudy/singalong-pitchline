/* Pitch detection and note naming. Pure functions: no DOM, no audio devices, no network. */
(function () {
  "use strict";
  var K = (window.KTV = window.KTV || {});

  var MIN_HZ = 70, MAX_HZ = 1100;      // singing range we look for
  var SILENCE_RMS = 0.01;              // below this the input counts as silence
  var THRESHOLD = 0.15;                // YIN: first dip below this wins
  var MAX_ACCEPT = 0.35;               // otherwise the best dip must be at least this clear
  var NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

  /* detect(samples, sampleRate) -> {freq, clarity, rms} or null (silence / no clear pitch).
   * samples: Float32Array (or array) of one mono block, values in [-1, 1].
   * Method: YIN (difference function, cumulative mean normalisation, first dip under a
   * threshold, parabolic interpolation). Choosing the first clear dip, not the deepest
   * one, is what keeps a strong overtone or a weak fundamental from causing octave errors. */
  function detect(samples, sampleRate) {
    var n = samples.length;
    var tauMin = Math.max(2, Math.floor(sampleRate / MAX_HZ));
    var tauMax = Math.min(Math.floor(sampleRate / MIN_HZ), Math.floor(n / 2));
    if (tauMax <= tauMin + 2) return null;
    var w = n - tauMax, i, tau;
    var sum = 0;
    for (i = 0; i < n; i++) sum += samples[i] * samples[i];
    var rms = Math.sqrt(sum / n);
    if (!(rms >= SILENCE_RMS)) return null;

    var cmnd = new Float32Array(tauMax + 1);
    cmnd[0] = 1;
    var running = 0;
    for (tau = 1; tau <= tauMax; tau++) {
      var d = 0;
      for (i = 0; i < w; i++) {
        var diff = samples[i] - samples[i + tau];
        d += diff * diff;
      }
      running += d;
      cmnd[tau] = running > 0 ? d * tau / running : 1;
    }

    var best = -1;
    for (tau = tauMin; tau < tauMax; tau++) {
      if (cmnd[tau] < THRESHOLD) {
        while (tau + 1 < tauMax && cmnd[tau + 1] < cmnd[tau]) tau++;
        best = tau;
        break;
      }
    }
    if (best < 0) {
      var lo = tauMin;
      for (tau = tauMin + 1; tau < tauMax; tau++) if (cmnd[tau] < cmnd[lo]) lo = tau;
      if (cmnd[lo] > MAX_ACCEPT || lo === tauMin || lo === tauMax - 1) return null;
      best = lo;
    }
    var a = cmnd[best - 1], b = cmnd[best], c = cmnd[best + 1];
    var denom = a - 2 * b + c;
    var shift = denom > 0 ? 0.5 * (a - c) / denom : 0;
    if (shift > 1 || shift < -1) shift = 0;
    var freq = sampleRate / (best + shift);
    if (!(freq >= MIN_HZ && freq <= MAX_HZ)) return null;
    return { freq: freq, clarity: 1 - b, rms: rms };
  }

  /* note(freq) -> {midi (float), name, octave, label, cents}; A4 = 440 Hz = MIDI 69. */
  function note(freq) {
    var midi = 69 + 12 * Math.log(freq / 440) / Math.LN2;
    var nearest = Math.round(midi);
    var name = NAMES[((nearest % 12) + 12) % 12];
    var octave = Math.floor(nearest / 12) - 1;
    return { midi: midi, name: name, octave: octave, label: name + octave, cents: Math.round((midi - nearest) * 100) };
  }

  K.pitch = { detect: detect, note: note, MIN_HZ: MIN_HZ, MAX_HZ: MAX_HZ };
})();
