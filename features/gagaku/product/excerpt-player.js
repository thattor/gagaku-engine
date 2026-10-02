/* Audition controller: explicit crossfades and artificial excerpt exits. */
(function (root) {
  'use strict';
  const FS = 48000, CLIP = 24 * FS, OVERLAP = 19200, STRIDE = CLIP - OVERLAP;
  function finishPlan(seconds) {
    if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds < 0 || seconds > 600) throw new Error('request outside 0..600 seconds');
    const requestFrame = Math.floor(seconds * FS + 1e-7), cycles = Math.floor(requestFrame / STRIDE) + 1;
    return { requestFrame, cycles, endFrame: (cycles - 1) * STRIDE + CLIP };
  }
  const SOURCE_HASHES = new Set(['f691ef4781bbcbf61faf09e22d03c822c9e46132d38cadcbc3082bc4d88b8170',
    'b48c7713eb34ea215ad2b2a97448042463357a0554c3900cd9dd6481e0977ba1']);
  function validateSourceHash(hash) { if (!SOURCE_HASHES.has(hash)) throw new Error('同梱の自前生成WAVだけを選択してください'); }
  class ExcerptController {
    constructor(context, buffer, update = () => {}) {
      if (buffer.sampleRate !== FS || buffer.length !== CLIP || buffer.numberOfChannels !== 2) throw new Error('24秒・48kHz・stereoの合奏WAVを選んでください');
      for (let ch = 0; ch < 2; ch++) {
        const data = buffer.getChannelData(ch);
        if (data[0] !== 0 || data[data.length - 1] !== 0) throw new Error('抜粋の端点が0ではありません');
      }
      this.context = context; this.buffer = buffer; this.update = update;
      this.phase = 'ready'; this.sources = []; this.next = 0; this.log = []; this.finish = null;
    }
    start() {
      if (this.phase !== 'ready') throw new Error('already started');
      this.origin = this.context.currentTime + .08; this.phase = 'playing';
      this.log.push({state: 'playing', time: 0, classification: 'first_line_audition'});
      this.pump(); this.timer = setInterval(() => this.pump(), 50);
    }
    schedule(index) {
      const source = this.context.createBufferSource(), gain = this.context.createGain();
      source.buffer = this.buffer; source.connect(gain); gain.connect(this.context.destination);
      const start = this.origin + index * STRIDE / FS;
      gain.gain.setValueAtTime(index === 0 ? 1 : 0, start);
      if (index > 0) gain.gain.linearRampToValueAtTime(1, start + OVERLAP / FS);
      gain.gain.setValueAtTime(1, start + STRIDE / FS);
      gain.gain.linearRampToValueAtTime(0, start + CLIP / FS);
      source.start(start); this.sources.push({index, start, source, gain});
      // Retain only recent nodes; audio itself has a finite scheduled endpoint.
      this.sources = this.sources.filter(n => n.start + CLIP / FS > this.context.currentTime);
    }
    pump() {
      if (!['playing', 'finish_pending'].includes(this.phase)) return;
      const elapsed = Math.max(0, this.context.currentTime - this.origin);
      if (this.phase === 'playing' && elapsed >= 600) this.requestFinish(600);
      if (this.phase === 'playing') {
        while (this.origin + this.next * STRIDE / FS <= this.context.currentTime + .15) this.schedule(this.next++);
      }
      if (this.phase === 'finish_pending' && this.context.currentTime >= this.origin + this.finish.endFrame / FS) {
        this.phase = 'ended'; clearInterval(this.timer);
        this.log.push({state: 'ended', time: this.finish.endFrame / FS, exitKind: 'author_excerpt_fade', verifiedMusicalExit: false, tomede: false});
        this.sources.forEach(n => { n.source.disconnect(); n.gain.disconnect(); }); this.sources = [];
      }
      this.update(this.phase, elapsed, this.finish);
    }
    requestFinish(seconds = Math.max(0, this.context.currentTime - this.origin)) {
      if (this.phase === 'finish_pending') return this.finish;
      if (this.phase !== 'playing') throw new Error('finish requires playback');
      this.finish = finishPlan(seconds); this.phase = 'finish_pending';
      const lastIndex = this.finish.cycles - 1;
      // A lookahead node can be queued but not yet started: cancel it completely.
      this.sources.filter(n => n.index > lastIndex).forEach(n => n.source.stop());
      this.sources = this.sources.filter(n => n.index <= lastIndex);
      while (this.next <= lastIndex) this.schedule(this.next++);
      const last = this.sources.find(n => n.index === lastIndex);
      // Final clip uses its original .25s PCM release, without a fade to another clip.
      last.gain.gain.cancelScheduledValues(last.start + STRIDE / FS);
      last.gain.gain.setValueAtTime(1, last.start + STRIDE / FS);
      this.log.push({state: 'finish_pending', requestFrame: this.finish.requestFrame, endFrame: this.finish.endFrame,
                     exitKind: 'author_excerpt_fade', verifiedMusicalExit: false, tomede: false});
      this.pump(); return this.finish;
    }
  }
  const api = {finishPlan, validateSourceHash, ExcerptController, FS, CLIP, OVERLAP, STRIDE};
  if (typeof module !== 'undefined') module.exports = api;
  root.ExcerptOperation = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
