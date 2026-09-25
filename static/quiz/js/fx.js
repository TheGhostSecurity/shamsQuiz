window.FX = (function () {
    var muted = false;
    try { muted = localStorage.getItem('shamsMute') === '1'; } catch (e) {}
    var ctx = null;
    function ensure() {
        if (!ctx) {
            try { ctx = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) {}
        }
        return ctx;
    }
    function tone(freq, t0, dur, type, vol) {
        if (muted) return;
        var c = ensure();
        if (!c) return;
        var o = c.createOscillator();
        var g = c.createGain();
        o.type = type;
        o.frequency.value = freq;
        g.gain.setValueAtTime(vol, c.currentTime + t0);
        g.gain.exponentialRampToValueAtTime(0.0001, c.currentTime + t0 + dur);
        o.connect(g);
        g.connect(c.destination);
        o.start(c.currentTime + t0);
        o.stop(c.currentTime + t0 + dur + 0.05);
    }
    return {
        isMuted: function () { return muted; },
        setMuted: function (m) {
            muted = m;
            try { localStorage.setItem('shamsMute', m ? '1' : '0'); } catch (e) {}
        },
        toggleMute: function () {
            this.setMuted(!muted);
            if (!muted) this.click();
            return muted;
        },
        click: function () { tone(1400, 0, .06, 'square', .05); },
        tick: function () { tone(1200, 0, .05, 'sine', .06); },
        buzz: function () { tone(300, 0, .12, 'sawtooth', .08); tone(220, .10, .15, 'sawtooth', .08); },
        correct: function () { tone(660, 0, .1, 'square', .07); tone(880, .1, .18, 'square', .07); },
        reveal: function () { tone(440, 0, .12, 'sine', .08); tone(554, .12, .12, 'sine', .08); tone(659, .24, .2, 'sine', .08); },
        fanfare: function () {
            var notes = [523, 659, 784, 1047];
            notes.forEach(function (f, i) { tone(f, i * .12, .18, 'triangle', .09); });
            tone(1319, .5, .4, 'triangle', .09);
        },
        confetti: function () {
            var canvas = document.createElement('canvas');
            canvas.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:9999;';
            document.body.appendChild(canvas);
            var w = canvas.width = window.innerWidth;
            var h = canvas.height = window.innerHeight;
            var g = canvas.getContext('2d');
            var colors = ['#0078d4', '#d99322', '#107c41', '#dc2626', '#7c3aed', '#e8a63d'];
            var parts = [];
            for (var i = 0; i < 140; i++) {
                parts.push({
                    x: Math.random() * w,
                    y: Math.random() * -h * 0.6,
                    vx: (Math.random() - .5) * 2,
                    vy: 2 + Math.random() * 3.5,
                    s: 5 + Math.random() * 7,
                    r: Math.random() * Math.PI,
                    vr: (Math.random() - .5) * .3,
                    c: colors[(Math.random() * colors.length) | 0],
                    ov: Math.random() * .9
                });
            }
            var start = null;
            function frame(t) {
                if (!start) start = t;
                var elapsed = t - start;
                if (elapsed > 5000) { canvas.remove(); return; }
                g.clearRect(0, 0, w, h);
                var fading = elapsed > 3800 ? (5000 - elapsed) / 1200 : 1;
                for (var i = 0; i < parts.length; i++) {
                    var p = parts[i];
                    p.x += p.vx;
                    p.y += p.vy;
                    p.r += p.vr;
                    g.save();
                    g.globalAlpha = p.ov * fading;
                    g.translate(p.x, p.y);
                    g.rotate(p.r);
                    g.fillStyle = p.c;
                    g.fillRect(-p.s / 2, -p.s / 2, p.s, p.s * .6);
                    g.restore();
                }
                requestAnimationFrame(frame);
            }
            requestAnimationFrame(frame);
        }
    };
})();