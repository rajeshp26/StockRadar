# Code Examples - Ania Kubow Design Patterns

Original minimal implementations for each pattern in `design-examples.md`. Each example is self-contained HTML + CSS unless noted. Copy the block, paste into an `.html` file, open in a browser. No framework, no build step.

Conventions used throughout:
- `.demo` is the wrapper for each example.
- Colours use `color-mix()` and CSS variables where that is the point of the example, plain hex otherwise.
- Reduced-motion and fallback notes are included where the technique needs one.

---

## 1. CSS Visual Effects and Motion

### 1.1 Album-art effect
Poster-like cover built from layered gradients, no image asset.

```html
<div class="album">
  <span class="album-title">MIDNIGHT</span>
  <span class="album-sub">SYNTH • 1984</span>
  <div class="album-disc"></div>
</div>
<style>
.album{position:relative;width:280px;aspect-ratio:1;overflow:hidden;border-radius:12px;
  background:linear-gradient(160deg,#2b1055 0%,#7597de 55%,#ff9a8b 100%);color:#fff;
  font-family:system-ui,sans-serif;display:flex;flex-direction:column;justify-content:flex-end;padding:20px}
.album-title{font-size:34px;font-weight:900;letter-spacing:.08em}
.album-sub{font-size:12px;letter-spacing:.3em;opacity:.85}
.album-disc{position:absolute;right:-40px;top:-40px;width:160px;height:160px;border-radius:50%;
  background:radial-gradient(circle at 35% 35%,#ffd93d,#ff6b6b 55%,#2b1055 75%)}
</style>
```

### 1.2 Shiny / premium card
Moving highlight sweeping across a card.

```html
<div class="shine-card"><h3>Pro Plan</h3><p>Everything unlimited.</p></div>
<style>
.shine-card{position:relative;overflow:hidden;width:260px;padding:24px;border-radius:16px;
  background:#111;color:#fff;font-family:system-ui,sans-serif}
.shine-card::after{content:"";position:absolute;inset:0;
  background:linear-gradient(105deg,transparent 40%,rgba(255,255,255,.35) 50%,transparent 60%);
  transform:translateX(-120%);animation:shine 3.2s ease-in-out infinite}
@keyframes shine{0%,60%{transform:translateX(-120%)}100%{transform:translateX(120%)}}
@media (prefers-reduced-motion:reduce){.shine-card::after{animation:none}}
</style>
```

### 1.3 Neon signs / light spill
Glow plus a soft spill on the surface below.

```html
<div class="neon-wrap"><div class="neon">OPEN</div><div class="neon-spill"></div></div>
<style>
.neon-wrap{background:#0a0a12;padding:32px;text-align:center;font-family:system-ui,sans-serif}
.neon{font-size:56px;font-weight:900;letter-spacing:.15em;color:#fff;
  text-shadow:0 0 6px #ff2ea6,0 0 18px #ff2ea6,0 0 42px #ff2ea6,0 0 80px #ff2ea6}
.neon-spill{height:40px;margin:8px 40px 0;border-radius:50%;
  background:radial-gradient(ellipse at center,rgba(255,46,166,.55),transparent 70%);
  filter:blur(8px)}
</style>
```

### 1.4 Holographic tickets
Iridescent ticket with perforated edge.

```html
<div class="ticket"><div><strong>LIVE • FRI</strong><p>General Admission</p></div><div class="stub">A12</div></div>
<style>
.ticket{display:flex;width:320px;border-radius:12px;overflow:hidden;color:#111;
  font-family:system-ui,sans-serif;
  background:linear-gradient(115deg,#a8edea,#fed6e3 30%,#d0bfff 55%,#a8edea 80%);background-size:200% 200%;
  animation:holo 6s linear infinite}
@keyframes holo{to{background-position:200% 0}}
.ticket>div:first-child{padding:18px;flex:1}
.stub{padding:18px;border-left:2px dashed rgba(0,0,0,.25);display:grid;place-items:center;font-weight:800;letter-spacing:.2em}
@media (prefers-reduced-motion:reduce){.ticket{animation:none}}
</style>
```

### 1.5 Odometer / rolling numbers
Digits roll vertically like a mechanical counter.

```html
<div class="odometer" aria-label="12,480"><span class="digit"><span class="reel">0 1 2 3 4 5 6 7 8 9</span></span><span class="digit"><span class="reel">0 1 2 3 4 5 6 7 8 9</span></span></div>
<style>
.odometer{display:flex;gap:4px;font-family:ui-monospace,monospace;font-size:32px}
.digit{width:1ch;height:1.2em;overflow:hidden;background:#111;color:#fff;border-radius:6px;text-align:center}
.reel{display:block;line-height:1.2em;white-space:pre;animation:roll 4s steps(9,end) infinite}
@keyframes roll{to{transform:translateY(-90%)}}
</style>
<!-- Tip: set the final translateY / steps to land on the target digit for a real counter, or drive it with JS by setting transform per digit. -->
```

### 1.6 Glowing AI voice orb
Soft luminous core from gradients + blur.

```html
<div class="orb" aria-label="Listening"></div>
<style>
.orb{width:96px;height:96px;border-radius:50%;margin:20px;
  background:radial-gradient(circle at 35% 30%,#fff,#a78bfa 35%,#6366f1 65%,#1e1b4b);
  box-shadow:0 0 24px #8b5cf6,0 0 64px #6366f1,0 0 120px #a78bfa;
  animation:breathe 2.4s ease-in-out infinite}
@keyframes breathe{50%{transform:scale(1.08);filter:brightness(1.15)}}
@media (prefers-reduced-motion:reduce){.orb{animation:none}}
</style>
```

### 1.7 Checkerboard gradients
Checkerboard from one background property, no images.

```html
<div class="checker"></div>
<style>
.checker{width:240px;height:160px;border-radius:10px;border:1px solid #ddd;
  background-image:linear-gradient(45deg,#ccc 25%,transparent 25%),
    linear-gradient(-45deg,#ccc 25%,transparent 25%),
    linear-gradient(45deg,transparent 75%,#ccc 75%),
    linear-gradient(-45deg,transparent 75%,#ccc 75%);
  background-size:24px 24px;background-position:0 0,0 12px,12px -12px,-12px 0}
</style>
```

### 1.8 Frosted / real glass
Glass with blur + distortion hint + highlight, text stays readable.

```html
<div class="glass-scene"><div class="glass-card"><h3>Glass card</h3><p>Text stays readable over the blur.</p></div></div>
<style>
.glass-scene{padding:28px;background:linear-gradient(135deg,#ff9a8b,#a78bfa,#60a5fa);font-family:system-ui,sans-serif}
.glass-card{max-width:280px;padding:22px;border-radius:18px;color:#111;
  background:rgba(255,255,255,.28);backdrop-filter:blur(14px) saturate(1.4);
  -webkit-backdrop-filter:blur(14px) saturate(1.4);
  border:1px solid rgba(255,255,255,.55);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.6),0 12px 32px rgba(0,0,0,.18)}
</style>
```

### 1.9 Infinite marquee
Seamless loop by duplicating content.

```html
<div class="marquee"><div class="track"><span>Design • Code • Ship •&nbsp;</span><span aria-hidden="true">Design • Code • Ship •&nbsp;</span></div></div>
<style>
.marquee{overflow:hidden;white-space:nowrap;background:#111;color:#fff;padding:12px 0;font-family:system-ui,sans-serif}
.track{display:inline-flex;animation:scroll 12s linear infinite}
@keyframes scroll{to{transform:translateX(-50%)}}
@media (prefers-reduced-motion:reduce){.track{animation:none}}
</style>
```

### 1.10 Pulsating dot (AI apps)
Calm pulsing indicator for listening / activity.

```html
<span class="pulse-dot" aria-label="Listening"></span>
<style>
.pulse-dot{display:inline-block;width:12px;height:12px;border-radius:50%;background:#22c55e;position:relative}
.pulse-dot::after{content:"";position:absolute;inset:-4px;border-radius:50%;
  border:2px solid #22c55e;animation:ping 1.6s ease-out infinite}
@keyframes ping{0%{transform:scale(.6);opacity:.9}100%{transform:scale(1.6);opacity:0}}
@media (prefers-reduced-motion:reduce){.pulse-dot::after{animation:none}}
</style>
```

### 1.11 Pixel art in HTML/CSS
Grid pixels forming a heart.

```html
<div class="pixel" role="img" aria-label="Pixel heart"></div>
<style>
.pixel{--p:14px;width:calc(var(--p)*7);height:calc(var(--p)*6);
  background:
    linear-gradient(#ef4444,#ef4444) calc(var(--p)*1) 0 / var(--p) var(--p),
    linear-gradient(#ef4444,#ef4444) calc(var(--p)*2) 0 / var(--p) var(--p),
    linear-gradient(#ef4444,#ef4444) calc(var(--p)*4) 0 / var(--p) var(--p),
    linear-gradient(#ef4444,#ef4444) calc(var(--p)*5) 0 / var(--p) var(--p),
    linear-gradient(#ef4444,#ef4444) 0 var(--p) / var(--p) var(--p),
    linear-gradient(#ef4444,#ef4444) calc(var(--p)*3) var(--p) / var(--p) var(--p),
    linear-gradient(#ef4444,#ef4444) calc(var(--p)*6) var(--p) / var(--p) var(--p),
    linear-gradient(#ef4444,#ef4444) calc(var(--p)*1) calc(var(--p)*2) / var(--p) var(--p),
    linear-gradient(#ef4444,#ef4444) calc(var(--p)*5) calc(var(--p)*2) / var(--p) var(--p),
    linear-gradient(#ef4444,#ef4444) calc(var(--p)*2) calc(var(--p)*3) / var(--p) var(--p),
    linear-gradient(#ef4444,#ef4444) calc(var(--p)*4) calc(var(--p)*3) / var(--p) var(--p),
    linear-gradient(#ef4444,#ef4444) calc(var(--p)*3) calc(var(--p)*4) / var(--p) var(--p),
    linear-gradient(#ef4444,#ef4444) calc(var(--p)*3) calc(var(--p)*5) / var(--p) var(--p);
  background-repeat:no-repeat}
</style>
<!-- Simpler alternative: use box-shadow pixels on a 1px element, or a CSS grid of divs. -->
```

### 1.12 Aurora inside letters
Gradient clipped to text.

```html
<h1 class="aurora">Make it glow</h1>
<style>
.aurora{font-family:system-ui,sans-serif;font-size:56px;font-weight:900;letter-spacing:-.02em;
  background:linear-gradient(90deg,#22d3ee,#a78bfa,#f472b6,#facc15,#22d3ee);
  background-size:300% 100%;-webkit-background-clip:text;background-clip:text;color:transparent;
  animation:drift 8s linear infinite}
@keyframes drift{to{background-position:300% 0}}
@media (prefers-reduced-motion:reduce){.aurora{animation:none}}
</style>
```

### 1.13 CSS video effect
Stylise video with filters + overlay, with fallback.

```html
<div class="video-hero"><video autoplay muted loop playsinline src="hero.mp4"></video><div class="video-label">Hero video</div></div>
<style>
.video-hero{position:relative;overflow:hidden;border-radius:16px;max-width:560px}
.video-hero video{display:block;width:100%;filter:saturate(1.3) contrast(1.1) hue-rotate(-12deg)}
.video-hero::after{content:"";position:absolute;inset:0;
  background:linear-gradient(180deg,transparent 55%,rgba(0,0,0,.55))}
.video-label{position:absolute;left:16px;bottom:14px;z-index:1;color:#fff;font-family:system-ui,sans-serif;font-weight:700}
</style>
```

### 1.14 Metaball effect
Blobs merging via blur + contrast.

```html
<div class="meta"><span class="blob b1"></span><span class="blob b2"></span><span class="blob b3"></span></div>
<style>
.meta{position:relative;width:280px;height:140px;overflow:hidden;background:#fff;filter:contrast(18);border-radius:12px}
.blob{position:absolute;width:64px;height:64px;border-radius:50%;background:#111;filter:blur(10px);animation:drift 6s ease-in-out infinite alternate}
.b1{left:30px;top:35px}.b2{left:110px;top:45px;animation-delay:-2s}.b3{left:190px;top:30px;animation-delay:-4s}
@keyframes drift{to{transform:translateY(22px) translateX(14px)}}
@media (prefers-reduced-motion:reduce){.blob{animation:none}}
</style>
```

### 1.15 Rotating glow border (@property)
Conic glow rotating around a card. Needs @property support, with static fallback.

```html
<div class="glow-card"><h3>Premium</h3><p>Rotating border, static fallback below.</p></div>
<style>
@property --angle{syntax:"<angle>";initial-value:0deg;inherits:false}
.glow-card{position:relative;padding:24px;border-radius:16px;background:#111;color:#fff;
  font-family:system-ui,sans-serif;isolation:isolate}
.glow-card::before{content:"";position:absolute;inset:-2px;border-radius:18px;z-index:-1;
  background:conic-gradient(from var(--angle),#22d3ee,#a78bfa,#f472b6,#facc15,#22d3ee);
  animation:spin 4s linear infinite}
@keyframes spin{to{--angle:360deg}}
@supports not (background:conic-gradient(from 0deg,red,blue)){.glow-card::before{background:linear-gradient(135deg,#22d3ee,#a78bfa,#f472b6);animation:none}}
@media (prefers-reduced-motion:reduce){.glow-card::before{animation:none}}
</style>
```

### 1.16 Scroll-driven bar fill
Progress bar tied to scroll, no JavaScript.

```html
<div class="progress"></div><div style="height:1200px;padding:20px;font-family:system-ui">Scroll this page - the bar fills.</div>
<style>
.progress{position:fixed;top:0;left:0;height:4px;width:100%;z-index:10;
  background:linear-gradient(90deg,#22d3ee,#a78bfa);
  transform-origin:0 50%;scale:0 1;
  animation:fill linear both;animation-timeline:scroll(root)}
@keyframes fill{to{scale:1 1}}
@supports not (animation-timeline:scroll()){.progress{display:none}}
</style>
```


---

## 2. UI Components and Interaction

### 2.1 Gliding pill
Active indicator glides between tabs.

```html
<div class="tabs"><button class="active">Day</button><button>Week</button><button>Month</button><span class="pill"></span></div>
<style>
.tabs{position:relative;display:inline-flex;background:#eee;border-radius:999px;padding:4px;font-family:system-ui,sans-serif}
.tabs button{position:relative;z-index:1;border:0;background:transparent;padding:8px 18px;border-radius:999px;cursor:pointer;font:inherit}
.pill{position:absolute;top:4px;bottom:4px;left:4px;width:calc((100% - 8px)/3);background:#111;border-radius:999px;transition:transform .3s ease}
.tabs button:nth-child(2).active ~ .pill{transform:translateX(100%)}
.tabs button:nth-child(3).active ~ .pill{transform:translateX(200%)}
</style>
<!-- In real code, move .pill with JS on click, or use :has() to position it: .tabs:has(button:nth-child(2).active) .pill { transform:translateX(100%) } -->
```

### 2.2 Avatar from two HTML tags
Minimal markup, CSS shapes only.

```html
<div class="avatar"><span></span></div>
<style>
.avatar{width:96px;height:96px;border-radius:50%;background:#fde68a;position:relative;overflow:hidden}
.avatar::before{content:"";position:absolute;left:50%;top:18px;width:36px;height:36px;transform:translateX(-50%);
  background:#fbbf24;border-radius:50%;box-shadow:inset 0 0 0 4px #111}
.avatar span{position:absolute;left:50%;bottom:-14px;width:64px;height:52px;transform:translateX(-50%);
  background:#111;border-radius:32px 32px 0 0}
.avatar span::before,.avatar span::after{content:"";position:absolute;top:14px;width:8px;height:8px;border-radius:50%;background:#fff}
.avatar span::before{left:12px}.avatar span::after{right:12px}
</style>
<!-- Two tags: div.avatar + span. Pseudo-elements do the face details. -->
```

### 2.3 3D carousel (pure CSS)
Transforms arrange items in depth. Hover / radio version, no JS.

```html
<div class="carousel"><input type="radio" name="c" id="c1" checked><input type="radio" name="c" id="c2"><input type="radio" name="c" id="c3">
<label for="c1" class="card3d">One</label><label for="c2" class="card3d">Two</label><label for="c3" class="card3d">Three</label></div>
<style>
.carousel{position:relative;height:180px;display:flex;justify-content:center;align-items:center;perspective:800px;font-family:system-ui,sans-serif}
.carousel input{position:absolute;opacity:0}
.card3d{position:absolute;width:130px;height:160px;display:grid;place-items:center;border-radius:14px;
  background:#111;color:#fff;font-weight:800;cursor:pointer;transition:transform .45s ease,opacity .45s ease}
.carousel:has(#c1:checked) label:nth-of-type(1){transform:translateX(0) translateZ(80px)}
.carousel:has(#c1:checked) label:nth-of-type(2){transform:translateX(110px) rotateY(-28deg) scale(.88);opacity:.7}
.carousel:has(#c1:checked) label:nth-of-type(3){transform:translateX(-110px) rotateY(28deg) scale(.88);opacity:.7}
.carousel:has(#c2:checked) label:nth-of-type(2){transform:translateX(0) translateZ(80px)}
.carousel:has(#c2:checked) label:nth-of-type(3){transform:translateX(110px) rotateY(-28deg) scale(.88);opacity:.7}
.carousel:has(#c2:checked) label:nth-of-type(1){transform:translateX(-110px) rotateY(28deg) scale(.88);opacity:.7}
.carousel:has(#c3:checked) label:nth-of-type(3){transform:translateX(0) translateZ(80px)}
.carousel:has(#c3:checked) label:nth-of-type(1){transform:translateX(110px) rotateY(-28deg) scale(.88);opacity:.7}
.carousel:has(#c3:checked) label:nth-of-type(2){transform:translateX(-110px) rotateY(28deg) scale(.88);opacity:.7}
</style>
```

### 2.4 Before / after slider (clip-path)
Drag handle reveals one layer over another.

```html
<div class="compare"><img src="before.jpg" alt="Before"><div class="after"><img src="after.jpg" alt="After"></div><input type="range" min="0" max="100" value="50" aria-label="Before after slider"></div>
<style>
.compare{position:relative;max-width:480px;aspect-ratio:16/10;overflow:hidden;border-radius:12px}
.compare img{width:100%;height:100%;object-fit:cover;display:block}
.after{position:absolute;inset:0;clip-path:inset(0 0 0 50%)}
.compare input{position:absolute;inset:0;width:100%;appearance:none;background:transparent;cursor:ew-resize}
.compare input::-webkit-slider-thumb{appearance:none;width:4px;height:100%;background:#fff;box-shadow:0 0 0 2px #111}
.compare:has(input[value]) .after{clip-path:inset(0 0 0 var(--pos,50%))}
</style>
<script>
const c=document.querySelector('.compare'), r=c.querySelector('input');
const update=()=>c.style.setProperty('--pos', r.value+'%');
r.addEventListener('input',update); update();
</script>
<!-- Pure-CSS alternative: set clip-path with style="--pos:50%" and update via JS as above. Keep handle large on touch: add a 28px thumb hit area. -->
```

### 2.5 Boring buttons + overlays
Layering + visible hover / active states.

```html
<button class="btn">Get started</button>
<style>
.btn{position:relative;overflow:hidden;border:0;border-radius:999px;padding:12px 26px;
  background:#111;color:#fff;font:600 15px system-ui,sans-serif;cursor:pointer;transition:transform .15s ease,box-shadow .2s ease}
.btn::after{content:"";position:absolute;inset:0;
  background:linear-gradient(105deg,transparent 40%,rgba(255,255,255,.28) 50%,transparent 60%);
  transform:translateX(-120%);transition:transform .45s ease}
.btn:hover::after{transform:translateX(120%)}
.btn:hover{box-shadow:0 8px 22px rgba(0,0,0,.25)}
.btn:active{transform:scale(.97)}
.btn:focus-visible{outline:3px solid #22d3ee;outline-offset:3px}
</style>
```

### 2.6 Custom checkbox styling
Native behaviour, custom look, unmistakable checked state.

```html
<label class="check"><input type="checkbox"><span class="box" aria-hidden="true"></span> Email me updates</label>
<style>
.check{display:inline-flex;align-items:center;gap:10px;font-family:system-ui,sans-serif;cursor:pointer}
.check input{position:absolute;opacity:0}
.box{width:22px;height:22px;border:2px solid #111;border-radius:6px;display:grid;place-items:center;transition:background .15s ease}
.box::after{content:"✓";color:#fff;font-size:15px;font-weight:900;opacity:0;transform:scale(.6);transition:.15s ease}
.check input:checked + .box{background:#111}
.check input:checked + .box::after{opacity:1;transform:scale(1)}
.check input:focus-visible + .box{outline:3px solid #22d3ee;outline-offset:2px}
</style>
```

### 2.7 Textarea resize
Control resize direction, prevent layout breakage.

```html
<textarea class="field" rows="4" placeholder="Leave a comment…"></textarea>
<style>
.field{width:100%;max-width:420px;min-height:96px;max-height:260px;padding:12px;
  border:1px solid #ccc;border-radius:10px;font:inherit;resize:vertical}
.field.no-resize{resize:none}
.field.horizontal-only{resize:horizontal}
</style>
<!-- resize: vertical | horizontal | both | none. Always set min/max sizes. -->
```

---

## 3. Shapes, Icons and Brand

### 3.1 Logo from SVG
Crisp vector mark, scales to any size.

```html
<svg width="48" height="48" viewBox="0 0 48 48" role="img" aria-label="Logo"><circle cx="24" cy="24" r="22" fill="#111"/><path d="M14 32 L24 12 L34 32" fill="none" stroke="#fff" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><circle cx="24" cy="28" r="3" fill="#facc15"/></svg>
<!-- Use as inline SVG for logos, or <img src="logo.svg">. Keep shapes simple, avoid tiny detail. -->
```

### 3.2 Apple icon shapes / squircles
Squircle vs rounded square - shape is identity.

```html
<div class="icon-row"><div class="app-icon rounded">A</div><div class="app-icon squircle">A</div></div>
<style>
.icon-row{display:flex;gap:16px}
.app-icon{width:64px;height:64px;display:grid;place-items:center;background:linear-gradient(135deg,#60a5fa,#8b5cf6);color:#fff;font:800 28px system-ui,sans-serif}
.rounded{border-radius:16px}
.squircle{border-radius:32% / 28%;border-radius:28px;corner-shape:squircle}
@supports (corner-shape:squircle){.squircle{border-radius:22px;corner-shape:squircle}}
</style>
```

### 3.3 Squircle via corner-shape
True squircle corners in CSS.

```html
<div class="squircle-card">Squircle card</div>
<style>
.squircle-card{width:220px;padding:28px;border-radius:24px;background:#111;color:#fff;
  font-family:system-ui,sans-serif;corner-shape:squircle}
/* Fallback: browsers without corner-shape fall back to border-radius above. */
</style>
```

### 3.4 Brand colours from a website
Derive brand colours from a site URL - concept code, verify against real brand.

```js
// Concept: fetch the site, read theme-color + dominant colours from its logo / CSS.
// In production, run this server-side or with a colour-extraction lib, and always verify.
async function brandFromUrl(url) {
  const html = await (await fetch(url)).text();
  const theme = html.match(/name=["']theme-color["'] content=["']([^"']+)["']/i)?.[1];
  return { themeColor: theme ?? null, note: 'Verify extracted colours against the real brand guide before use.' };
}
```

```html
<!-- Simpler, reliable version: read the site's own declared tokens -->
<meta name="theme-color" content="#111827">
<style>:root{--brand:#111827;--brand-soft:color-mix(in srgb,var(--brand) 12%,white)}</style>
```

### 3.5 Highlighting brand colours
Brand colour sparingly for emphasis.

```html
<p class="copy">Ship faster with <mark>one</mark> clear call to action.</p>
<style>
.copy{font:18px/1.6 system-ui,sans-serif;max-width:420px;color:#111}
.copy mark{background:transparent;color:inherit;
  background-image:linear-gradient(transparent 62%,#facc15 62%,#facc15 94%,transparent 94%)}
</style>
```

---

## 4. Colour, Typography and Theming

### 4.1 CSS colour mixing
Native tints / shades without a preprocessor.

```html
<button class="mix-btn">Hover me</button>
<style>
.mix-btn{--brand:#6366f1;border:0;border-radius:999px;padding:12px 24px;color:#fff;
  background:var(--brand);font:600 15px system-ui,sans-serif;cursor:pointer;transition:background .2s ease}
.mix-btn:hover{background:color-mix(in srgb,var(--brand) 82%,white)}
.mix-btn:active{background:color-mix(in srgb,var(--brand) 82%,black)}
.mix-btn:disabled{background:color-mix(in srgb,var(--brand) 35%,transparent);cursor:not-allowed}
</style>
```

### 4.2 Auto-changing text colour
Text adapts to its background.

```html
<div class="adaptive">Readable on any photo</div>
<style>
.adaptive{padding:36px;border-radius:14px;font:800 22px system-ui,sans-serif;
  background-image:url('photo.jpg');background-size:cover;background-position:center;
  color:#fff;text-shadow:0 1px 0 rgba(0,0,0,.4),0 0 18px rgba(0,0,0,.45)}
/* Robust version: put text on a scrim, not raw on the image */
.adaptive-alt{position:relative;isolation:isolate}
.adaptive-alt::before{content:"";position:absolute;inset:0;z-index:-1;background:linear-gradient(180deg,rgba(0,0,0,.15),rgba(0,0,0,.55));border-radius:inherit}
</style>
```

### 4.3 Light / dark mode in two lines
Native colour-scheme switch.

```html
<style>
:root{color-scheme:light dark}
body{background:light-dark(#fff,#111);color:light-dark(#111,#fff);font-family:system-ui,sans-serif}
.card{background:light-dark(#f3f4f6,#1f2937);border:1px solid light-dark(#e5e7eb,#374151);border-radius:14px;padding:20px}
</style>
<div class="card">This card follows your OS theme. Background, text, and border switch together.</div>
<!-- Equivalent two-line core: :root{color-scheme:light dark} + use light-dark() for surfaces. For manual toggle, set color-scheme on :root via JS / data-theme. -->
```


---

## 5. Layout, Responsive and UX

### 5.1 Pinterest responsive grid
Masonry-style grid. Native masonry is experimental - grid version below is the safe production pattern.

```html
<div class="masonry"><figure><img src="a.jpg" alt=""><figcaption>Short</figcaption></figure><figure class="tall"><img src="b.jpg" alt=""><figcaption>Tall card with more text</figcaption></figure><figure><img src="c.jpg" alt=""><figcaption>Short</figcaption></figure></div>
<style>
/* Experimental native masonry (check support before shipping): */
/* .masonry{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));grid-template-rows:masonry;gap:14px} */
.masonry{columns:3 180px;column-gap:14px}
.masonry figure{break-inside:avoid;margin:0 0 14px;border-radius:12px;overflow:hidden;background:#f3f4f6;font-family:system-ui,sans-serif}
.masonry img{width:100%;display:block}
.masonry .tall img{aspect-ratio:3/4;object-fit:cover}
.masonry figcaption{padding:10px 12px}
</style>
```

### 5.2 One-letter mobile layout change
One value flips stacked to side-by-side.

```html
<div class="split"><div>Text side</div><div>Image side</div></div>
<style>
.split{display:grid;gap:16px;font-family:system-ui,sans-serif}
/* Change ONE value to flip layout: */
@media (min-width:640px){.split{grid-template-columns:1fr 1fr}}
/* Or with flex: .split{display:flex;flex-direction:column} -> row at breakpoint. Test on real phone widths. */
</style>
```

### 5.3 Zooming forms on mobile
Prevent auto-zoom by sizing inputs at 16px+.

```html
<form class="form"><label>Email<input type="email" placeholder="you@example.com"></label><button>Continue</button></form>
<style>
.form{font-family:system-ui,sans-serif;max-width:360px}
.form input,.form button{width:100%;padding:12px;border-radius:10px;border:1px solid #ccc;font-size:16px}
.form button{margin-top:10px;background:#111;color:#fff;border:0;font-weight:600}
/* Key rule: input font-size must be >= 16px on iOS, otherwise Safari zooms on focus. Do not use maximum-scale=1 to block zoom - it harms accessibility. */
</style>
```

### 5.4 Focus-within / child focus
Style a parent when any child is focused.

```html
<div class="field-group"><label>Card number<input type="text" inputmode="numeric" placeholder="4242 4242 4242 4242"></label><label>Expiry<input type="text" placeholder="MM / YY"></label></div>
<style>
.field-group{display:flex;gap:12px;padding:16px;border:2px solid #e5e7eb;border-radius:14px;font-family:system-ui,sans-serif;transition:border-color .2s ease,box-shadow .2s ease}
.field-group:focus-within{border-color:#111;box-shadow:0 0 0 3px rgba(34,211,238,.45)}
.field-group label{display:flex;flex-direction:column;gap:6px;flex:1;font-size:13px;font-weight:600}
.field-group input{padding:10px;border:1px solid #d1d5db;border-radius:8px;font-size:16px}
.field-group input:focus{outline:none;border-color:#111}
</style>
```

### 5.5 Reduced motion
Honour the preference, offer a calmer alternative.

```html
<div class="float-card">Gentle motion</div>
<style>
.float-card{width:200px;padding:22px;border-radius:14px;background:#111;color:#fff;font-family:system-ui,sans-serif;
  animation:float 4s ease-in-out infinite}
@keyframes float{50%{transform:translateY(-8px)}}
@media (prefers-reduced-motion:reduce){
  .float-card{animation:none;transition:none}
  *,*::before,*::after{animation-duration:.01ms !important;animation-iteration-count:1 !important;scroll-behavior:auto !important}
}
</style>
```

### 5.6 Hero images loading
Prioritise the hero image so first view feels fast.

```html
<!-- Preload + fetchpriority + responsive sizes. Balance quality vs load time. -->
<link rel="preload" as="image" href="hero-1600.jpg" imagesrcset="hero-800.jpg 800w, hero-1600.jpg 1600w" imagesizes="100vw" fetchpriority="high">
<img src="hero-1600.jpg" srcset="hero-800.jpg 800w, hero-1600.jpg 1600w" sizes="100vw" width="1600" height="900" fetchpriority="high" decoding="async" alt="Product hero" style="width:100%;height:auto;display:block;border-radius:16px">
<!-- Do NOT lazy-load the hero. Lazy-load below-the-fold images with loading="lazy" instead. -->
```

---

## Quick index

| # | Pattern | File section |
|---|---------|--------------|
| 1.1 | Album-art | 1.1 |
| 1.2 | Shiny card | 1.2 |
| 1.3 | Neon | 1.3 |
| 1.4 | Holographic tickets | 1.4 |
| 1.5 | Odometer | 1.5 |
| 1.6 | AI orb | 1.6 |
| 1.7 | Checkerboard | 1.7 |
| 1.8 | Frosted glass | 1.8 |
| 1.9 | Marquee | 1.9 |
| 1.10 | Pulsating dot | 1.10 |
| 1.11 | Pixel art | 1.11 |
| 1.12 | Aurora text | 1.12 |
| 1.13 | Video effect | 1.13 |
| 1.14 | Metaball | 1.14 |
| 1.15 | Rotating glow border | 1.15 |
| 1.16 | Scroll bar | 1.16 |
| 2.1 | Gliding pill | 2.1 |
| 2.2 | 2-tag avatar | 2.2 |
| 2.3 | 3D carousel | 2.3 |
| 2.4 | Before / after | 2.4 |
| 2.5 | Button overlays | 2.5 |
| 2.6 | Custom checkbox | 2.6 |
| 2.7 | Textarea resize | 2.7 |
| 3.1 | SVG logo | 3.1 |
| 3.2 | Squircles | 3.2 |
| 3.3 | corner-shape | 3.3 |
| 3.4 | Brand colours | 3.4 |
| 3.5 | Highlight brand | 3.5 |
| 4.1 | Colour mixing | 4.1 |
| 4.2 | Adaptive text | 4.2 |
| 4.3 | Light / dark | 4.3 |
| 5.1 | Masonry grid | 5.1 |
| 5.2 | Mobile layout flip | 5.2 |
| 5.3 | Mobile form zoom | 5.3 |
| 5.4 | Focus-within | 5.4 |
| 5.5 | Reduced motion | 5.5 |
| 5.6 | Hero loading | 5.6 |

Source videos for all 37: see `design-examples.md`.
