"""
TXT 2 SHORTS V5 — PREMIUM CINEMATIC ENGINE
==========================================
Built on V4's True Selenium-Free Pillow Renderer.

NEW IN V5:
  ✦ 55+ Premium Glowing Themes  (Cyber Blue, Neon Cyan, Emerald, Royal Purple,
    Crimson, Gold, Orange Fire, Ice Blue, Holographic, Glassmorphism, Matrix,
    Synthwave, Tron, Aurora, Quantum, Deep Ocean, Cosmic, Luxury Gold, ...)
  ✦ Random Cinematic Transition Engine (15 premium transitions)
  ✦ Dynamic Content Sizing — cards auto-resize to content
  ✦ Breathing Glow Animations — borders & shadows softly pulse
  ✦ Premium Intro + Outro Screens — cinematic, emoji-rich, gradient
  ✦ Video Uniqueness Engine — no two exports look identical

NEW IN V10 (HINDI SUPPORT):
  * Hindi (Devanagari) questions / options / explanations render correctly
    (proper matras + conjuncts via HarfBuzz, Nirmala UI / Mangal font - no more boxes)
  * Intro, outro, badges, footer, "Guess the answer" etc. switch to Hindi automatically
  * Hindi voice: Microsoft Edge Neural (hi-IN Madhur / Swara, online, best quality)
    or an installed Windows SAPI Hindi voice (offline)
  * Language is auto-detected per video (or force English / Hindi in Settings)
  * Emoji / junk symbols in the txt (e.g. "Ex: <hearts>") are removed, not drawn as boxes
  * Correct-answer tick is now a vector check mark (works with every font)

EXTRA REQUIREMENTS FOR HINDI:
  pip install uharfbuzz freetype-py edge-tts

NEW IN V9: text-size option (question / options / explanation), much faster rendering
  (cheaper glow, single-pass ffmpeg for video backgrounds, optional GPU encoder).

V12 FIXES (on top of V11):
  * "WinError 206 - The filename or extension is too long" on videos with many questions
    (e.g. 100 per video): long videos are now built in chunks and joined, so the ffmpeg
    command can never get too long (tested up to 1000 questions per video).
  * Crash "y1 must be greater than or equal to y0" on long questions in tight formats
    (16:9 HD 1280x720, 720x1280, ...): text now shrinks to fit and the layout can never break.

NEW IN V11  (every item below can be switched ON / OFF in the "V11 Pro Features" box):
  * Typewriter question  - the question types itself letter by letter
  * Options slide in one-by-one (A, B, C, D fly in from the right)
  * Animated countdown   - number 10 -> 1 and the ring slowly empties (uses YOUR timer seconds)
  * Multi-format export  - 9:16, 4:5 (Instagram), 1:1, 4:3, 16:9, 16:9 HD, 2:3 in ONE click.
                           Voice is generated only once and shared by all formats.
  * Round logo watermark - upload any image, shown as a small circle at the bottom of the video
  Speed: animations are tiny "sprites" that ffmpeg lays over the normal slide image, so
         the slide is still rendered only once - videos are created almost as fast as before.

NEW: VIDEO BACKGROUNDS (optional)
  Add your own MP4 clips in the "Video Backgrounds" box. When at least one clip
  is added, the static gradient backgrounds are NOT drawn - the clips play
  behind the cards instead (muted, looped to fill the whole video).

REQUIREMENTS:
  pip install pillow pywin32 static-ffmpeg numpy
"""

import sys, os, re, time, wave, math, shutil, tempfile, asyncio, unicodedata
import threading, subprocess, array, random
import concurrent.futures

# ── Optional / guarded imports ─────────────────────────────────────────────────
try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import pythoncom
    HAS_PYTHONCOM = True
except ImportError:
    HAS_PYTHONCOM = False

# Hindi: HarfBuzz (text shaping) + FreeType (glyph rasteriser) + Edge neural TTS
def _try_hindi_imports():
    global hb, freetype, edge_tts, HAS_HB, HAS_EDGE
    try:
        import uharfbuzz as hb
        import freetype
        HAS_HB = True
    except Exception:
        HAS_HB = False
    try:
        import edge_tts
        HAS_EDGE = True
    except Exception:
        HAS_EDGE = False


def _ensure_hindi_deps():
    """Installs the Hindi helper packages automatically (once) if they are missing."""
    import subprocess as _sp, importlib
    _try_hindi_imports()
    need = []
    if not HAS_HB:
        need += ["uharfbuzz", "freetype-py"]
    if not HAS_EDGE:
        need += ["edge-tts"]
    if not need:
        return
    print(f"[SETUP] Installing Hindi support packages: {' '.join(need)} ...")
    try:
        r = _sp.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *need],
                    timeout=600)
        if r.returncode != 0:
            r = _sp.run([sys.executable, "-m", "pip", "install", "--user",
                         "--disable-pip-version-check", *need], timeout=600)
        importlib.invalidate_caches()
    except Exception as e:
        print(f"[SETUP] Automatic install failed: {e}")
    _try_hindi_imports()
    print(f"[SETUP] HarfBuzz: {'OK' if HAS_HB else 'MISSING'} | edge-tts: {'OK' if HAS_EDGE else 'MISSING'}")


HAS_HB = HAS_EDGE = False
_try_hindi_imports()


# ─── Audio Helpers ────────────────────────────────────────────────────────────
CANONICAL_RATE     = 44100
CANONICAL_CHANNELS = 1
CANONICAL_WIDTH    = 2


def generate_ticking_audio(filepath, duration_sec=10.0, sample_rate=CANONICAL_RATE):
    n = int(sample_rate * duration_sec)
    if HAS_NUMPY:
        t    = np.arange(n, dtype=np.float64) / sample_rate
        sf   = t - np.floor(t)
        beat = (np.floor(t).astype(np.int32) % 2 == 0).astype(np.float64)
        freq = 1500.0 * beat + 1100.0 * (1.0 - beat)
        env  = np.exp(-sf * 110.0) * (sf < 0.048)
        tick = (0.80 * np.sin(2.0 * np.pi * freq * t) +
                0.55 * np.sin(       np.pi * freq * t)) * env
        raw   = (np.clip(tick, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
    else:
        buf = array.array('h', [0] * n)
        for i in range(n):
            t_  = i / sample_rate
            sf_ = t_ - int(t_)
            tick_ = 0.0
            if sf_ < 0.048:
                freq_ = 1500.0 if int(t_) % 2 == 0 else 1100.0
                env_  = math.exp(-sf_ * 110.0)
                tick_ = (0.80 * math.sin(2*math.pi*freq_*t_) +
                         0.55 * math.sin(math.pi*freq_*t_)) * env_
            buf[i] = int(max(-1.0, min(1.0, tick_)) * 32767)
        raw = buf.tobytes()
    with wave.open(filepath, 'w') as wf:
        wf.setnchannels(CANONICAL_CHANNELS)
        wf.setsampwidth(CANONICAL_WIDTH)
        wf.setframerate(sample_rate)
        wf.writeframes(raw)


def generate_silent_wav(filepath, duration_sec=1.0, sample_rate=CANONICAL_RATE):
    n = int(sample_rate * duration_sec)
    with wave.open(filepath, 'w') as wf:
        wf.setnchannels(CANONICAL_CHANNELS)
        wf.setsampwidth(CANONICAL_WIDTH)
        wf.setframerate(sample_rate)
        wf.writeframes(b'\x00\x00' * n)


def wav_duration(filepath, minimum=1.0):
    try:
        with wave.open(filepath, 'r') as wf:
            return max(minimum, wf.getnframes() / float(wf.getframerate()))
    except Exception:
        return minimum


def _normalize_wav(src_path, dst_path,
                   out_rate=CANONICAL_RATE,
                   out_channels=CANONICAL_CHANNELS,
                   out_width=CANONICAL_WIDTH):
    try:
        with wave.open(src_path, 'r') as wf:
            in_channels = wf.getnchannels()
            in_width    = wf.getsampwidth()
            in_rate     = wf.getframerate()
            n_frames    = wf.getnframes()
            raw_bytes   = wf.readframes(n_frames)

        total_samples = n_frames * in_channels
        if in_width == 1:
            samples = array.array('b', raw_bytes)
            samples = array.array('h', [s << 8 for s in samples])
        elif in_width == 2:
            samples = array.array('h')
            samples.frombytes(raw_bytes)
        elif in_width == 4:
            samples32 = array.array('i')
            samples32.frombytes(raw_bytes)
            samples = array.array('h', [s >> 16 for s in samples32])
        else:
            samples = array.array('h', [0] * total_samples)

        if in_channels > 1:
            mono = array.array('h', [0] * n_frames)
            for i in range(n_frames):
                s = sum(samples[i*in_channels + c] for c in range(in_channels))
                mono[i] = max(-32768, min(32767, s // in_channels))
            samples = mono

        if in_rate != out_rate:
            ratio      = in_rate / out_rate
            out_frames = int(n_frames / ratio)
            resampled  = array.array('h', [0] * out_frames)
            for i in range(out_frames):
                src_f = i * ratio
                src_i = int(src_f)
                frac  = src_f - src_i
                s0    = samples[min(src_i,     n_frames-1)]
                s1    = samples[min(src_i + 1, n_frames-1)]
                resampled[i] = int(s0 + frac * (s1 - s0))
            samples = resampled

        with wave.open(dst_path, 'w') as wf:
            wf.setnchannels(out_channels)
            wf.setsampwidth(out_width)
            wf.setframerate(out_rate)
            wf.writeframes(samples.tobytes())

    except Exception:
        shutil.copy2(src_path, dst_path)


# ─── Text Helpers ─────────────────────────────────────────────────────────────
def clean_text(text):
    if not text: return ""
    t = re.sub(r'www\.\S+', '', text, flags=re.IGNORECASE)
    t = re.sub(r'@\S+', '', t)
    t = re.sub(r'https?://\S+', '', t)
    t = re.sub(r'pakexampoint[^\n]*', '', t, flags=re.IGNORECASE)
    t = re.sub(r'PowerUp\s+Prelims[^\n]*', '', t, flags=re.IGNORECASE)
    t = re.sub(r'No part of this document[^\n]*', '', t, flags=re.IGNORECASE)
    t = re.sub(r'[ \t]+', ' ', t).strip()
    return t


# ─── Parser ───────────────────────────────────────────────────────────────────
def parse_input_file(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    raw_blocks = re.split(r'(?=\bQ\d+[\.\s\:\)])', content)
    questions  = []

    for block in raw_blocks:
        block = block.strip()
        if not block: continue
        hm = re.match(r'^Q(\d+)[\.\s\:\)]\s*(.*)', block, re.DOTALL)
        if not hm: continue
        q_num = int(hm[1])
        rest  = hm[2].strip()

        em = re.search(r'\n\s*(?:Ex|Explanation|\u0935\u094d\u092f\u093e\u0916\u094d\u092f\u093e)\s*[:\uff1a]\s*(.*)', rest,
                       re.DOTALL | re.IGNORECASE)
        if em:
            q_and_opts  = rest[:em.start()].strip()
            explanation = em.group(1).strip()
        else:
            q_and_opts  = rest
            explanation = ""

        explanation = clean_text(explanation)
        if not re.search(r'\w', explanation):      # only emoji / symbols -> no explanation
            explanation = ""
        lines = [l.strip() for l in q_and_opts.split('\n') if l.strip()]
        lines = [l for l in lines if l not in ['😂','😊','👍','🙏']]

        opts, correct_idx = [], 0
        ans_m    = re.search(r'(?:\bAnsw\s*er|\u0909\u0924\u094d\u0924\u0930)\s*[:\uff1a]\s*\(?([a-dA-D])\)?(?![A-Za-z])', explanation, re.IGNORECASE)
        explicit = ord(ans_m.group(1).lower()) - ord('a') if ans_m else -1

        if len(lines) >= 5:
            possible = lines[-4:]; q_lines = lines[:-4]
            for i, ol in enumerate(possible):
                correct = ('✅' in ol) or (explicit == i)
                clean_o = ol.replace('✅', '').strip()
                clean_o = re.sub(r'^(?:[a-dA-D][\.\)]|[1-4][\.\)])\s*', '',
                                 clean_o).strip()
                opts.append(clean_text(clean_o))
                if correct: correct_idx = i
        else:
            q_lines = lines
            opts    = ["Option A", "Option B", "Option C", "Option D"]

        q_text = clean_text("\n".join(q_lines).strip())
        first  = q_lines[0] if q_lines else f"Question {q_num}"
        title  = first[:50] + "..." if len(first) > 50 else first

        questions.append({
            "number": q_num, "title": title,
            "questionText": q_text, "options": opts,
            "correctIndex": correct_idx, "explanation": explanation
        })

    return questions


# ─── 55+ PREMIUM GLOWING THEMES ───────────────────────────────────────────────
# Each theme has:
#   bg/bg2: gradient background colors
#   card: card fill color
#   border: crisp border color
#   glow: glow halo color (usually = border or accent)
#   title: primary text color
#   badge_bg/badge_fg: badge pill colors
#   accent: highlight/secondary color
#   correct: correct-answer highlight color
#   gradient: 'vertical'|'radial'|'diagonal'|'solid'
#   glow_intensity: 0.5–1.0
#   particle: dot-grid color
THEMES = [
    # ── CYBER / TECH ──────────────────────────────────────────────────────────
    {   # 0 Cyber Blue
        "name":"Cyber Blue",
        "bg":"#06101e","bg2":"#091426","card":"#0d1e30",
        "border":"#00D8FF","glow":"#00D8FF","title":"#00EEFF",
        "badge_bg":"#00D8FF","badge_fg":"#06101e",
        "accent":"#FFD700","correct":"#00FF88",
        "gradient":"diagonal","glow_intensity":0.90,"particle":"#00D8FF",
    },
    {   # 1 Neon Cyan
        "name":"Neon Cyan",
        "bg":"#040c10","bg2":"#071318","card":"#0a1a20",
        "border":"#00FFF0","glow":"#00FFF0","title":"#00FFF0",
        "badge_bg":"#00FFF0","badge_fg":"#040c10",
        "accent":"#FF6B35","correct":"#00FF88",
        "gradient":"radial","glow_intensity":1.0,"particle":"#00E5D4",
    },
    {   # 2 Matrix
        "name":"Matrix",
        "bg":"#010d05","bg2":"#011a08","card":"#031a09",
        "border":"#00FF41","glow":"#00FF41","title":"#00FF41",
        "badge_bg":"#00FF41","badge_fg":"#010d05",
        "accent":"#39FF14","correct":"#00FF41",
        "gradient":"vertical","glow_intensity":0.95,"particle":"#00FF41",
    },
    {   # 3 Tron Blue
        "name":"Tron",
        "bg":"#03080f","bg2":"#040d18","card":"#081220",
        "border":"#3BFCFD","glow":"#3BFCFD","title":"#7FFFFF",
        "badge_bg":"#3BFCFD","badge_fg":"#03080f",
        "accent":"#FF8C00","correct":"#00FF88",
        "gradient":"diagonal","glow_intensity":0.85,"particle":"#3BFCFD",
    },
    {   # 4 Quantum
        "name":"Quantum",
        "bg":"#050915","bg2":"#080e20","card":"#0c1630",
        "border":"#4488FF","glow":"#4488FF","title":"#88BBFF",
        "badge_bg":"#4488FF","badge_fg":"#050915",
        "accent":"#FF44AA","correct":"#44FF88",
        "gradient":"radial","glow_intensity":0.88,"particle":"#4488FF",
    },
    {   # 5 Electric Purple
        "name":"Electric Purple",
        "bg":"#0b0518","bg2":"#120825","card":"#180a30",
        "border":"#BF5FFF","glow":"#BF5FFF","title":"#D580FF",
        "badge_bg":"#BF5FFF","badge_fg":"#0b0518",
        "accent":"#00D8FF","correct":"#00FF88",
        "gradient":"vertical","glow_intensity":0.92,"particle":"#9040CC",
    },
    {   # 6 Hacker Green
        "name":"Hacker",
        "bg":"#010a04","bg2":"#010e06","card":"#021508",
        "border":"#39FF14","glow":"#39FF14","title":"#7FFF00",
        "badge_bg":"#39FF14","badge_fg":"#010a04",
        "accent":"#00FFCC","correct":"#39FF14",
        "gradient":"solid","glow_intensity":0.95,"particle":"#39FF14",
    },
    {   # 7 Synthwave
        "name":"Synthwave",
        "bg":"#120024","bg2":"#200040","card":"#1e003a",
        "border":"#FF2D78","glow":"#FF2D78","title":"#FF88CC",
        "badge_bg":"#FF2D78","badge_fg":"#120024",
        "accent":"#00F0FF","correct":"#00FF88",
        "gradient":"radial","glow_intensity":0.93,"particle":"#CC0066",
    },
    # ── WARM / FIRE ───────────────────────────────────────────────────────────
    {   # 8 Orange Fire
        "name":"Orange Fire",
        "bg":"#120500","bg2":"#1f0900","card":"#1e0a00",
        "border":"#FF6B00","glow":"#FF6B00","title":"#FF9A3C",
        "badge_bg":"#FF6B00","badge_fg":"#120500",
        "accent":"#FFD700","correct":"#00FF88",
        "gradient":"vertical","glow_intensity":0.90,"particle":"#FF4400",
    },
    {   # 9 Crimson
        "name":"Crimson",
        "bg":"#140006","bg2":"#200009","card":"#220008",
        "border":"#FF1744","glow":"#FF1744","title":"#FF6680",
        "badge_bg":"#FF1744","badge_fg":"#140006",
        "accent":"#FFD700","correct":"#00FF88",
        "gradient":"diagonal","glow_intensity":0.88,"particle":"#CC0022",
    },
    {   # 10 Luxury Gold
        "name":"Luxury Gold",
        "bg":"#0d0900","bg2":"#180e00","card":"#1a1000",
        "border":"#FFD700","glow":"#FFD700","title":"#FFE566",
        "badge_bg":"#FFD700","badge_fg":"#0d0900",
        "accent":"#FF8C00","correct":"#00FF88",
        "gradient":"vertical","glow_intensity":0.95,"particle":"#CC9900",
    },
    {   # 11 Magma
        "name":"Magma",
        "bg":"#0f0300","bg2":"#1a0500","card":"#1c0600",
        "border":"#FF3D00","glow":"#FF3D00","title":"#FF6333",
        "badge_bg":"#FF3D00","badge_fg":"#0f0300",
        "accent":"#FFB300","correct":"#00FF88",
        "gradient":"radial","glow_intensity":0.92,"particle":"#CC2800",
    },
    {   # 12 Solar
        "name":"Solar",
        "bg":"#100a00","bg2":"#1c1100","card":"#1e1200",
        "border":"#FFC107","glow":"#FFC107","title":"#FFD740",
        "badge_bg":"#FFC107","badge_fg":"#100a00",
        "accent":"#FF5722","correct":"#00FF88",
        "gradient":"diagonal","glow_intensity":0.85,"particle":"#FFA000",
    },
    {   # 13 Neon Pink
        "name":"Neon Pink",
        "bg":"#14000a","bg2":"#200012","card":"#22001a",
        "border":"#FF0080","glow":"#FF0080","title":"#FF66B2",
        "badge_bg":"#FF0080","badge_fg":"#14000a",
        "accent":"#00F0FF","correct":"#00FF88",
        "gradient":"radial","glow_intensity":0.93,"particle":"#CC0066",
    },
    {   # 14 Rose Gold
        "name":"Rose Gold",
        "bg":"#130008","bg2":"#1e000e","card":"#200010",
        "border":"#FF6B9D","glow":"#FF6B9D","title":"#FFB3D1",
        "badge_bg":"#FF6B9D","badge_fg":"#130008",
        "accent":"#FFD700","correct":"#00FF88",
        "gradient":"vertical","glow_intensity":0.80,"particle":"#CC4477",
    },
    # ── COOL / ICE ────────────────────────────────────────────────────────────
    {   # 15 Ice Blue
        "name":"Ice Blue",
        "bg":"#050d18","bg2":"#081525","card":"#0c1c30",
        "border":"#7EC8E3","glow":"#7EC8E3","title":"#B3E0F0",
        "badge_bg":"#7EC8E3","badge_fg":"#050d18",
        "accent":"#E0F7FF","correct":"#00FF88",
        "gradient":"vertical","glow_intensity":0.75,"particle":"#5AABC4",
    },
    {   # 16 Deep Ocean
        "name":"Deep Ocean",
        "bg":"#020c1a","bg2":"#041528","card":"#061e35",
        "border":"#0088CC","glow":"#00AAFF","title":"#44CCFF",
        "badge_bg":"#0088CC","badge_fg":"#020c1a",
        "accent":"#00F0C8","correct":"#00FF88",
        "gradient":"radial","glow_intensity":0.87,"particle":"#005588",
    },
    {   # 17 Sapphire
        "name":"Sapphire",
        "bg":"#040b1c","bg2":"#061428","card":"#091b35",
        "border":"#1E90FF","glow":"#1E90FF","title":"#6AB4FF",
        "badge_bg":"#1E90FF","badge_fg":"#040b1c",
        "accent":"#00F0FF","correct":"#00FF88",
        "gradient":"diagonal","glow_intensity":0.90,"particle":"#1166CC",
    },
    {   # 18 Arctic
        "name":"Arctic",
        "bg":"#06101c","bg2":"#0a1828","card":"#0f2035",
        "border":"#A8D8EA","glow":"#A8D8EA","title":"#D4EEF7",
        "badge_bg":"#A8D8EA","badge_fg":"#06101c",
        "accent":"#FFD700","correct":"#00FF88",
        "gradient":"vertical","glow_intensity":0.70,"particle":"#80B8CC",
    },
    {   # 19 Storm
        "name":"Storm",
        "bg":"#080c14","bg2":"#0d1220","card":"#121828",
        "border":"#5B8CFF","glow":"#5B8CFF","title":"#8CB0FF",
        "badge_bg":"#5B8CFF","badge_fg":"#080c14",
        "accent":"#FF6B35","correct":"#00FF88",
        "gradient":"radial","glow_intensity":0.85,"particle":"#3355CC",
    },
    # ── NATURE / ORGANIC ──────────────────────────────────────────────────────
    {   # 20 Emerald
        "name":"Emerald",
        "bg":"#020e07","bg2":"#031608","card":"#051c0c",
        "border":"#00E676","glow":"#00E676","title":"#66FF99",
        "badge_bg":"#00E676","badge_fg":"#020e07",
        "accent":"#FFEB3B","correct":"#00E676",
        "gradient":"vertical","glow_intensity":0.90,"particle":"#00BB55",
    },
    {   # 21 Forest
        "name":"Forest",
        "bg":"#041208","bg2":"#071c0c","card":"#092010",
        "border":"#4CAF50","glow":"#4CAF50","title":"#A5D6A7",
        "badge_bg":"#4CAF50","badge_fg":"#041208",
        "accent":"#CDDC39","correct":"#4CAF50",
        "gradient":"diagonal","glow_intensity":0.80,"particle":"#2E7D32",
    },
    {   # 22 Bioluminescent
        "name":"Bioluminescent",
        "bg":"#020a08","bg2":"#031410","card":"#051c15",
        "border":"#00FFCC","glow":"#00FFCC","title":"#66FFEE",
        "badge_bg":"#00FFCC","badge_fg":"#020a08",
        "accent":"#80FF00","correct":"#00FFCC",
        "gradient":"radial","glow_intensity":1.0,"particle":"#00CC99",
    },
    {   # 23 Jade
        "name":"Jade",
        "bg":"#031410","bg2":"#051e18","card":"#072620",
        "border":"#00BFA5","glow":"#00BFA5","title":"#66D9C8",
        "badge_bg":"#00BFA5","badge_fg":"#031410",
        "accent":"#FFCA28","correct":"#00BFA5",
        "gradient":"vertical","glow_intensity":0.82,"particle":"#008875",
    },
    {   # 24 Mint
        "name":"Mint",
        "bg":"#031412","bg2":"#061e1a","card":"#082422",
        "border":"#00E5CC","glow":"#00E5CC","title":"#88FFF0",
        "badge_bg":"#00E5CC","badge_fg":"#031412",
        "accent":"#FF8A80","correct":"#00E5CC",
        "gradient":"diagonal","glow_intensity":0.78,"particle":"#00B8A0",
    },
    # ── PREMIUM / LUXURY ──────────────────────────────────────────────────────
    {   # 25 Royal Purple
        "name":"Royal Purple",
        "bg":"#0d0520","bg2":"#170830","card":"#200a40",
        "border":"#9C27B0","glow":"#CE93D8","title":"#E1BEE7",
        "badge_bg":"#9C27B0","badge_fg":"#0d0520",
        "accent":"#FFD700","correct":"#00FF88",
        "gradient":"radial","glow_intensity":0.88,"particle":"#6A1B9A",
    },
    {   # 26 Holographic
        "name":"Holographic",
        "bg":"#08080f","bg2":"#12101a","card":"#1a1825",
        "border":"#CC88FF","glow":"#FF88CC","title":"#FFBBEE",
        "badge_bg":"#CC88FF","badge_fg":"#08080f",
        "accent":"#88FFFF","correct":"#88FF88",
        "gradient":"diagonal","glow_intensity":0.95,"particle":"#9944CC",
    },
    {   # 27 Glassmorphism
        "name":"Glassmorphism",
        "bg":"#0a1628","bg2":"#112235","card":"#162a40",
        "border":"#88CCFF","glow":"#AADDFF","title":"#CCEEFF",
        "badge_bg":"#3388CC","badge_fg":"#0a1628",
        "accent":"#FFD700","correct":"#00FF88",
        "gradient":"diagonal","glow_intensity":0.72,"particle":"#4488AA",
    },
    {   # 28 Velvet
        "name":"Velvet",
        "bg":"#100018","bg2":"#1a0028","card":"#240035",
        "border":"#AA44FF","glow":"#CC66FF","title":"#EEB0FF",
        "badge_bg":"#AA44FF","badge_fg":"#100018",
        "accent":"#FF88CC","correct":"#00FF88",
        "gradient":"vertical","glow_intensity":0.85,"particle":"#7722BB",
    },
    {   # 29 Diamond
        "name":"Diamond",
        "bg":"#07101c","bg2":"#0d1a28","card":"#122230",
        "border":"#B0E0FF","glow":"#D0EEFF","title":"#E8F4FF",
        "badge_bg":"#7BBCDD","badge_fg":"#07101c",
        "accent":"#FFD700","correct":"#00FF88",
        "gradient":"radial","glow_intensity":0.80,"particle":"#4488AA",
    },
    # ── ARTISTIC / SPECIAL ────────────────────────────────────────────────────
    {   # 30 Aurora
        "name":"Aurora",
        "bg":"#030e10","bg2":"#051820","card":"#082028",
        "border":"#00FFAA","glow":"#00FFAA","title":"#88FFD4",
        "badge_bg":"#00FFAA","badge_fg":"#030e10",
        "accent":"#AA44FF","correct":"#00FFAA",
        "gradient":"diagonal","glow_intensity":0.93,"particle":"#00CC88",
    },
    {   # 31 Cosmic
        "name":"Cosmic",
        "bg":"#060410","bg2":"#0c0820","card":"#120c30",
        "border":"#8844FF","glow":"#AA66FF","title":"#CC99FF",
        "badge_bg":"#6622CC","badge_fg":"#060410",
        "accent":"#FF44AA","correct":"#00FF88",
        "gradient":"radial","glow_intensity":0.90,"particle":"#5511AA",
    },
    {   # 32 Galaxy
        "name":"Galaxy",
        "bg":"#050308","bg2":"#0c0715","card":"#130b20",
        "border":"#7755EE","glow":"#9977FF","title":"#BBAAFF",
        "badge_bg":"#5533BB","badge_fg":"#050308",
        "accent":"#FF66CC","correct":"#00FF88",
        "gradient":"radial","glow_intensity":0.88,"particle":"#4422AA",
    },
    {   # 33 Neon Tokyo
        "name":"Neon Tokyo",
        "bg":"#0a0010","bg2":"#14001a","card":"#1a0022",
        "border":"#FF00FF","glow":"#FF44FF","title":"#FF99FF",
        "badge_bg":"#CC00CC","badge_fg":"#0a0010",
        "accent":"#00FFFF","correct":"#00FF88",
        "gradient":"vertical","glow_intensity":0.95,"particle":"#AA00AA",
    },
    {   # 34 Sunrise
        "name":"Sunrise",
        "bg":"#0e0800","bg2":"#200e00","card":"#1e1200",
        "border":"#FF7043","glow":"#FF7043","title":"#FFAB91",
        "badge_bg":"#FF7043","badge_fg":"#0e0800",
        "accent":"#FFC107","correct":"#00FF88",
        "gradient":"vertical","glow_intensity":0.82,"particle":"#CC4400",
    },
    {   # 35 Indigo Night
        "name":"Indigo Night",
        "bg":"#080a20","bg2":"#0d0f30","card":"#121540",
        "border":"#5C6BC0","glow":"#7986CB","title":"#9FA8DA",
        "badge_bg":"#3F51B5","badge_fg":"#080a20",
        "accent":"#FF4081","correct":"#00FF88",
        "gradient":"diagonal","glow_intensity":0.82,"particle":"#283593",
    },
    {   # 36 Cyber Green V2
        "name":"Cyber Green",
        "bg":"#040d06","bg2":"#071508","card":"#0a1e0c",
        "border":"#00FF66","glow":"#00FF66","title":"#66FFA0",
        "badge_bg":"#00CC44","badge_fg":"#040d06",
        "accent":"#FFFF00","correct":"#00FF66",
        "gradient":"diagonal","glow_intensity":0.92,"particle":"#00BB33",
    },
    {   # 37 Blood Moon
        "name":"Blood Moon",
        "bg":"#150004","bg2":"#220006","card":"#2a0008",
        "border":"#CC0000","glow":"#FF2222","title":"#FF8888",
        "badge_bg":"#990000","badge_fg":"#150004",
        "accent":"#FF8800","correct":"#FF4444",
        "gradient":"radial","glow_intensity":0.90,"particle":"#880000",
    },
    {   # 38 Cyber Orange
        "name":"Cyber Orange",
        "bg":"#0f0600","bg2":"#190a00","card":"#1e0d00",
        "border":"#FF8C00","glow":"#FF8C00","title":"#FFBB55",
        "badge_bg":"#E65C00","badge_fg":"#0f0600",
        "accent":"#00D4FF","correct":"#00FF88",
        "gradient":"vertical","glow_intensity":0.88,"particle":"#CC5500",
    },
    {   # 39 Deep Violet
        "name":"Deep Violet",
        "bg":"#0c0520","bg2":"#160830","card":"#1e0c40",
        "border":"#7B1FA2","glow":"#AB47BC","title":"#CE93D8",
        "badge_bg":"#6A1B9A","badge_fg":"#0c0520",
        "accent":"#FF80AB","correct":"#00FF88",
        "gradient":"radial","glow_intensity":0.85,"particle":"#4A0072",
    },
    {   # 40 Electric Lime
        "name":"Electric Lime",
        "bg":"#080d00","bg2":"#0e1600","card":"#121c00",
        "border":"#AAFF00","glow":"#CCFF33","title":"#DDFF77",
        "badge_bg":"#88CC00","badge_fg":"#080d00",
        "accent":"#FF4400","correct":"#AAFF00",
        "gradient":"diagonal","glow_intensity":0.90,"particle":"#77AA00",
    },
    {   # 41 Ocean Glow
        "name":"Ocean Glow",
        "bg":"#030c18","bg2":"#051525","card":"#081e35",
        "border":"#00BCD4","glow":"#00E5FF","title":"#80DEEA",
        "badge_bg":"#0097A7","badge_fg":"#030c18",
        "accent":"#FF6D00","correct":"#00FF88",
        "gradient":"vertical","glow_intensity":0.87,"particle":"#00688B",
    },
    {   # 42 Raspberry
        "name":"Raspberry",
        "bg":"#160008","bg2":"#22000e","card":"#2a0014",
        "border":"#E91E63","glow":"#F48FB1","title":"#FCE4EC",
        "badge_bg":"#C2185B","badge_fg":"#160008",
        "accent":"#FFD740","correct":"#00FF88",
        "gradient":"diagonal","glow_intensity":0.87,"particle":"#880033",
    },
    {   # 43 Cyber Amber
        "name":"Cyber Amber",
        "bg":"#0f0900","bg2":"#1a1000","card":"#1e1500",
        "border":"#FFAB00","glow":"#FFAB00","title":"#FFD54F",
        "badge_bg":"#FF8F00","badge_fg":"#0f0900",
        "accent":"#00E5FF","correct":"#00FF88",
        "gradient":"vertical","glow_intensity":0.88,"particle":"#CC8800",
    },
    {   # 44 Plasma
        "name":"Plasma",
        "bg":"#0a0518","bg2":"#140a28","card":"#1a1035",
        "border":"#FF44BB","glow":"#FF44BB","title":"#FF99DD",
        "badge_bg":"#CC1188","badge_fg":"#0a0518",
        "accent":"#44FFDD","correct":"#00FF88",
        "gradient":"radial","glow_intensity":0.93,"particle":"#AA0077",
    },
    {   # 45 Arctic Blue
        "name":"Arctic Blue",
        "bg":"#050e18","bg2":"#081520","card":"#0c1c2c",
        "border":"#64B5F6","glow":"#90CAF9","title":"#BBDEFB",
        "badge_bg":"#1976D2","badge_fg":"#050e18",
        "accent":"#FF8A65","correct":"#00FF88",
        "gradient":"vertical","glow_intensity":0.78,"particle":"#1565C0",
    },
    {   # 46 Phantom
        "name":"Phantom",
        "bg":"#060610","bg2":"#0a0a18","card":"#0f0f22",
        "border":"#9999FF","glow":"#BBBBFF","title":"#DDDDFF",
        "badge_bg":"#5555CC","badge_fg":"#060610",
        "accent":"#FF8844","correct":"#00FF88",
        "gradient":"radial","glow_intensity":0.82,"particle":"#4444AA",
    },
    {   # 47 Inferno
        "name":"Inferno",
        "bg":"#100200","bg2":"#1e0400","card":"#280600",
        "border":"#FF4500","glow":"#FF6600","title":"#FF9966",
        "badge_bg":"#CC2200","badge_fg":"#100200",
        "accent":"#FFD700","correct":"#FF4500",
        "gradient":"radial","glow_intensity":0.95,"particle":"#AA1100",
    },
    {   # 48 Midnight
        "name":"Midnight",
        "bg":"#050510","bg2":"#080818","card":"#0c0c20",
        "border":"#4455AA","glow":"#6677CC","title":"#99AADD",
        "badge_bg":"#334488","badge_fg":"#050510",
        "accent":"#FF9933","correct":"#00FF88",
        "gradient":"solid","glow_intensity":0.70,"particle":"#223366",
    },
    {   # 49 Sakura
        "name":"Sakura",
        "bg":"#140010","bg2":"#200018","card":"#280020",
        "border":"#FF80AB","glow":"#FFAAC8","title":"#FFDDE8",
        "badge_bg":"#E91E63","badge_fg":"#140010",
        "accent":"#FFD700","correct":"#00FF88",
        "gradient":"diagonal","glow_intensity":0.80,"particle":"#CC3377",
    },
    {   # 50 Neon Violet
        "name":"Neon Violet",
        "bg":"#0d0020","bg2":"#160030","card":"#1e0040",
        "border":"#CC00FF","glow":"#DD44FF","title":"#EE88FF",
        "badge_bg":"#AA00CC","badge_fg":"#0d0020",
        "accent":"#00FFAA","correct":"#00FF88",
        "gradient":"vertical","glow_intensity":0.95,"particle":"#8800AA",
    },
    {   # 51 Copper
        "name":"Copper",
        "bg":"#0e0600","bg2":"#180a00","card":"#1e0e00",
        "border":"#B87333","glow":"#D4884F","title":"#FFCC99",
        "badge_bg":"#8B5A2B","badge_fg":"#0e0600",
        "accent":"#FFD700","correct":"#00FF88",
        "gradient":"vertical","glow_intensity":0.78,"particle":"#7A4520",
    },
    {   # 52 Chrome
        "name":"Chrome",
        "bg":"#080c12","bg2":"#0e1420","card":"#141c28",
        "border":"#AABBCC","glow":"#CCDDEE","title":"#E8EEF4",
        "badge_bg":"#778899","badge_fg":"#080c12",
        "accent":"#FF6B35","correct":"#00FF88",
        "gradient":"diagonal","glow_intensity":0.75,"particle":"#5577AA",
    },
    {   # 53 Vaporwave
        "name":"Vaporwave",
        "bg":"#0f0020","bg2":"#180030","card":"#220040",
        "border":"#FF71CE","glow":"#FF71CE","title":"#FFB3E8",
        "badge_bg":"#B455F0","badge_fg":"#0f0020",
        "accent":"#01CDFE","correct":"#05FFA1",
        "gradient":"radial","glow_intensity":0.93,"particle":"#9900CC",
    },
    {   # 54 Biotech
        "name":"Biotech",
        "bg":"#020e08","bg2":"#031610","card":"#052018",
        "border":"#00FFB2","glow":"#00FFB2","title":"#66FFD4",
        "badge_bg":"#00CC88","badge_fg":"#020e08",
        "accent":"#BBFF00","correct":"#00FFB2",
        "gradient":"vertical","glow_intensity":0.93,"particle":"#009966",
    },
]


# ─── Color Utilities ─────────────────────────────────────────────────────────
def _rgb(hex_color):
    h = hex_color.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _lighten(rgb, amount=30):
    return tuple(min(255, c + amount) for c in rgb)


def _darken(rgb, amount=20):
    return tuple(max(0, c - amount) for c in rgb)


def _alpha_blend(base_rgb, overlay_rgb, alpha):
    return tuple(int(b*(1-alpha) + o*alpha) for b, o in zip(base_rgb, overlay_rgb))


def _hex_alpha(hex_color, alpha_0_255):
    """Return RGBA tuple from hex color + alpha int 0-255."""
    r, g, b = _rgb(hex_color)
    return (r, g, b, alpha_0_255)


# ─── Font Loading ─────────────────────────────────────────────────────────────
_FONT_CACHE = {}
_TL = threading.local()      # per-thread render state (auto-fit shrink, video-bg matte)
TEXT_SCALE      = 1.25       # user text-size multiplier (set from the UI)
USE_GPU_ENCODER = False       # try a hardware H.264 encoder first (set from the UI)

# ── V11 switches (copied from the UI at the start of every run) ───────────────
ANIM_CFG = {'typewriter': True, 'options': True, 'countdown': True}
LOGO_CFG = {'enabled': False, 'path': '', 'position': 'bottom-right'}
_RENDER_SEM = threading.Semaphore(2)   # caps heavy per-format work when several formats are exported
_ANIM_STEP_FAST = 0.04                 # typing / slide-in animation step (25 fps)
_ANIM_STEP_RING = 0.08                 # countdown ring + number step (12.5 fps - plenty for a slow ring)

# key, label, width, height   (all even numbers - required by the video encoder)
OUTPUT_FORMATS = [
    ("9x16",    "9:16  Shorts / Reels / TikTok  (1080x1920)",      1080, 1920),
    ("4x5",     "4:5   Instagram Feed portrait  (1080x1350)",      1080, 1350),
    ("1x1",     "1:1   Instagram / Facebook square  (1080x1080)",  1080, 1080),
    ("4x3",     "4:3   Facebook / classic  (1440x1080)",           1440, 1080),
    ("16x9",    "16:9  YouTube landscape  (1920x1080)",            1920, 1080),
    ("16x9_hd", "16:9  YouTube HD  (1280x720)",                    1280, 720),
    ("2x3",     "2:3   Pinterest  (1000x1500)",                    1000, 1500),
]


def _eff_scale():
    return TEXT_SCALE * getattr(_TL, 'shrink', 1.0)


def _sz(base):
    """Scale a base font size by the user's text-size setting."""
    return max(10, int(round(base * _eff_scale())))


def _sz_half(base):
    """Scale by HALF the change (used for the small letter badges A/B/C/D)."""
    return max(10, int(round(base * (1.0 + (_eff_scale() - 1.0) * 0.5))))


# ─── Language handling (English / Hindi) ──────────────────────────────────────
_DEVA_RE  = re.compile(r'[\u0900-\u097F]')
_LATIN_RE = re.compile(r'[A-Za-z]')
FORCE_LANG = 'auto'          # 'auto' | 'en' | 'hi'   (set from the UI)
FFMPEG_EXE = 'ffmpeg'        # set at run time
_LOG_FN    = print           # set at run time
TTS_CFG = {
    'engine': 'auto',                       # auto | edge | sapi
    'hi_edge_voice': 'hi-IN-MadhurNeural',
    'en_edge_voice': 'en-IN-PrabhatNeural',
    'speed': 1.0,
    'sapi_hi_idx': -1,                      # index of an installed SAPI Hindi voice (or -1)
}
_WARNED = set()


def _warn_once(key, msg):
    if key in _WARNED:
        return
    _WARNED.add(key)
    try:
        _LOG_FN(msg)
    except Exception:
        print(msg)


def detect_lang(texts):
    """'hi' when a meaningful share of the letters is Devanagari, else 'en'."""
    deva = latin = 0
    for t in texts:
        deva  += len(_DEVA_RE.findall(t))
        latin += len(_LATIN_RE.findall(t))
    if deva == 0:
        return 'en'
    return 'hi' if deva >= 0.15 * (deva + latin) else 'en'


def resolve_lang(questions):
    if FORCE_LANG in ('en', 'hi'):
        return FORCE_LANG
    texts = []
    for q in questions:
        texts.append(q.get('questionText', ''))
        texts.extend(q.get('options', []))
    return detect_lang(texts)


# Every on-screen / spoken label.  English strings are exactly the V9 ones.
_STR = {
    'en': {
        'badge_entrance': "\U0001f4dd QUIZ QUESTION",
        'badge_timer':    "\u23f1\ufe0f THINK FAST!",
        'badge_answer':   "\u2705 ANSWER REVEAL",
        'badge_expl':     "\U0001f4a1 EXPLANATION",
        'badge_end':      "\U0001f3c6 QUIZ COMPLETE \U0001f3c6",
        'hook_badges': ["\u26a1 QUIZ TIME \u26a1", "\U0001f3af BRAIN CHALLENGE \U0001f3af",
                        "\U0001f525 IQ TEST \U0001f525", "\U0001f9e0 THINK FAST \u23f1\ufe0f",
                        "\u2b50 CHALLENGE YOURSELF \u2b50"],
        'hook_l1':        "\U0001f3af IQ Test \u2014 Are You Smarter Than 90%?",
        'hook_l2_multi':  "\U0001f525 Can You Get All {n} Questions Right? \U0001f525",
        'hook_l2_single': "\U0001f92f This Question Trips Everyone Up! \U0001f92f",
        'hook_l3':        "\u23f1\ufe0f Guess in {s} Seconds!",
        'hook_cta':       "\U0001f44c Like \u2022 \u2197\ufe0f Share \u2022 \U0001f514 Subscribe",
        'footer':         "* LIKE, SHARE AND SUBSCRIBE *",
        'guess':          "GUESS THE ANSWER!",
        'end_l1':         "FOLLOW FOR DAILY QUIZ!",
        'end_l2':         "Every day new questions!",
        'end_actions':    ["\U0001f44d Like", "\u2197\ufe0f Share", "\U0001f514 Subscribe", "\u2764\ufe0f Follow"],
        'end_sub':        "\U0001f514 Turn on notifications for more quizzes!",
        'speak_hook':     "Welcome! Test your knowledge with this quiz!",
        'speak_answer':   "The correct answer is Option {L}: {text}.",
        'speak_end':      "Follow for daily quizzes. Like, share and subscribe!",
        'letters_spoken': ['A', 'B', 'C', 'D'],
    },
    'hi': {
        'badge_entrance': "\u0915\u094d\u0935\u093f\u091c\u093c \u092a\u094d\u0930\u0936\u094d\u0928",
        'badge_timer':    "\u091c\u0932\u094d\u0926\u0940 \u0938\u094b\u091a\u093f\u090f!",
        'badge_answer':   "\u0938\u0939\u0940 \u0909\u0924\u094d\u0924\u0930",
        'badge_expl':     "\u0935\u094d\u092f\u093e\u0916\u094d\u092f\u093e",
        'badge_end':      "\u0915\u094d\u0935\u093f\u091c\u093c \u092a\u0942\u0930\u093e \u0939\u0941\u0906",
        'hook_badges': ["\u0915\u094d\u0935\u093f\u091c\u093c \u091f\u093e\u0907\u092e",
                        "\u0926\u093f\u092e\u093e\u0917\u0940 \u091a\u0941\u0928\u094c\u0924\u0940",
                        "\u0906\u0908 \u0915\u094d\u092f\u0942 \u091f\u0947\u0938\u094d\u091f",
                        "\u0924\u0947\u091c\u093c \u0938\u094b\u091a\u093f\u090f",
                        "\u0916\u0941\u0926 \u0915\u094b \u092a\u0930\u0916\u093f\u090f"],
        'hook_l1':        "\u0906\u0908 \u0915\u094d\u092f\u0942 \u091f\u0947\u0938\u094d\u091f \u2014 \u0915\u094d\u092f\u093e \u0906\u092a 90% \u0932\u094b\u0917\u094b\u0902 \u0938\u0947 \u091c\u093c\u094d\u092f\u093e\u0926\u093e \u0938\u092e\u091d\u0926\u093e\u0930 \u0939\u0948\u0902?",
        'hook_l2_multi':  "\u0915\u094d\u092f\u093e \u0906\u092a \u0938\u092d\u0940 {n} \u092a\u094d\u0930\u0936\u094d\u0928 \u0938\u0939\u0940 \u0915\u0930 \u0938\u0915\u0924\u0947 \u0939\u0948\u0902?",
        'hook_l2_single': "\u092f\u0939 \u0938\u0935\u093e\u0932 \u0938\u092c\u0915\u094b \u0909\u0932\u091d\u093e \u0926\u0947\u0924\u093e \u0939\u0948!",
        'hook_l3':        "{s} \u0938\u0947\u0915\u0902\u0921 \u092e\u0947\u0902 \u0909\u0924\u094d\u0924\u0930 \u0926\u0940\u091c\u093f\u090f!",
        'hook_cta':       "\u0932\u093e\u0907\u0915  \u2022  \u0936\u0947\u092f\u0930  \u2022  \u0938\u092c\u094d\u0938\u0915\u094d\u0930\u093e\u0907\u092c",
        'footer':         "* \u0932\u093e\u0907\u0915, \u0936\u0947\u092f\u0930 \u0914\u0930 \u0938\u092c\u094d\u0938\u0915\u094d\u0930\u093e\u0907\u092c \u0915\u0930\u0947\u0902 *",
        'guess':          "\u0909\u0924\u094d\u0924\u0930 \u092c\u0924\u093e\u0907\u090f!",
        'end_l1':         "\u0930\u094b\u091c\u093c\u093e\u0928\u093e \u0915\u094d\u0935\u093f\u091c\u093c \u0915\u0947 \u0932\u093f\u090f \u092b\u0949\u0932\u094b \u0915\u0930\u0947\u0902!",
        'end_l2':         "\u0939\u0930 \u0926\u093f\u0928 \u0928\u090f \u092a\u094d\u0930\u0936\u094d\u0928!",
        'end_actions':    ["\u0932\u093e\u0907\u0915", "\u0936\u0947\u092f\u0930", "\u0938\u092c\u094d\u0938\u0915\u094d\u0930\u093e\u0907\u092c", "\u092b\u0949\u0932\u094b"],
        'end_sub':        "\u0914\u0930 \u0915\u094d\u0935\u093f\u091c\u093c \u0915\u0947 \u0932\u093f\u090f \u0928\u094b\u091f\u093f\u092b\u093f\u0915\u0947\u0936\u0928 \u091a\u093e\u0932\u0942 \u0915\u0930\u0947\u0902!",
        'speak_hook':     "\u0938\u094d\u0935\u093e\u0917\u0924 \u0939\u0948! \u0907\u0938 \u0915\u094d\u0935\u093f\u091c\u093c \u092e\u0947\u0902 \u0905\u092a\u0928\u093e \u091c\u094d\u091e\u093e\u0928 \u092a\u0930\u0916\u093f\u090f!",
        'speak_answer':   "\u0938\u0939\u0940 \u0909\u0924\u094d\u0924\u0930 \u0935\u093f\u0915\u0932\u094d\u092a {L} \u0939\u0948: {text}",
        'speak_end':      "\u0930\u094b\u091c\u093c\u093e\u0928\u093e \u0915\u094d\u0935\u093f\u091c\u093c \u0915\u0947 \u0932\u093f\u090f \u092b\u0949\u0932\u094b \u0915\u0940\u091c\u093f\u090f\u0964 \u0932\u093e\u0907\u0915, \u0936\u0947\u092f\u0930 \u0914\u0930 \u0938\u092c\u094d\u0938\u0915\u094d\u0930\u093e\u0907\u092c \u0915\u0930\u0928\u093e \u0928 \u092d\u0942\u0932\u0947\u0902!",
        'letters_spoken': ["\u090f", "\u092c\u0940", "\u0938\u0940", "\u0921\u0940"],
    },
}


def _t(key):
    """Label for the language of the slide currently being rendered."""
    return _STR[getattr(_TL, 'lang', 'en')][key]


# ─── Text clean-up for Hindi (emoji / unsupported symbols never become boxes) ─
_EMOJI_RE = re.compile('[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u20E3'
                       '\u2300-\u23FF\U000E0000-\U000E007F]')
_HI_REPL = {'\u2756': '\u2022', '\u2192': '->', '\u279c': '->', '\u21d2': '=>',
            '\u200b': '', '\ufeff': '', '\u00a0': ' '}


def _hi_sanitize(text, probe=None):
    if not text:
        return text
    for k, v in _HI_REPL.items():
        text = text.replace(k, v)
    text = _EMOJI_RE.sub('', text)
    out = []
    for i, ch in enumerate(text):
        if ch in '\u200c\u200d':                # keep joiners only inside Devanagari words
            if out and _DEVA_RE.match(out[-1]):
                out.append(ch)
            continue
        if (probe is not None and ord(ch) >= 0x80 and ch != ' '
                and not _DEVA_RE.match(ch) and not probe.has_glyph(ch)):
            continue                              # font cannot draw it -> drop (no box)
        out.append(ch)
    return re.sub(r'[ \t]+', ' ', ''.join(out)).strip()


def _speak_clean(text, lang):
    """Make text TTS-friendly. English is returned unchanged (V9 behaviour)."""
    if lang != 'hi':
        return text
    t = _hi_sanitize(text)
    for letter, spoken in zip('ABCD', _STR['hi']['letters_spoken']):
        t = re.sub(r'\(\s*' + letter + r'\s*\)', ' ' + spoken + ' ', t, flags=re.IGNORECASE)
    t = (t.replace('%', ' \u092a\u094d\u0930\u0924\u093f\u0936\u0924 ')
          .replace('\u20b9', '\u0930\u0941\u092a\u092f\u0947 ')
          .replace('->', ', ').replace('>', ', \u092b\u093f\u0930 ').replace('<', ', ')
          .replace('/', ' ').replace('*', ' '))
    return re.sub(r'\s+', ' ', t).strip()


def _prep_questions_for_lang(questions, lang):
    """Returns copies of the questions with Hindi text sanitised."""
    if lang != 'hi':
        return questions
    probe = _load_font(24, bold=True)
    probe = probe if isinstance(probe, _HBFont) else None
    out = []
    for q in questions:
        nq = dict(q)
        nq['questionText'] = _hi_sanitize(q.get('questionText', ''), probe)
        nq['options']      = [_hi_sanitize(o, probe) for o in q.get('options', [])]
        nq['explanation']  = _hi_sanitize(q.get('explanation', ''), probe)
        out.append(nq)
    return out


# ─── Devanagari font discovery ────────────────────────────────────────────────
def _hindi_font_dirs():
    dirs = []
    custom = os.environ.get('HINDI_FONT_DIR')
    if custom:
        dirs.append(custom)
    here = os.path.dirname(os.path.abspath(__file__))
    dirs.append(os.path.join(here, 'fonts'))
    win = os.environ.get('WINDIR', r'C:\Windows')
    dirs.append(os.path.join(win, 'Fonts'))
    la = os.environ.get('LOCALAPPDATA')
    if la:
        dirs.append(os.path.join(la, 'Microsoft', 'Windows', 'Fonts'))
    dirs += ['/system/fonts', '/system/font',
             '/usr/share/fonts/truetype/noto', '/usr/share/fonts/truetype/lohit-devanagari']
    return dirs


_HI_BOLD_NAMES = ["hindi_bold.ttf", "NirmalaB.ttf", "mangalb.ttf", "NotoSansDevanagari-Bold.ttf",
                  "Nirmala.ttf", "Nirmala.ttc", "mangal.ttf", "Lohit-Devanagari.ttf"]
_HI_REG_NAMES  = ["hindi_regular.ttf", "Nirmala.ttf", "Nirmala.ttc", "mangal.ttf",
                  "NotoSansDevanagari-Regular.ttf", "Lohit-Devanagari.ttf"]
_HI_PATH_CACHE = {}


def _find_hindi_font(bold=True):
    if bold in _HI_PATH_CACHE:
        return _HI_PATH_CACHE[bold]
    found = None
    for name in (_HI_BOLD_NAMES if bold else _HI_REG_NAMES):
        for d in _hindi_font_dirs():
            p = os.path.join(d, name)
            if os.path.exists(p):
                found = p
                break
        if found:
            break
    _HI_PATH_CACHE[bold] = found
    return found


_LATIN_BOLD_NAMES = ["OpenSans-Bold.ttf", "Roboto-Bold.ttf", "segoeuib.ttf", "arialbd.ttf", "calibrib.ttf", "DejaVuSans-Bold.ttf",
                     "LiberationSans-Bold.ttf"]
_LATIN_REG_NAMES  = ["OpenSans-Regular.ttf", "Roboto-Regular.ttf", "segoeui.ttf", "arial.ttf", "calibri.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"]


def _find_latin_font(bold=True):
    dirs = _hindi_font_dirs() + ['/usr/share/fonts/truetype/dejavu',
                                 '/usr/share/fonts/truetype/liberation']
    for name in (_LATIN_BOLD_NAMES if bold else _LATIN_REG_NAMES):
        for d in dirs:
            p = os.path.join(d, name)
            if os.path.exists(p):
                return p
    return None


class _HBFont:
    """Font that shapes with HarfBuzz and rasterises with FreeType, so Devanagari
    matras / conjuncts come out right on any Pillow build (no libraqm / fribidi needed).
    One instance per (thread, font, size) - FreeType faces are not thread-safe."""

    def __init__(self, path, size, fallback=None):
        self.path = path
        self.size = int(size)
        self.fallback = fallback          # _HBFont used for characters this font lacks (e.g. A-Z)
        self._face = hb.Face(hb.Blob.from_file_path(path), 0)
        self._font = hb.Font(self._face)
        self._upem = self._face.upem or 1000
        self._ft = freetype.Face(path)
        self._ft.set_pixel_sizes(0, self.size)
        self.ascent = int(math.ceil(self._ft.size.ascender / 64.0))
        self._shape_c, self._glyph_c, self._mask_c = {}, {}, {}

    def _own_glyph(self, ch):
        try:
            return self._ft.get_char_index(ord(ch)) != 0
        except Exception:
            return True

    def has_glyph(self, ch):
        return self._own_glyph(ch) or (self.fallback is not None and self.fallback._own_glyph(ch))

    def shape(self, text):
        """-> ([(font, glyph_id, x, y), ...], total_advance).  Runs of characters that the main
        font lacks are shaped with the fallback font."""
        c = self._shape_c.get(text)
        if c is None:
            runs, cur_f, cur = [], None, ''
            for ch in text:
                f = self
                if (self.fallback is not None and ch != ' ' and not self._own_glyph(ch)
                        and self.fallback._own_glyph(ch)):
                    f = self.fallback
                if ch == ' ' and cur_f is not None:
                    f = cur_f
                if cur and f is not cur_f:
                    runs.append((cur_f, cur)); cur = ''
                cur_f = f
                cur += ch
            if cur:
                runs.append((cur_f, cur))
            glyphs, x = [], 0.0
            for f, sub in runs:
                g, adv = f._shape_run(sub)
                glyphs.extend((f, gid, gx + x, gy) for gid, gx, gy in g)
                x += adv
            c = (glyphs, x)
            if len(self._shape_c) > 4000:
                self._shape_c.clear()
            self._shape_c[text] = c
        return c

    def _shape_run(self, text):
        if True:
            buf = hb.Buffer()
            buf.add_str(text)
            if _DEVA_RE.search(text):          # shape the WHOLE run as Devanagari even if it
                buf.script = 'Deva'            # starts with a Latin word
                buf.direction = 'ltr'
                buf.language = 'hi'
            else:
                buf.guess_segment_properties()
            hb.shape(self._font, buf, {})
            k = self.size / float(self._upem)
            glyphs, x = [], 0.0
            for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
                glyphs.append((info.codepoint, x + pos.x_offset * k, -pos.y_offset * k))
                x += pos.x_advance * k
            return glyphs, x

    def width(self, text):
        return int(math.ceil(self.shape(text)[1]))

    def _glyph(self, gid):
        g = self._glyph_c.get(gid)
        if g is None:
            self._ft.load_glyph(gid, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
            slot = self._ft.glyph
            bm = slot.bitmap
            w, h, pitch = bm.width, bm.rows, bm.pitch
            im = None
            if w and h:
                data = bytes(bm.buffer)
                if pitch != w:
                    data = b''.join(data[r * pitch:r * pitch + w] for r in range(h))
                im = Image.frombytes('L', (w, h), data)
            g = (im, slot.bitmap_left, slot.bitmap_top)
            self._glyph_c[gid] = g
        return g

    def _mask(self, text):
        m = self._mask_c.get(text)
        if m is None:
            glyphs, _adv = self.shape(text)
            placed = []
            x0 = y0 = 10 ** 9
            x1 = y1 = -10 ** 9
            for gfont, gid, gx, gy in glyphs:
                im, left, top = gfont._glyph(gid)
                if im is None:
                    continue
                px = int(round(gx)) + left
                py = self.ascent + int(round(gy)) - top
                placed.append((im, px, py))
                x0 = min(x0, px); y0 = min(y0, py)
                x1 = max(x1, px + im.width); y1 = max(y1, py + im.height)
            if not placed:
                m = (None, 0, 0)
            else:
                canvas = Image.new('L', (x1 - x0, y1 - y0), 0)
                for im, px, py in placed:
                    canvas.paste(255, (px - x0, py - y0), im)
                m = (canvas, x0, y0)
            if len(self._mask_c) > 600:
                self._mask_c.clear()
            self._mask_c[text] = m
        return m

    def bbox(self, text):
        canvas, ox, oy = self._mask(text)
        bb = canvas.getbbox() if canvas is not None else None
        if bb is None:
            return (0, 0, self.width(text), 0)
        return (ox + bb[0], oy + bb[1], ox + bb[2], oy + bb[3])

    def draw(self, draw, xy, text, fill, ink=False):
        canvas, ox, oy = self._mask(text)
        if canvas is None:
            return
        x, y = int(round(xy[0])), int(round(xy[1]))
        if ink:                                   # y = top of the visible ink (not of the line box)
            y -= self.bbox(text)[1]
        alpha = fill[3] if len(fill) > 3 else 255
        mask = canvas if alpha >= 255 else canvas.point(lambda v, a=alpha: v * a // 255)
        img = getattr(draw, '_image', None) or getattr(draw, 'im', None)
        img.paste(tuple(fill[:3]), (x + ox, y + oy), mask)


def _load_hindi_font(size, bold=True, heavy=False):
    path = _find_hindi_font(bold or heavy)
    if not path:
        return None
    cache = getattr(_TL, 'hi_cache', None)
    if cache is None:
        cache = _TL.hi_cache = {}
    key = (path, size, HAS_HB)
    f = cache.get(key)
    if f is not None:
        return f
    try:
        if HAS_HB:
            f = _HBFont(path, size)
            if not f._own_glyph('A'):            # Hindi-only font -> borrow Latin letters
                lp = _find_latin_font(bold or heavy)
                if lp:
                    f.fallback = _HBFont(lp, size)
        else:
            _warn_once('nohb', "[WARNING] 'uharfbuzz' / 'freetype-py' not installed - Hindi conjuncts may "
                               "look wrong.  Run:  pip install uharfbuzz freetype-py")
            f = ImageFont.truetype(path, size)
    except Exception as e:
        _warn_once('hbfail', f"[WARNING] Hindi font engine failed ({e}) - falling back to Pillow.")
        try:
            f = ImageFont.truetype(path, size)
        except Exception:
            return None
    cache[key] = f
    return f


def _load_font(size, bold=True, heavy=False):
    """Font for the slide being rendered (Devanagari-capable when it is a Hindi slide)."""
    if getattr(_TL, 'lang', 'en') == 'hi':
        f = _load_hindi_font(size, bold, heavy)
        if f is not None:
            return f
    return _load_pil_font(size, bold, heavy)


def _find_font_file(names):
    dirs = _hindi_font_dirs() + [r"C:\\Windows\\Fonts", '/usr/share/fonts/truetype/dejavu',
                                 '/usr/share/fonts/truetype/liberation']
    for name in names:
        for d in dirs:
            p = os.path.join(d, name)
            if os.path.exists(p):
                return p
    return None


def _load_pil_font(size, bold=True, heavy=False):
    """Latin font for slides.  Order: bundled Open Sans -> Windows Segoe/Arial -> Android Roboto
    -> DejaVu.  (The old code only looked in C:\\Windows\\Fonts, so on a phone it fell back to a
    tiny bitmap font.)"""
    key = (size, bold, heavy)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    if heavy:
        candidates = ["OpenSans-ExtraBold.ttf", "seguibl.ttf", "OpenSans-Bold.ttf", "segoeuib.ttf",
                      "Roboto-Black.ttf", "Roboto-Bold.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"]
    elif bold:
        candidates = ["OpenSans-Bold.ttf", "segoeuib.ttf", "Roboto-Bold.ttf", "arialbd.ttf",
                      "calibrib.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"]
    else:
        candidates = ["OpenSans-Regular.ttf", "segoeui.ttf", "Roboto-Regular.ttf", "arial.ttf",
                      "calibri.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"]
    for name in candidates:
        path = _find_font_file([name])
        if path:
            try:
                font = ImageFont.truetype(path, size)
                _FONT_CACHE[key] = font
                return font
            except Exception:
                continue
    try:
        font = ImageFont.load_default(size)       # Pillow >= 10.1 gives a scalable font
    except Exception:
        font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


_EMOJI_FONT_FILES = ["NotoColorEmoji.ttf", "seguiemj.ttf", "seguisym.ttf"]
_EMOJI_IMG_CACHE = {}


def _emoji_image(char, size):
    """Colour emoji as an RGBA image `size` px tall.  Android's Noto Color Emoji is a bitmap font
    that only exists at 109 px, so it is drawn at 109 and scaled."""
    key = (char, int(size))
    if key in _EMOJI_IMG_CACHE:
        return _EMOJI_IMG_CACHE[key]
    result = None
    path = _find_font_file(["NotoColorEmoji.ttf"])
    if path:
        try:
            f = ImageFont.truetype(path, 109)
            canvas = Image.new('RGBA', (160, 160), (0, 0, 0, 0))
            ImageDraw.Draw(canvas).text((10, 10), char, font=f, embedded_color=True)
            bb = canvas.getbbox()
            if bb:
                glyph = canvas.crop(bb)
                k = float(size) / max(glyph.width, glyph.height)
                result = glyph.resize((max(1, int(glyph.width * k)), max(1, int(glyph.height * k))),
                                      Image.LANCZOS)
        except Exception:
            result = None
    _EMOJI_IMG_CACHE[key] = result
    return result


def _load_emoji_font(size):
    """Vector emoji font (Windows).  On Android use _emoji_image() instead."""
    for name in ["seguiemj.ttf", "seguisym.ttf"]:
        path = _find_font_file([name])
        if path:
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return _load_pil_font(size, bold=True)


# ─── OFFLINE STICKER SYSTEM ────────────────────────────────────────────────
STICKER_MAP = {
    "president": {"keywords": ['president', 'rashtrapati', 'president of india', 'raisina hill', 'rashtrapati bhavan', 'head of state'], "emoji": "🏛️"},
    "vice_president": {"keywords": ['vice president', 'up-rashtrapati', 'upa rashtrapati', 'vice-president of india', 'chairman of rajya sabha'], "emoji": "🎗️"},
    "prime_minister": {"keywords": ['prime minister', 'pradhan mantri', 'pm', 'pm of india', 'pmo', 'council of prime minister', 'head of government'], "emoji": "🎙️"},
    "parliament": {"keywords": ['parliament', 'lok sabha', 'rajya sabha', 'sansad', 'lower house', 'upper house', 'speaker of lok sabha', 'bicameral legislature'], "emoji": "🏛️"},
    "constitution": {"keywords": ['constitution', 'samvidhan', 'article', 'preamble', 'constituent assembly', 'dr br ambedkar', 'constitution of india', 'schedules of constitution'], "emoji": "📜"},
    "fundamental_rights": {"keywords": ['fundamental rights', 'mool adhikar', 'right to equality', 'right to freedom', 'right against exploitation', 'cultural and educational rights'], "emoji": "✊"},
    "directive_principles": {"keywords": ['directive principles', 'dpsp', 'state policy', 'part iv'], "emoji": "📘"},
    "amendment": {"keywords": ['amendment', 'sanshodhan', 'constitutional amendment', '42nd amendment', '44th amendment'], "emoji": "✏️"},
    "supreme_court": {"keywords": ['supreme court', 'chief justice', 'cji', 'apex court', 'judicial appointment', 'collegium system'], "emoji": "⚖️"},
    "high_court": {"keywords": ['high court', 'state judiciary'], "emoji": "⚖️"},
    "judiciary": {"keywords": ['judiciary', 'judicial', 'judicial review', 'separation of powers', 'rule of law'], "emoji": "⚖️"},
    "election_commission": {"keywords": ['election commission', 'election', 'voting', 'chunav', 'general election', 'by-election', 'voter id', 'evm', 'chief election commissioner'], "emoji": "🗳️"},
    "governor": {"keywords": ['governor', 'rajyapal', 'state governor'], "emoji": "🏢"},
    "chief_minister": {"keywords": ['chief minister', 'mukhyamantri', 'cm of', 'state government head'], "emoji": "🏢"},
    "panchayat": {"keywords": ['panchayat', 'gram sabha', 'local self government', 'panchayati raj', '73rd amendment'], "emoji": "🏘️"},
    "municipality": {"keywords": ['municipality', 'municipal corporation', 'urban local body', '74th amendment'], "emoji": "🏙️"},
    "cabinet": {"keywords": ['cabinet', 'council of ministers', 'cabinet minister', 'cabinet secretary'], "emoji": "🗂️"},
    "emergency": {"keywords": ['national emergency', "president's rule", 'emergency provisions', 'financial emergency', '1975 emergency'], "emoji": "🚨"},
    "citizenship": {"keywords": ['citizenship', 'nagrikta', 'citizenship act', 'caa'], "emoji": "🪪"},
    "federalism": {"keywords": ['federalism', 'federal structure', 'centre-state relations', 'concurrent list', 'union list', 'state list'], "emoji": "🧩"},
    "upsc": {"keywords": ['upsc', 'civil services', 'ias', 'ips', 'ifs officer', 'public service commission'], "emoji": "📋"},
    "niti_aayog": {"keywords": ['niti aayog', 'planning commission', 'national institution for transforming india'], "emoji": "📊"},
    "human_rights": {"keywords": ['human rights', 'nhrc', 'national human rights commission'], "emoji": "🕊️"},
    "rti": {"keywords": ['right to information', 'rti act', 'transparency law'], "emoji": "📄"},
    "national_flag": {"keywords": ['national flag', 'tiranga', 'indian flag', 'flag code of india', 'ashoka chakra on flag'], "emoji": "🇮🇳"},
    "national_anthem": {"keywords": ['national anthem', 'jana gana mana', 'rabindranath tagore anthem'], "emoji": "🎵"},
    "national_song": {"keywords": ['national song', 'vande mataram'], "emoji": "🎶"},
    "national_emblem": {"keywords": ['national emblem', 'ashoka chakra', 'lion capital', 'sarnath pillar', 'satyamev jayate'], "emoji": "🦁"},
    "national_bird": {"keywords": ['national bird', 'peacock', 'mor'], "emoji": "🦚"},
    "national_animal": {"keywords": ['national animal', 'tiger', 'bagh', 'royal bengal tiger'], "emoji": "🐅"},
    "national_aquatic_animal": {"keywords": ['national aquatic animal', 'river dolphin', 'gangetic dolphin'], "emoji": "🐬"},
    "national_flower": {"keywords": ['national flower', 'lotus', 'kamal'], "emoji": "🪷"},
    "national_tree": {"keywords": ['national tree', 'banyan tree', 'vat vriksha'], "emoji": "🌳"},
    "national_fruit": {"keywords": ['national fruit', 'mango', 'aam'], "emoji": "🥭"},
    "national_sport": {"keywords": ['national sport', 'field hockey of india'], "emoji": "🏑"},
    "economy": {"keywords": ['economy', 'economics', 'arthvyavastha', 'economic policy', 'mixed economy', 'planned economy'], "emoji": "💹"},
    "gdp": {"keywords": ['gdp', 'gross domestic product', 'gnp', 'national income', 'per capita income', 'nominal gdp', 'gdp growth rate'], "emoji": "📈"},
    "inflation": {"keywords": ['inflation', 'mehngai', 'deflation', 'cpi', 'wpi', 'consumer price index', 'wholesale price index'], "emoji": "💸"},
    "rbi": {"keywords": ['rbi', 'reserve bank', 'monetary policy', 'repo rate', 'reverse repo', 'crr', 'slr', 'central bank of india'], "emoji": "🏦"},
    "fiscal_policy": {"keywords": ['fiscal policy', 'budget', 'finance minister', 'fiscal deficit', 'union budget', 'annual financial statement'], "emoji": "💰"},
    "tax": {"keywords": ['tax', 'gst', 'income tax', 'direct tax', 'indirect tax', 'goods and services tax', 'customs duty'], "emoji": "🧾"},
    "stock_market": {"keywords": ['stock market', 'sensex', 'nifty', 'share market', 'stock exchange', 'bse', 'nse', 'ipo', 'mutual fund'], "emoji": "📊"},
    "disinvestment": {"keywords": ['disinvestment', 'privatisation', 'psu', 'public sector undertaking'], "emoji": "🏭"},
    "subsidy": {"keywords": ['subsidy', 'poverty', 'unemployment', 'bpl', 'below poverty line', 'minimum wage'], "emoji": "🪙"},
    "banking": {"keywords": ['banking', 'npa', 'bank', 'loan', 'credit', 'nationalisation of banks', 'cooperative bank'], "emoji": "🏦"},
    "five_year_plan": {"keywords": ['five year plan', 'planning', 'first five year plan'], "emoji": "🗓️"},
    "foreign_trade": {"keywords": ['foreign trade', 'export', 'import', 'balance of payment', 'fdi', 'foreign direct investment'], "emoji": "🚢"},
    "currency": {"keywords": ['currency', 'rupee', 'exchange rate', 'demonetisation', 'legal tender'], "emoji": "💵"},
    "world_bank": {"keywords": ['world bank', 'imf', 'wto', 'international monetary fund', 'world trade organization'], "emoji": "🌐"},
    "msme": {"keywords": ['msme', 'small scale industry', 'startup india', 'make in india'], "emoji": "🏢"},
    "agriculture_economy": {"keywords": ['agriculture', 'crop', 'irrigation', 'farmer', 'green revolution', 'white revolution', 'kharif crop', 'rabi crop', 'minimum support price'], "emoji": "🌾"},
    "history": {"keywords": ['history', 'itihas', 'chronology'], "emoji": "📜"},
    "indus_valley": {"keywords": ['indus valley', 'harappa', 'mohenjo daro', 'lothal', 'dholavira', 'bronze age india'], "emoji": "🏺"},
    "vedic_period": {"keywords": ['vedic period', 'vedas', 'vedic age', 'rigveda', 'upanishads'], "emoji": "📖"},
    "maurya_empire": {"keywords": ['maurya empire', 'chandragupta maurya', 'ashoka the great', 'kalinga war', 'bindusara'], "emoji": "🐘"},
    "gupta_empire": {"keywords": ['gupta empire', 'gupta period', 'golden age of india', 'samudragupta', 'chandragupta ii'], "emoji": "👑"},
    "mughal_empire": {"keywords": ['mughal', 'akbar', 'shah jahan', 'aurangzeb', 'babur', 'humayun', 'jahangir', 'mughal dynasty'], "emoji": "🕌"},
    "freedom_struggle": {"keywords": ['independence', 'freedom struggle', 'swatantrata', 'quit india movement', 'civil disobedience movement', 'non-cooperation movement', 'salt march', 'dandi march'], "emoji": "✊"},
    "indian_national_congress": {"keywords": ['indian national congress', 'inc formed', 'ac hume', '1885 congress'], "emoji": "🎗️"},
    "gandhi": {"keywords": ['mahatma gandhi', 'gandhiji', 'satyagraha', 'father of the nation', 'champaran satyagraha'], "emoji": "🕊️"},
    "nehru": {"keywords": ['jawaharlal nehru', 'first prime minister of india', 'tryst with destiny'], "emoji": "🎩"},
    "bhagat_singh": {"keywords": ['bhagat singh', 'revolutionary movement', 'hindustan socialist republican association'], "emoji": "🔥"},
    "subhash_chandra_bose": {"keywords": ['subhas chandra bose', 'azad hind fauj', 'indian national army', 'jai hind slogan'], "emoji": "🎖️"},
    "rani_lakshmibai": {"keywords": ['rani lakshmibai', 'jhansi ki rani', '1857 revolt', 'sepoy mutiny'], "emoji": "🗡️"},
    "partition": {"keywords": ['partition of india', '1947 partition', 'radcliffe line'], "emoji": "🗺️"},
    "independence_day": {"keywords": ['independence day', '15 august', '1947 independence'], "emoji": "🎉"},
    "republic_day": {"keywords": ['republic day', '26 january', '1950 republic'], "emoji": "🎊"},
    "world_war": {"keywords": ['world war', 'first world war', 'second world war', 'ww1', 'ww2', 'allied powers', 'axis powers'], "emoji": "⚔️"},
    "french_revolution": {"keywords": ['french revolution', '1789 revolution', 'bastille'], "emoji": "🇫🇷"},
    "russian_revolution": {"keywords": ['russian revolution', 'bolshevik', 'lenin revolution'], "emoji": "🇷🇺"},
    "industrial_revolution": {"keywords": ['industrial revolution', 'machine age'], "emoji": "🏭"},
    "cold_war": {"keywords": ['cold war', 'superpower rivalry', 'iron curtain'], "emoji": "🧊"},
    "taj_mahal": {"keywords": ['taj mahal', 'mumtaz mahal tomb', 'agra monument'], "emoji": "🕌"},
    "red_fort": {"keywords": ['red fort', 'lal qila'], "emoji": "🏯"},
    "qutub_minar": {"keywords": ['qutub minar', 'qutb minar'], "emoji": "🗼"},
    "india_gate": {"keywords": ['india gate', 'all india war memorial'], "emoji": "🎗️"},
    "gateway_of_india": {"keywords": ['gateway of india', 'mumbai monument'], "emoji": "🏛️"},
    "charminar": {"keywords": ['charminar', 'hyderabad monument'], "emoji": "🕌"},
    "konark_temple": {"keywords": ['konark sun temple', 'konark temple'], "emoji": "🛕"},
    "golden_temple": {"keywords": ['golden temple', 'harmandir sahib', 'amritsar'], "emoji": "🛕"},
    "geography": {"keywords": ['geography', 'bhugol', 'physical geography'], "emoji": "🗺️"},
    "continent": {"keywords": ['continent', 'asia continent', 'europe continent', 'africa continent', 'seven continents'], "emoji": "🌍"},
    "ocean": {"keywords": ['ocean', 'sea', 'samudra', 'five oceans', 'pacific ocean', 'atlantic ocean', 'indian ocean'], "emoji": "🌊"},
    "river": {"keywords": ['river', 'nadi', 'tributary', 'river system', 'river basin'], "emoji": "🏞️"},
    "river_ganga": {"keywords": ['ganga river', 'ganges river', 'ganga basin', 'gangotri'], "emoji": "🏞️"},
    "river_yamuna": {"keywords": ['yamuna river', 'yamunotri'], "emoji": "🏞️"},
    "river_brahmaputra": {"keywords": ['brahmaputra river'], "emoji": "🏞️"},
    "river_godavari": {"keywords": ['godavari river', 'dakshin ganga'], "emoji": "🏞️"},
    "river_krishna": {"keywords": ['krishna river'], "emoji": "🏞️"},
    "river_narmada": {"keywords": ['narmada river'], "emoji": "🏞️"},
    "river_kaveri": {"keywords": ['kaveri river', 'cauvery river'], "emoji": "🏞️"},
    "river_indus": {"keywords": ['indus river', 'sindhu river'], "emoji": "🏞️"},
    "mountain": {"keywords": ['mountain', 'himalaya', 'himalayas', 'himalayan', 'peak', 'hills', 'mountain range'], "emoji": "⛰️"},
    "mount_everest": {"keywords": ['mount everest', 'sagarmatha', 'highest peak'], "emoji": "🏔️"},
    "kangchenjunga": {"keywords": ['kangchenjunga', 'kanchenjunga'], "emoji": "🏔️"},
    "nanda_devi": {"keywords": ['nanda devi peak'], "emoji": "🏔️"},
    "k2_peak": {"keywords": ['k2 mountain', 'godwin austen'], "emoji": "🏔️"},
    "western_ghats": {"keywords": ['western ghats', 'eastern ghats'], "emoji": "🏔️"},
    "desert": {"keywords": ['desert', 'thar desert', 'sahara desert', 'arid region'], "emoji": "🏜️"},
    "plateau": {"keywords": ['plateau', 'deccan plateau', 'chota nagpur plateau'], "emoji": "🪨"},
    "volcano": {"keywords": ['volcano', 'volcanic', 'barren island volcano'], "emoji": "🌋"},
    "earthquake": {"keywords": ['earthquake', 'seismic', 'tsunami', 'richter scale'], "emoji": "🌐"},
    "climate": {"keywords": ['climate', 'monsoon', 'rainfall', 'weather', 'climate zones', 'cyclone'], "emoji": "🌦️"},
    "latitude_longitude": {"keywords": ['latitude', 'longitude', 'equator', 'tropic of cancer', 'prime meridian'], "emoji": "🧭"},
    "timezone": {"keywords": ['time zone', 'gmt', 'ist', 'indian standard time'], "emoji": "🕰️"},
    "population": {"keywords": ['population', 'census', 'demography', 'sex ratio', 'literacy rate'], "emoji": "👥"},
    "capital_city": {"keywords": ['capital of', 'rajdhani', 'national capital'], "emoji": "🏙️"},
    "map": {"keywords": ['map', 'border', 'boundary', 'cartography'], "emoji": "🗺️"},
    "minerals": {"keywords": ['minerals', 'natural resources', 'mining', 'coal', 'iron ore', 'bauxite', 'mineral belt'], "emoji": "⛏️"},
    "forest": {"keywords": ['forest', 'wildlife sanctuary', 'national park', 'biodiversity hotspot', 'tiger reserve', 'biosphere reserve'], "emoji": "🌳"},
    "state_rajasthan": {"keywords": ['rajasthan', 'jaipur', 'thar desert state'], "emoji": "🏜️"},
    "state_kerala": {"keywords": ['kerala', 'thiruvananthapuram', 'backwaters', 'gods own country'], "emoji": "🌴"},
    "state_punjab": {"keywords": ['punjab state', 'chandigarh', 'land of five rivers'], "emoji": "🌾"},
    "state_goa": {"keywords": ['goa', 'panaji', 'goa beaches'], "emoji": "🏖️"},
    "state_kashmir": {"keywords": ['jammu and kashmir', 'srinagar', 'kashmir valley'], "emoji": "🏔️"},
    "state_gujarat": {"keywords": ['gujarat', 'gandhinagar', 'rann of kutch'], "emoji": "🦁"},
    "state_maharashtra": {"keywords": ['maharashtra', 'mumbai state', 'pune'], "emoji": "🏙️"},
    "state_tamil_nadu": {"keywords": ['tamil nadu', 'chennai', 'madras'], "emoji": "🛕"},
    "state_west_bengal": {"keywords": ['west bengal', 'kolkata', 'calcutta'], "emoji": "🎭"},
    "state_uttar_pradesh": {"keywords": ['uttar pradesh', 'lucknow'], "emoji": "🕌"},
    "state_assam": {"keywords": ['assam', 'guwahati', 'kaziranga'], "emoji": "🦏"},
    "state_sikkim": {"keywords": ['sikkim', 'gangtok'], "emoji": "🏔️"},
    "state_bihar": {"keywords": ['bihar', 'patna', 'nalanda'], "emoji": "📜"},
    "state_odisha": {"keywords": ['odisha', 'orissa', 'bhubaneswar'], "emoji": "🛕"},
    "state_karnataka": {"keywords": ['karnataka', 'bengaluru', 'bangalore'], "emoji": "💻"},
    "state_telangana": {"keywords": ['telangana', 'hyderabad state'], "emoji": "🕌"},
    "state_madhya_pradesh": {"keywords": ['madhya pradesh', 'bhopal'], "emoji": "🐅"},
    "state_himachal": {"keywords": ['himachal pradesh', 'shimla'], "emoji": "⛰️"},
    "state_uttarakhand": {"keywords": ['uttarakhand', 'dehradun', 'char dham'], "emoji": "🏔️"},
    "state_northeast": {"keywords": ['manipur', 'meghalaya', 'mizoram', 'nagaland', 'tripura', 'arunachal pradesh'], "emoji": "🌄"},
    "science": {"keywords": ['science', 'vigyan', 'scientific method'], "emoji": "🔬"},
    "physics": {"keywords": ['physics', 'gravity', 'newton', 'motion', 'force', 'energy', 'laws of motion', 'thermodynamics'], "emoji": "🧲"},
    "electricity": {"keywords": ['electricity', 'current', 'circuit', 'magnetism', 'electromagnetic', 'ohms law'], "emoji": "⚡"},
    "light_sound": {"keywords": ['light', 'sound', 'reflection', 'refraction', 'wave', 'doppler effect', 'lens'], "emoji": "💡"},
    "chemistry": {"keywords": ['chemistry', 'element', 'compound', 'reaction', 'atom', 'periodic table', 'chemical formula', 'water', 'molecule', 'valency', 'acid rain'], "emoji": "🧪"},
    "acid_base": {"keywords": ['acid', 'base', 'ph value', 'alkaline', 'litmus test'], "emoji": "🧫"},
    "biology": {"keywords": ['biology', 'cell', 'organism', 'human body', 'tissue', 'photosynthesis', 'cell organelles'], "emoji": "🧬"},
    "respiratory_digestive": {"keywords": ['respiratory system', 'digestive system', 'nervous system', 'circulatory system', 'excretory system', 'skeletal system'], "emoji": "🫁"},
    "genetics": {"keywords": ['genetics', 'dna', 'gene', 'heredity', 'evolution', 'mendel laws', 'chromosome'], "emoji": "🧬"},
    "ecosystem": {"keywords": ['ecosystem', 'environment', 'pollution', 'global warming', 'climate change', 'food chain', 'biosphere'], "emoji": "🌱"},
    "renewable_energy": {"keywords": ['renewable energy', 'solar energy', 'wind energy', 'hydro power', 'non-conventional energy'], "emoji": "🔋"},
    "space": {"keywords": ['space', 'solar system', 'planet', 'satellite', 'astronomy', 'galaxy', 'black hole', 'asteroid'], "emoji": "🚀"},
    "isro_missions": {"keywords": ['isro', 'chandrayaan', 'mangalyaan', 'gaganyaan', 'aditya l1', 'pslv', 'gslv', 'indian space research organisation'], "emoji": "🛰️"},
    "nasa_missions": {"keywords": ['nasa', 'apollo mission', 'hubble telescope', 'mars rover'], "emoji": "🚀"},
    "computer": {"keywords": ['computer', 'technology', 'internet', 'software', 'hardware', 'operating system', 'computer memory'], "emoji": "💻"},
    "artificial_intelligence": {"keywords": ['artificial intelligence', 'machine learning', 'deep learning', 'neural network'], "emoji": "🤖"},
    "cyber_security": {"keywords": ['cyber security', 'hacking', 'data privacy', 'cyber crime', 'malware'], "emoji": "🔒"},
    "robotics": {"keywords": ['robotics', 'robot', 'automation'], "emoji": "🦾"},
    "mobile_social_media": {"keywords": ['mobile technology', 'social media', 'smartphone', 'app development'], "emoji": "📱"},
    "grammar": {"keywords": ['grammar', 'tense', 'noun', 'pronoun', 'verb', 'adjective', 'adverb', 'preposition', 'conjunction', 'active passive voice', 'direct indirect speech'], "emoji": "📖"},
    "vocabulary": {"keywords": ['synonym', 'antonym', 'vocabulary', 'meaning of', 'idiom', 'phrase', 'one word substitution'], "emoji": "📚"},
    "comprehension": {"keywords": ['comprehension', 'passage', 'reading comprehension'], "emoji": "📃"},
    "literature": {"keywords": ['poem', 'poet', 'novel', 'author', 'literature', 'essay', 'speech', 'playwright', 'shakespeare'], "emoji": "✒️"},
    "sports_general": {"keywords": ['sports', 'olympics', 'asian games', 'commonwealth games', 'world cup', 'sports award', 'paralympics'], "emoji": "🏆"},
    "cricket": {"keywords": ['cricket', 'batsman', 'bowler', 'test match', 'odi', 'ipl', 'wicket', 'century', 'world cup cricket'], "emoji": "🏏"},
    "football": {"keywords": ['football', 'fifa', 'soccer', 'goal', 'world cup football'], "emoji": "⚽"},
    "hockey": {"keywords": ['hockey', 'field hockey', 'dhyan chand'], "emoji": "🏑"},
    "tennis_badminton": {"keywords": ['tennis', 'badminton', 'wimbledon', 'grand slam', 'shuttlecock'], "emoji": "🎾"},
    "chess": {"keywords": ['chess', 'grandmaster', 'checkmate'], "emoji": "♟️"},
    "athletics": {"keywords": ['athletics', 'marathon', 'sprint', 'long jump', 'high jump'], "emoji": "🏃"},
    "kabaddi_wrestling": {"keywords": ['kabaddi', 'wrestling', 'boxing', 'akhada'], "emoji": "🤼"},
    "swimming": {"keywords": ['swimming', 'swimmer'], "emoji": "🏊"},
    "badminton_player": {"keywords": ['badminton player', 'shuttler'], "emoji": "🏸"},
    "award": {"keywords": ['award', 'prize', 'nobel prize', 'bharat ratna', 'padma awards', 'padma vibhushan', 'padma bhushan', 'padma shri', 'arjuna award', 'pulitzer', 'oscar', 'grammy', 'khel ratna'], "emoji": "🏅"},
    "defence": {"keywords": ['defence', 'army', 'navy', 'air force', 'missile', 'drdo', 'nuclear weapon', 'border security', 'military exercise', 'cds', 'chief of defence staff'], "emoji": "🎖️"},
    "organizations": {"keywords": ['united nations', 'world health organization', 'unesco', 'unicef', 'saarc', 'brics', 'nato', 'european union', 'g20', 'commonwealth of nations', 'asean', 'opec', 'un security council'], "emoji": "🌐"},
    "culture": {"keywords": ['culture', 'festival', 'heritage site', 'unesco heritage', 'folk tradition'], "emoji": "🎭"},
    "religion_hinduism": {"keywords": ['hinduism', 'hindu religion', 'vedic religion', 'sanatan dharma'], "emoji": "🕉️"},
    "religion_islam": {"keywords": ['islam', 'muslim religion', 'quran'], "emoji": "☪️"},
    "religion_christianity": {"keywords": ['christianity', 'christian religion', 'bible'], "emoji": "✝️"},
    "religion_sikhism": {"keywords": ['sikhism', 'sikh religion', 'guru granth sahib', 'guru nanak'], "emoji": "☬"},
    "religion_buddhism": {"keywords": ['buddhism', 'gautam buddha', 'buddhist religion', 'eightfold path'], "emoji": "☸️"},
    "religion_jainism": {"keywords": ['jainism', 'mahavira', 'jain religion'], "emoji": "🙏"},
    "dance_bharatanatyam": {"keywords": ['bharatanatyam', 'classical dance tamil nadu'], "emoji": "💃"},
    "dance_kathak": {"keywords": ['kathak dance', 'kathak'], "emoji": "💃"},
    "dance_kathakali": {"keywords": ['kathakali', 'kerala dance'], "emoji": "🎭"},
    "dance_bhangra": {"keywords": ['bhangra dance', 'punjab dance'], "emoji": "💃"},
    "music_instrument": {"keywords": ['sitar', 'tabla', 'veena', 'flute', 'musical instrument', 'classical music'], "emoji": "🎻"},
    "painting_art": {"keywords": ['painting', 'sculpture', 'madhubani painting', 'warli painting', 'mural art'], "emoji": "🎨"},
    "mythology": {"keywords": ['mythology', 'ramayana', 'mahabharata', 'puranas', 'epic'], "emoji": "📖"},
    "environment_conservation": {"keywords": ['conservation', 'biodiversity', 'deforestation', 'wildlife protection', 'endangered species'], "emoji": "🌿"},
    "special_days": {"keywords": ['teachers day', "women's day", 'environment day', 'yoga day', 'human rights day', 'gandhi jayanti', "children's day", 'world health day'], "emoji": "📅"},
    "scientist_cv_raman": {"keywords": ['cv raman', 'raman effect'], "emoji": "🔬"},
    "scientist_apj_kalam": {"keywords": ['apj abdul kalam', 'missile man of india', 'kalam'], "emoji": "🚀"},
    "scientist_homi_bhabha": {"keywords": ['homi bhabha', 'father of indian nuclear program'], "emoji": "⚛️"},
    "scientist_einstein": {"keywords": ['albert einstein', 'theory of relativity'], "emoji": "🧠"},
    "scientist_newton": {"keywords": ['isaac newton', 'law of gravitation'], "emoji": "🍎"},
    "scientist_darwin": {"keywords": ['charles darwin', 'theory of evolution'], "emoji": "🧬"},
    "invention_discovery": {"keywords": ['invention', 'discovery', 'inventor', 'patent'], "emoji": "💡"},
    "current_affairs": {"keywords": ['current affairs', 'recently launched', 'latest scheme', '2025', '2026'], "emoji": "🗞️"},
    "book_author": {"keywords": ['book written by', 'autobiography', 'bestseller book'], "emoji": "📗"},
    "wonder_of_world": {"keywords": ['wonder of the world', 'seven wonders', 'great pyramid'], "emoji": "🗿"},
    "yoga_ayurveda": {"keywords": ['yoga', 'ayurveda', 'pranayama', 'meditation'], "emoji": "🧘"},
    "indian_railways": {"keywords": ['indian railways', 'railway budget', 'metro rail'], "emoji": "🚆"},
    "agriculture_schemes": {"keywords": ['pm kisan', 'krishi yojana', 'soil health card', 'food security'], "emoji": "🌾"},
    "health_schemes": {"keywords": ['ayushman bharat', 'national health mission', 'immunisation programme'], "emoji": "🏥"},
    "education_policy": {"keywords": ['national education policy', 'right to education', 'midday meal scheme'], "emoji": "🎓"},
    "women_empowerment": {"keywords": ['beti bachao beti padhao', 'women empowerment scheme', 'gender equality'], "emoji": "👩"},
    "disaster_management": {"keywords": ['disaster management', 'flood relief', 'cyclone warning'], "emoji": "🌪️"},
    "smart_city": {"keywords": ['smart city mission', 'urban development', 'swachh bharat'], "emoji": "🏙️"},
    "digital_india": {"keywords": ['digital india', 'aadhaar', 'unified payments interface', 'upi'], "emoji": "📲"},
    "mythological_epics": {"keywords": ['ramayan', 'krishna leela', 'shiv purana', 'bhagavad gita', 'vedic scriptures'], "emoji": "📖"},
    "indian_cuisine": {"keywords": ['indian cuisine', 'traditional food', 'spices of india', 'regional dishes'], "emoji": "🍛"},
    "indian_festivals": {"keywords": ['diwali', 'holi', 'eid', 'christmas', 'pongal', 'onam', 'navratri', 'durga puja'], "emoji": "🎇"},
    "state_andhra_pradesh": {"keywords": ['andhra pradesh', 'amaravati'], "emoji": "📍"},
    "british_colonial_rule": {"keywords": ['viceroy', 'governor general', 'east india company', 'charter act', 'british india', 'colonial rule', 'regulating act'], "emoji": "🎩"},
    "reservation_policy": {"keywords": ['scheduled castes', 'scheduled tribes', 'other backward classes', 'obc reservation', 'reservation policy'], "emoji": "🤝"},
    "cag_audit": {"keywords": ['cag', 'comptroller and auditor general'], "emoji": "📊"},
    "cbi_investigation": {"keywords": ['cbi', 'central bureau of investigation', 'enforcement directorate'], "emoji": "🕵️"},
    "money_bill": {"keywords": ['money bill', 'finance bill', 'consolidated fund', 'finance commission'], "emoji": "💵"},
    "state_legislature": {"keywords": ['legislative assembly', 'legislative council', 'vidhan sabha', 'vidhan parishad'], "emoji": "🏛️"},
    "cng_fuel": {"keywords": ['cng', 'compressed natural gas', 'png fuel', 'lpg cylinder'], "emoji": "⛽"},
    "carbon_emission": {"keywords": ['carbon dioxide', 'carbon emission', 'carbon footprint', 'greenhouse gas', 'methane emission'], "emoji": "🌫️"},
    "mathematics_reasoning": {"keywords": ['profit and loss', 'speed and distance', 'probability', 'percentage problem', 'ratio and proportion', 'number series', 'logical reasoning', 'coding decoding', 'time and work', 'simple interest', 'compound interest'], "emoji": "🧮"},
    "geometry_shapes": {"keywords": ['circle geometry', 'square shape', 'triangle shape', 'cube volume', 'sphere volume', 'cylinder volume', 'pyramid shape', 'perimeter of', 'area of', 'mensuration'], "emoji": "📐"},
    "ants_insects": {"keywords": ['ants', 'ant colony', 'termites'], "emoji": "🐜"},
    "honeybees": {"keywords": ['honeybee', 'honey bee', 'bee colony', 'pollination'], "emoji": "🐝"},
    "amazon_rainforest": {"keywords": ['amazon rainforest', 'amazon river', 'amazon basin', 'tropical rainforest'], "emoji": "🌳"},
    "antarctica_arctic": {"keywords": ['antarctica', 'arctic circle', 'south pole', 'north pole', 'polar region', 'polar bear'], "emoji": "❄️"},
    "tardigrades": {"keywords": ['tardigrades', 'water bear'], "emoji": "🔬"},
    "fennec_fox": {"keywords": ['fennec fox'], "emoji": "🦊"},
    "eucalyptus": {"keywords": ['eucalyptus tree'], "emoji": "🌿"},
    "planet_mercury": {"keywords": ['mercury planet', 'planet mercury'], "emoji": "🪐"},
    "planet_jupiter": {"keywords": ['jupiter planet', 'planet jupiter', 'gas giant planet'], "emoji": "🪐"},
    "planet_venus": {"keywords": ['venus planet', 'planet venus'], "emoji": "🪐"},
    "cataracts_eye": {"keywords": ['cataract', 'cataracts eye', 'human eye disease'], "emoji": "👁️"},
    "heart_organ": {"keywords": ['human heart', 'heart valve', 'cardiac', 'blood circulation'], "emoji": "❤️"},
    "kangaroo": {"keywords": ['kangaroo', 'marsupial'], "emoji": "🦘"},
    "orchids": {"keywords": ['orchid flower', 'orchids'], "emoji": "🌺"},
    "octopus": {"keywords": ['octopus', 'octopuses'], "emoji": "🐙"},
    "lemmings": {"keywords": ['lemming', 'lemmings'], "emoji": "🐹"},
    "unesco_heritage_sites": {"keywords": ['unesco world heritage site', 'world heritage site'], "emoji": "🏛️"},
    "mediterranean_region": {"keywords": ['mediterranean sea', 'mediterranean region'], "emoji": "🌊"},

    # ── World Flags (auto-generated, offline, zero assets) ──
    "flag_india": {"keywords": ['republic of india', 'map of india', 'indian subcontinent'], "emoji": "🇮🇳"},
    "flag_usa": {"keywords": ['usa', 'united states', 'america', 'united states of america'], "emoji": "🇺🇸"},
    "flag_uk": {"keywords": ['uk', 'united kingdom', 'britain', 'england', 'great britain'], "emoji": "🇬🇧"},
    "flag_china": {"keywords": ['china', 'peoples republic of china'], "emoji": "🇨🇳"},
    "flag_russia": {"keywords": ['russia', 'russian federation'], "emoji": "🇷🇺"},
    "flag_japan": {"keywords": ['japan'], "emoji": "🇯🇵"},
    "flag_germany": {"keywords": ['germany'], "emoji": "🇩🇪"},
    "flag_france": {"keywords": ['france'], "emoji": "🇫🇷"},
    "flag_italy": {"keywords": ['italy'], "emoji": "🇮🇹"},
    "flag_spain": {"keywords": ['spain'], "emoji": "🇪🇸"},
    "flag_canada": {"keywords": ['canada'], "emoji": "🇨🇦"},
    "flag_australia": {"keywords": ['australia'], "emoji": "🇦🇺"},
    "flag_brazil": {"keywords": ['brazil'], "emoji": "🇧🇷"},
    "flag_south_africa": {"keywords": ['south africa'], "emoji": "🇿🇦"},
    "flag_nigeria": {"keywords": ['nigeria'], "emoji": "🇳🇬"},
    "flag_egypt": {"keywords": ['egypt'], "emoji": "🇪🇬"},
    "flag_saudi_arabia": {"keywords": ['saudi arabia'], "emoji": "🇸🇦"},
    "flag_uae": {"keywords": ['uae', 'united arab emirates', 'dubai country'], "emoji": "🇦🇪"},
    "flag_pakistan": {"keywords": ['pakistan'], "emoji": "🇵🇰"},
    "flag_bangladesh": {"keywords": ['bangladesh'], "emoji": "🇧🇩"},
    "flag_sri_lanka": {"keywords": ['sri lanka', 'ceylon'], "emoji": "🇱🇰"},
    "flag_nepal": {"keywords": ['nepal'], "emoji": "🇳🇵"},
    "flag_bhutan": {"keywords": ['bhutan'], "emoji": "🇧🇹"},
    "flag_afghanistan": {"keywords": ['afghanistan'], "emoji": "🇦🇫"},
    "flag_iran": {"keywords": ['iran', 'persia'], "emoji": "🇮🇷"},
    "flag_iraq": {"keywords": ['iraq'], "emoji": "🇮🇶"},
    "flag_israel": {"keywords": ['israel'], "emoji": "🇮🇱"},
    "flag_turkey": {"keywords": ['turkey', 'turkiye'], "emoji": "🇹🇷"},
    "flag_greece": {"keywords": ['greece'], "emoji": "🇬🇷"},
    "flag_portugal": {"keywords": ['portugal'], "emoji": "🇵🇹"},
    "flag_netherlands": {"keywords": ['netherlands', 'holland'], "emoji": "🇳🇱"},
    "flag_belgium": {"keywords": ['belgium'], "emoji": "🇧🇪"},
    "flag_switzerland": {"keywords": ['switzerland'], "emoji": "🇨🇭"},
    "flag_sweden": {"keywords": ['sweden'], "emoji": "🇸🇪"},
    "flag_norway": {"keywords": ['norway'], "emoji": "🇳🇴"},
    "flag_denmark": {"keywords": ['denmark'], "emoji": "🇩🇰"},
    "flag_finland": {"keywords": ['finland'], "emoji": "🇫🇮"},
    "flag_poland": {"keywords": ['poland'], "emoji": "🇵🇱"},
    "flag_ukraine": {"keywords": ['ukraine'], "emoji": "🇺🇦"},
    "flag_austria": {"keywords": ['austria'], "emoji": "🇦🇹"},
    "flag_ireland": {"keywords": ['ireland'], "emoji": "🇮🇪"},
    "flag_mexico": {"keywords": ['mexico'], "emoji": "🇲🇽"},
    "flag_argentina": {"keywords": ['argentina'], "emoji": "🇦🇷"},
    "flag_chile": {"keywords": ['chile'], "emoji": "🇨🇱"},
    "flag_colombia": {"keywords": ['colombia'], "emoji": "🇨🇴"},
    "flag_peru": {"keywords": ['peru'], "emoji": "🇵🇪"},
    "flag_venezuela": {"keywords": ['venezuela'], "emoji": "🇻🇪"},
    "flag_indonesia": {"keywords": ['indonesia'], "emoji": "🇮🇩"},
    "flag_malaysia": {"keywords": ['malaysia'], "emoji": "🇲🇾"},
    "flag_singapore": {"keywords": ['singapore'], "emoji": "🇸🇬"},
    "flag_thailand": {"keywords": ['thailand'], "emoji": "🇹🇭"},
    "flag_vietnam": {"keywords": ['vietnam'], "emoji": "🇻🇳"},
    "flag_philippines": {"keywords": ['philippines'], "emoji": "🇵🇭"},
    "flag_south_korea": {"keywords": ['south korea'], "emoji": "🇰🇷"},
    "flag_north_korea": {"keywords": ['north korea'], "emoji": "🇰🇵"},
    "flag_new_zealand": {"keywords": ['new zealand'], "emoji": "🇳🇿"},
    "flag_kenya": {"keywords": ['kenya'], "emoji": "🇰🇪"},
    "flag_ethiopia": {"keywords": ['ethiopia'], "emoji": "🇪🇹"},
    "flag_ghana": {"keywords": ['ghana'], "emoji": "🇬🇭"},
    "flag_morocco": {"keywords": ['morocco'], "emoji": "🇲🇦"},
    "flag_algeria": {"keywords": ['algeria'], "emoji": "🇩🇿"},
    "flag_libya": {"keywords": ['libya'], "emoji": "🇱🇾"},
    "flag_sudan": {"keywords": ['sudan'], "emoji": "🇸🇩"},
    "flag_qatar": {"keywords": ['qatar'], "emoji": "🇶🇦"},
    "flag_kuwait": {"keywords": ['kuwait'], "emoji": "🇰🇼"},
    "flag_bahrain": {"keywords": ['bahrain'], "emoji": "🇧🇭"},
    "flag_oman": {"keywords": ['oman'], "emoji": "🇴🇲"},
    "flag_yemen": {"keywords": ['yemen'], "emoji": "🇾🇪"},
    "flag_jordan": {"keywords": ['jordan'], "emoji": "🇯🇴"},
    "flag_lebanon": {"keywords": ['lebanon'], "emoji": "🇱🇧"},
    "flag_syria": {"keywords": ['syria'], "emoji": "🇸🇾"},
    "flag_cuba": {"keywords": ['cuba'], "emoji": "🇨🇺"},
    "flag_jamaica": {"keywords": ['jamaica'], "emoji": "🇯🇲"},
    "flag_mongolia": {"keywords": ['mongolia'], "emoji": "🇲🇳"},
    "flag_kazakhstan": {"keywords": ['kazakhstan'], "emoji": "🇰🇿"},
    "flag_uzbekistan": {"keywords": ['uzbekistan'], "emoji": "🇺🇿"},
    "flag_myanmar": {"keywords": ['myanmar', 'burma'], "emoji": "🇲🇲"},
    "flag_cambodia": {"keywords": ['cambodia'], "emoji": "🇰🇭"},
    "flag_laos": {"keywords": ['laos'], "emoji": "🇱🇦"},
    "flag_hungary": {"keywords": ['hungary'], "emoji": "🇭🇺"},
    "flag_czech_republic": {"keywords": ['czech republic', 'czechia'], "emoji": "🇨🇿"},
    "flag_romania": {"keywords": ['romania'], "emoji": "🇷🇴"},
    "flag_bulgaria": {"keywords": ['bulgaria'], "emoji": "🇧🇬"},
    "flag_serbia": {"keywords": ['serbia'], "emoji": "🇷🇸"},
    "flag_croatia": {"keywords": ['croatia'], "emoji": "🇭🇷"},
    "flag_iceland": {"keywords": ['iceland'], "emoji": "🇮🇸"},
    "flag_tanzania": {"keywords": ['tanzania'], "emoji": "🇹🇿"},
    "flag_uganda": {"keywords": ['uganda'], "emoji": "🇺🇬"},
    "flag_zimbabwe": {"keywords": ['zimbabwe'], "emoji": "🇿🇼"},
    "flag_zambia": {"keywords": ['zambia'], "emoji": "🇿🇲"},
    "flag_tunisia": {"keywords": ['tunisia'], "emoji": "🇹🇳"},
}

# ─── OFFLINE STICKER ENGINE (keyword → sticker, zero network/API calls) ───────
# Matches question text against STICKER_MAP and draws a relevant emoji/PNG
# sticker in whatever empty space is left in the card. Runs in microseconds,
# adds no measurable time to render or FFmpeg encode. Works for every
# resolution/orientation (shorts, landscape, square) since it plugs into the
# same _render_mcq function used everywhere.

import functools as _sticker_functools
import re as _sticker_re

STICKER_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "assets", "stickers")  # optional PNG overrides


class _StickerMatcher:
    def __init__(self, sticker_map):
        self.sticker_map = sticker_map
        self._entries = []  # (compiled_regex, sid)
        for sid, entry in sticker_map.items():
            kws = entry.get("keywords", [])
            if not kws:
                continue
            kws_sorted = sorted(kws, key=len, reverse=True)
            # \b...\b word-boundary wrapping is critical: without it, short
            # keywords like "eci" or "pm" would false-match inside unrelated
            # words (e.g. "specific" contains "eci"). This keeps matching
            # both fast (single compiled regex) AND accurate.
            alts = "|".join(_sticker_re.escape(k.strip()) for k in kws_sorted)
            pattern = r"\b(?:" + alts + r")\b"
            self._entries.append((_sticker_re.compile(pattern, _sticker_re.IGNORECASE), sid))

    def match(self, text):
        """Tries every entry and returns the sid whose ACTUAL matched text
        is longest (most specific), not the sid that merely happens to
        declare the longest keyword somewhere in its list. This matters a
        lot for GK quizzes: almost every question mentions "India" or
        similar broad words, so without ranking by the real matched span,
        a generic word would constantly drown out specific topic matches
        like "Narmada River" or a particular award/act name.
        """
        t = f" {text.lower()} "
        best_sid, best_len = None, 0
        for regex, sid in self._entries:
            m = regex.search(t)
            if m:
                span_len = m.end() - m.start()
                if span_len > best_len:
                    best_sid, best_len = sid, span_len
        return best_sid


_STICKER_MATCHER = _StickerMatcher(STICKER_MAP)  # built once at import time


# ─── Layer B: pattern-based fallback (guarantees nothing is ever "missed") ──
# If a question mentions some proper noun that isn't in STICKER_MAP (a river,
# scheme, award, act... we've never seen before), these suffix/context rules
# still assign a sensible category icon. Runs only when Layer A finds no
# exact match, so it costs nothing extra in the common case. Matched against
# the ORIGINAL-case text so "Capitalised Word + suffix" reads as a proper
# noun (e.g. "Kaveri River", "Ashoka Award", "Bhima Koregaon Battle").
_FALLBACK_RULES = [
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+Rivers?\b", "🏞️"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+Lakes?\b", "🏞️"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+(?:Mountains?|Peaks?|Range)\b", "⛰️"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+Desert\b", "🏜️"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+(?:Ocean|Sea|Gulf|Bay|Strait)\b", "🌊"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+Volcano\b", "🌋"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+Islands?\b", "🏝️"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+(?:Fort|Palace|Mahal)\b", "🏰"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+(?:Temple|Mandir)\b", "🛕"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+(?:Mosque|Masjid)\b", "🕌"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+(?:Church|Cathedral)\b", "⛪"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+(?:University|Institute|College)\b", "🎓"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+Bank\b", "🏦"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+(?:Commission|Council|Committee|Board|Tribunal)\b", "📋"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+(?:Ministry|Department)\b", "🏢"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+(?:Scheme|Yojana|Mission|Programme|Program|Policy)\b", "📋"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+Day\b", "📅"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+(?:Award|Prize|Medal)\b", "🏅"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+(?:War|Battle|Revolt|Rebellion|Mutiny)\b", "⚔️"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+(?:Company|Corporation)\b", "🏢"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+(?:Satellite|Rocket|Spacecraft)\b", "🛰️"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+(?:Virus|Disease|Syndrome)\b", "🦠"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+Vaccine\b", "💉"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+Court\b", "⚖️"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+Party\b", "🎌"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+(?:Election|Poll)\b", "🗳️"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+(?:Act|Amendment|Article|Bill|Ordinance)\b", "📜"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+(?:Treaty|Agreement|Pact|Accord)\b", "🤝"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+Airport\b", "✈️"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+(?:Railway|Station)\b", "🚆"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+Stadium\b", "🏟️"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+Species\b", "🐾"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+Bird\b", "🐦"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+Flowers?\b", "🌸"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+(?:Tree|Plant)\b", "🌳"),
    (r"[A-Z][\w']+(?:\s+[A-Z][\w']+)*\s+Planet\b", "🪐"),
]
_FALLBACK_COMPILED = [(_sticker_re.compile(p), emo) for p, emo in _FALLBACK_RULES]


def _fallback_match(original_text):
    for regex, emo in _FALLBACK_COMPILED:
        if regex.search(original_text):
            return emo
    return None


@_sticker_functools.lru_cache(maxsize=256)
def _load_png_sticker(rel_path, size):
    full = os.path.join(STICKER_ASSETS_DIR, rel_path)
    if not os.path.exists(full):
        return None
    img = Image.open(full).convert("RGBA")
    img.thumbnail((size, size), Image.LANCZOS)
    return img


_HI_STICKERS = [
    ("\u0930\u093e\u0937\u094d\u091f\u094d\u0930\u092a\u0924\u093f", "\U0001f3db\ufe0f"),   # rashtrapati
    ("\u092a\u094d\u0930\u0927\u093e\u0928\u092e\u0902\u0924\u094d\u0930\u0940", "\U0001f399\ufe0f"),
    ("\u0938\u0902\u0935\u093f\u0927\u093e\u0928", "\U0001f4dc"),
    ("\u0938\u0902\u0938\u0926", "\U0001f3db\ufe0f"), ("\u0932\u094b\u0915\u0938\u092d\u093e", "\U0001f3db\ufe0f"),
    ("\u0930\u093e\u091c\u094d\u092f\u0938\u092d\u093e", "\U0001f3db\ufe0f"),
    ("\u0928\u094d\u092f\u093e\u092f\u093e\u0932\u092f", "\u2696\ufe0f"),
    ("\u091a\u0941\u0928\u093e\u0935", "\U0001f5f3\ufe0f"), ("\u0928\u093f\u0930\u094d\u0935\u093e\u091a\u0928", "\U0001f5f3\ufe0f"),
    ("\u0930\u093e\u091c\u094d\u092f\u092a\u093e\u0932", "\U0001f3e2"), ("\u092e\u0941\u0916\u094d\u092f\u092e\u0902\u0924\u094d\u0930\u0940", "\U0001f3e2"),
    ("\u092a\u0902\u091a\u093e\u092f\u0924", "\U0001f3d8\ufe0f"),
    ("\u091c\u092f\u092a\u0941\u0930", "\U0001f3f0"), ("\u0915\u093f\u0932\u093e", "\U0001f3f0"), ("\u0926\u0941\u0930\u094d\u0917", "\U0001f3f0"),
    ("\u0930\u093e\u091c\u0938\u094d\u0925\u093e\u0928", "\U0001f3dc\ufe0f"), ("\u092e\u0930\u0941\u0938\u094d\u0925\u0932", "\U0001f3dc\ufe0f"),
    ("\u092e\u0902\u0926\u093f\u0930", "\U0001f6d5"), ("\u092e\u0938\u094d\u091c\u093f\u0926", "\U0001f54c"),
    ("\u0928\u0926\u0940", "\U0001f3de\ufe0f"), ("\u091d\u0940\u0932", "\U0001f3de\ufe0f"),
    ("\u092a\u0930\u094d\u0935\u0924", "\u26f0\ufe0f"), ("\u092a\u0939\u093e\u0921\u093c", "\u26f0\ufe0f"),
    ("\u091c\u0902\u0917\u0932", "\U0001f333"), ("\u0905\u092d\u092f\u093e\u0930\u0923\u094d\u092f", "\U0001f333"),
    ("\u0915\u0943\u0937\u093f", "\U0001f33e"), ("\u092b\u0938\u0932", "\U0001f33e"), ("\u0915\u093f\u0938\u093e\u0928", "\U0001f33e"),
    ("\u0909\u0926\u094d\u092f\u094b\u0917", "\U0001f3ed"), ("\u092c\u0948\u0902\u0915", "\U0001f3e6"),
    ("\u092c\u091c\u091f", "\U0001f4b0"), ("\u0905\u0930\u094d\u0925\u0935\u094d\u092f\u0935\u0938\u094d\u0925\u093e", "\U0001f4b9"),
    ("GSVA", "\U0001f4c8"), ("GDP", "\U0001f4c8"),
    ("\u092a\u0930\u094d\u092f\u091f\u0928", "\U0001f9f3"), ("\u092a\u0941\u0930\u0938\u094d\u0915\u093e\u0930", "\U0001f3c5"),
    ("\u0916\u0947\u0932", "\U0001f3c6"), ("\u0915\u094d\u0930\u093f\u0915\u0947\u091f", "\U0001f3cf"),
    ("\u0935\u093f\u091c\u094d\u091e\u093e\u0928", "\U0001f52c"), ("\u0907\u0924\u093f\u0939\u093e\u0938", "\U0001f4dc"),
    ("\u092f\u0941\u0926\u094d\u0927", "\u2694\ufe0f"), ("\u0938\u094d\u0935\u0924\u0902\u0924\u094d\u0930\u0924\u093e", "\u270a"),
    ("\u092f\u094b\u091c\u0928\u093e", "\U0001f4cb"), ("\u0936\u093f\u0915\u094d\u0937\u093e", "\U0001f393"),
    ("\u0938\u094d\u0935\u093e\u0938\u094d\u0925\u094d\u092f", "\U0001f3e5"),
    ("\u091c\u0928\u0938\u0902\u0916\u094d\u092f\u093e", "\U0001f465"), ("\u091c\u0928\u0917\u0923\u0928\u093e", "\U0001f465"),
    ("\u091c\u0932\u0935\u093e\u092f\u0941", "\U0001f326\ufe0f"), ("\u092c\u093f\u091c\u0932\u0940", "\u26a1"),
    ("\u0909\u092a\u0917\u094d\u0930\u0939", "\U0001f6f0\ufe0f"), ("\u0907\u0938\u0930\u094b", "\U0001f6f0\ufe0f"),
]


def get_sticker_for_text(text):
    """Returns ('emoji', glyph) or ('png', rel_path) or None.
    Layer A: exact curated dictionary (best, most specific icon).
    Layer B: suffix/pattern fallback — catches any proper noun category
    (river, university, award, act...) that isn't in the dictionary yet,
    so a relevant question essentially never comes up empty.
    """
    if _DEVA_RE.search(text):
        for _k, _e in _HI_STICKERS:
            if _k in text:
                return ("emoji", _e)
    sid = _STICKER_MATCHER.match(text)
    if sid:
        entry = STICKER_MAP[sid]
        png_rel = entry.get("png")
        if png_rel and os.path.exists(os.path.join(STICKER_ASSETS_DIR, png_rel)):
            return ("png", png_rel)
        if entry.get("emoji"):
            return ("emoji", entry["emoji"])

    fallback_emoji = _fallback_match(text)
    if fallback_emoji:
        return ("emoji", fallback_emoji)

    return None


def place_sticker(img_rgba, draw, box, text, theme=None, max_size=110):
    """
    box = (x1, y1, x2, y2) — leftover empty space already computed by the
    caller. Draws a glowing circular "badge" (shadow + rim light + glossy
    highlight) behind the emoji so it reads as a polished 3D sticker rather
    than flat text — built entirely with Pillow drawing, no downloaded
    image assets, so there's no copyright/licensing risk.
    Skips cleanly (does nothing) if there's no room or no keyword match.
    """
    x1, y1, x2, y2 = box
    box_w, box_h = x2 - x1, y2 - y1
    if box_w < 50 or box_h < 50:
        return False

    hit = get_sticker_for_text(text)
    if not hit:
        return False
    kind, payload = hit

    # Reserve room for the glowing "badge" backdrop around the sticker so it
    # reads as a polished 3D chip instead of a flat emoji floating in space.
    badge_d = int(min(max_size + 30, box_w * 0.95, box_h * 0.95))
    if badge_d < 60:
        return False
    icon_size = int(badge_d * 0.62)

    # Pre-load/validate the sticker content BEFORE drawing anything, so a
    # missing PNG file never leaves a half-drawn empty badge behind.
    sticker_img = None
    if kind == "png":
        sticker_img = _load_png_sticker(payload, icon_size)
        if sticker_img is None:
            return False

    cx, cy = x1 + box_w // 2, y1 + box_h // 2
    r = badge_d // 2

    if theme is not None:
        accent_rgb = _rgb(theme.get('accent', theme.get('border', '#5B8CFF')))
        glow_rgb   = _rgb(theme.get('glow', theme.get('border', '#5B8CFF')))
        card_rgb   = _rgb(theme.get('card', '#141A2A'))
        shadow_rgb = _darken(_rgb(theme.get('bg', '#0B0F19')), 25)
    else:
        accent_rgb = (91, 140, 255); glow_rgb = (91, 140, 255)
        card_rgb   = (20, 26, 42);   shadow_rgb = (5, 7, 12)

    # 1) drop shadow (offset down-right) — gives the badge lift/depth
    draw.ellipse([cx - r + 4, cy - r + 6, cx + r + 4, cy + r + 6],
                 fill=(*shadow_rgb, 150))
    # 2) soft glow halo behind the badge (matches card theme)
    _draw_glow_ellipse(img_rgba, cx, cy, r + 6, glow_rgb, intensity=0.75, blur_r=16)
    # 3) base circle fill
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*card_rgb, 235))
    # 4) rim light border in accent colour
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(*accent_rgb, 255), width=3)
    # 5) glossy highlight (upper-left) — fakes a rounded 3D sticker surface
    hl_r = int(r * 0.62)
    hl_cx, hl_cy = cx - int(r * 0.32), cy - int(r * 0.38)
    highlight = Image.new('RGBA', (hl_r * 2, hl_r * 2), (0, 0, 0, 0))
    hdraw = ImageDraw.Draw(highlight)
    hdraw.ellipse([0, 0, hl_r * 2, hl_r * 2], fill=(255, 255, 255, 55))
    img_rgba.alpha_composite(highlight, (hl_cx - hl_r, hl_cy - hl_r))

    if kind == "png":
        px = cx - sticker_img.width // 2
        py = cy - sticker_img.height // 2
        img_rgba.alpha_composite(sticker_img, (px, py))
        return True

    # kind == "emoji"
    _eimg = _emoji_image(payload, icon_size)
    if _eimg is not None:
        img_rgba.alpha_composite(_eimg, (cx - _eimg.width // 2, cy - _eimg.height // 2))
        return True
    font = _load_emoji_font(icon_size)
    try:
        bbox = draw.textbbox((0, 0), payload, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        ox, oy_ = bbox[0], bbox[1]
    except Exception:
        tw, th, ox, oy_ = icon_size, icon_size, 0, 0
    try:
        draw.text((cx - tw // 2 - ox, cy - th // 2 - oy_), payload, font=font,
                  embedded_color=True)
    except TypeError:
        draw.text((cx - tw // 2 - ox, cy - th // 2 - oy_), payload, font=font)
    return True




# ─── Text Utilities ───────────────────────────────────────────────────────────
def _tw(draw, text, font):
    if isinstance(font, _HBFont):
        return font.width(text)
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0]


def _th(draw, text, font):
    if isinstance(font, _HBFont):
        b = font.bbox(text)
        return b[3] - b[1]
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[3] - bb[1]


def _dt(draw, xy, text, font, fill, ink=False):
    """draw.text() that also works with the HarfBuzz Hindi font.
    ink=True (Hindi font only): y is the top of the visible ink, so centring maths is exact."""
    if isinstance(font, _HBFont):
        font.draw(draw, xy, text, fill, ink=ink)
    else:
        draw.text(xy, text, font=font, fill=fill)


def _line_h(sz):
    if getattr(_TL, 'lang', 'en') == 'hi':
        return int(sz * 1.42) + 4          # Devanagari needs room for matras above / below
    return sz + max(8, sz // 5)


def _split_long_word(draw, word, font, max_w):
    """Break a single over-long 'word' without separating a letter from its matra."""
    parts, cur = [], ''
    for ch in word:
        glued = (unicodedata.category(ch) in ('Mn', 'Mc') or ch in '\u200c\u200d'
                 or (cur and cur[-1] == '\u094d'))
        if cur and not glued and _tw(draw, cur + ch, font) > max_w:
            parts.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        parts.append(cur)
    return parts or [word]


def _wrap(draw, text, font, max_w):
    words = text.split()
    if not words:
        return [""]
    lines, cur = [], []
    for word in words:
        if _tw(draw, word, font) > max_w:
            if cur:
                lines.append(' '.join(cur))
                cur = []
            pieces = _split_long_word(draw, word, font, max_w)
            lines.extend(pieces[:-1])
            cur = [pieces[-1]]
            continue
        test = ' '.join(cur + [word])
        if _tw(draw, test, font) <= max_w:
            cur.append(word)
        else:
            if cur:
                lines.append(' '.join(cur))
            cur = [word]
    if cur:
        lines.append(' '.join(cur))
    return lines or [""]


def _fit_text(draw, text, max_w, max_h, size_max, size_min, bold=True, heavy=False):
    text = text.strip() or " "
    step = 2
    for sz in range(size_max, size_min - 1, -step):
        font = _load_font(sz, bold=bold, heavy=heavy)
        lh   = _line_h(sz)
        lines = _wrap(draw, text, font, max_w)
        if len(lines) * lh <= max_h:
            return font, lines, lh
    font = _load_font(size_min, bold=bold, heavy=heavy)
    lh   = _line_h(size_min)
    lines = _wrap(draw, text, font, max_w)
    return font, lines, lh


def _draw_text_block(draw, lines, font, lh, cx, y, fill, align='center', max_w=None):
    for line in lines:
        w = _tw(draw, line, font)
        if align == 'center':
            x = cx - w // 2
            if max_w is not None:
                x = max(cx - max_w // 2, x)
            _dt(draw, (x, y), line, font, fill)
        else:
            _dt(draw, (cx, y), line, font, fill)
        y += lh
    return y


# ─── Glow Drawing Engine ─────────────────────────────────────────────────────
def _draw_glow_rect(img_rgba, x1, y1, x2, y2, glow_rgb, intensity=0.85,
                    blur_r=14, corner_r=28):
    """Soft glowing halo around a rounded rectangle (works only on the card's
    neighbourhood, not the whole canvas - identical look, far faster)."""
    try:
        pad = 2 * blur_r + 8
        bx1 = max(0, int(x1) - pad);  by1 = max(0, int(y1) - pad)
        bx2 = min(img_rgba.width,  int(x2) + pad + 1)
        by2 = min(img_rgba.height, int(y2) + pad + 1)
        if bx2 <= bx1 or by2 <= by1:
            return
        glow_layer = Image.new('RGBA', (bx2 - bx1, by2 - by1), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow_layer)
        r, g, b = glow_rgb
        lx1, ly1, lx2, ly2 = x1 - bx1, y1 - by1, x2 - bx1, y2 - by1
        for offset in range(blur_r, 0, -1):
            a = int(intensity * 220 * (offset / blur_r) ** 0.6)
            a = min(200, a)
            color = (r, g, b, a)
            expand = offset
            try:
                gd.rounded_rectangle(
                    [lx1 - expand, ly1 - expand, lx2 + expand, ly2 + expand],
                    radius=max(1, corner_r + expand // 2),
                    outline=color, width=2
                )
            except (AttributeError, TypeError):
                gd.rectangle(
                    [lx1 - expand, ly1 - expand, lx2 + expand, ly2 + expand],
                    outline=color, width=2
                )
        blurred = glow_layer.filter(ImageFilter.GaussianBlur(radius=blur_r // 3))
        img_rgba.alpha_composite(blurred, dest=(bx1, by1))
    except Exception:
        pass  # Graceful fallback — no glow


def _draw_glow_ellipse(img_rgba, cx, cy, r, glow_rgb, intensity=0.85, blur_r=12):
    """Glowing halo around a circle (cropped to the circle's neighbourhood)."""
    try:
        pad = 2 * blur_r + 8
        ext = int(r) + blur_r + pad
        bx1 = max(0, int(cx) - ext);  by1 = max(0, int(cy) - ext)
        bx2 = min(img_rgba.width,  int(cx) + ext + 1)
        by2 = min(img_rgba.height, int(cy) + ext + 1)
        if bx2 <= bx1 or by2 <= by1:
            return
        glow_layer = Image.new('RGBA', (bx2 - bx1, by2 - by1), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow_layer)
        rv, gv, bv = glow_rgb
        lcx, lcy = cx - bx1, cy - by1
        for offset in range(blur_r, 0, -1):
            a = int(intensity * 200 * (offset / blur_r) ** 0.7)
            a = min(200, a)
            color = (rv, gv, bv, a)
            ex = offset
            gd.ellipse([lcx - r - ex, lcy - r - ex, lcx + r + ex, lcy + r + ex],
                       outline=color, width=2)
        blurred = glow_layer.filter(ImageFilter.GaussianBlur(radius=blur_r // 3))
        img_rgba.alpha_composite(blurred, dest=(bx1, by1))
    except Exception:
        pass


# ─── Gradient Background Maker ────────────────────────────────────────────────
_DOT_CACHE = {}


def _make_gradient_bg(W, H, theme, glow_phase=0.0):
    """Create gradient background + dot grid. Returns RGB image."""
    _solid = getattr(_TL, 'solid_bg', None)
    if _solid is not None:                      # video-bg mode: flat canvas, no gradient/dots
        return Image.new('RGBA', (W, H), (*_solid, 255))
    bg1 = _rgb(theme['bg'])
    bg2 = _rgb(theme.get('bg2', theme['bg']))
    gradient = theme.get('gradient', 'solid')
    glow_intensity = theme.get('glow_intensity', 0.85)
    # Breathing phase modulates bg2 slightly
    breath = 0.85 + 0.15 * (math.sin(glow_phase) * 0.5 + 0.5)

    if HAS_NUMPY:
        bg1a = np.array(bg1, dtype=np.float32)
        bg2a = np.array(bg2, dtype=np.float32) * breath

        if gradient == 'vertical':
            t = np.linspace(0, 1, H, dtype=np.float32).reshape(-1, 1, 1)
            rgb = np.clip((1 - t) * bg1a + t * bg2a, 0, 255).astype(np.uint8)
            rgb = np.broadcast_to(rgb, (H, W, 3)).copy()

        elif gradient == 'radial':
            cx_f, cy_f = W / 2.0, H / 2.0
            y_arr, x_arr = np.mgrid[0:H, 0:W]
            r_arr = np.sqrt((x_arr - cx_f) ** 2 + (y_arr - cy_f) ** 2)
            max_r = math.sqrt(cx_f ** 2 + cy_f ** 2)
            t = np.clip(r_arr / max_r, 0, 1).reshape(H, W, 1).astype(np.float32)
            rgb = np.clip((1 - t) * bg1a + t * bg2a, 0, 255).astype(np.uint8)

        elif gradient == 'diagonal':
            x_t = np.linspace(0, 1, W, dtype=np.float32).reshape(1, W, 1)
            y_t = np.linspace(0, 1, H, dtype=np.float32).reshape(H, 1, 1)
            t = ((x_t + y_t) / 2).astype(np.float32)
            rgb = np.clip((1 - t) * bg1a + t * bg2a, 0, 255).astype(np.uint8)

        else:  # solid
            rgb = np.full((H, W, 3), bg1, dtype=np.uint8)

        img = Image.fromarray(rgb, 'RGB')
    else:
        # Pure-Python fallback: vertical row loop
        img = Image.new('RGB', (W, H), bg1)
        d = ImageDraw.Draw(img)
        for y in range(H):
            t = y / H if H > 1 else 0
            c = tuple(int(bg1[i] * (1 - t) + bg2[i] * t * breath) for i in range(3))
            d.line([(0, y), (W-1, y)], fill=c)

    # Add subtle dot grid overlay (cached - it never changes for a given theme/size)
    img = img.convert('RGBA')
    dot_rgb = _rgb(theme.get('particle', theme['border']))
    dot_a = int(20 * glow_intensity)
    _dk = (W, H, dot_rgb, dot_a)
    ov = _DOT_CACHE.get(_dk)
    if ov is None:
        ov = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(ov)
        dot_c = (*dot_rgb, dot_a)
        spacing = 30
        for gy in range(0, H + spacing, spacing):
            for gx in range(0, W + spacing, spacing):
                odraw.ellipse([gx - 2, gy - 2, gx + 2, gy + 2], fill=dot_c)
        if len(_DOT_CACHE) > 24:
            _DOT_CACHE.clear()
        _DOT_CACHE[_dk] = ov

    result = Image.alpha_composite(img, ov)
    return result.convert('RGBA')  # Keep RGBA for glow compositing


# ─── Drawing Primitives ───────────────────────────────────────────────────────
def _rounded_rect(draw, x1, y1, x2, y2, radius, fill=None, outline=None, width=3):
    if x2 < x1: x1, x2 = x2, x1
    if y2 < y1: y1, y2 = y2, y1
    try:
        draw.rounded_rectangle([x1, y1, x2, y2], radius=radius,
                               fill=fill, outline=outline, width=width)
    except ValueError:
        draw.rectangle([x1, y1, max(x2, x1), max(y2, y1)], fill=fill, outline=outline, width=width)
    except (AttributeError, TypeError):
        draw.rectangle([x1, y1, x2, y2], fill=fill, outline=outline, width=width)


def _draw_card(img_rgba, draw, x, y, x2, y2, theme, accent_border=False,
               radius=28, glow_phase=0.0, extra_glow=False):
    """Draw a premium card with glow on an RGBA image."""
    glow_intensity = theme.get('glow_intensity', 0.85)
    breath = 0.6 + 0.4 * (math.sin(glow_phase) * 0.5 + 0.5)
    effective_glow = glow_intensity * breath

    border_hex = theme['accent'] if accent_border else theme['border']
    glow_hex   = theme.get('glow', theme['border'])
    border_rgb = _rgb(border_hex)
    glow_rgb   = _rgb(glow_hex)
    card_rgb   = _rgb(theme['card'])
    shadow_rgb = _darken(_rgb(theme['bg']), 25)

    # Shadow
    _rounded_rect(draw, x + 5, y + 5, x2 + 5, y2 + 5,
                  radius=radius, fill=(*shadow_rgb, 160))
    # Card fill
    _rounded_rect(draw, x, y, x2, y2,
                  radius=radius, fill=(*card_rgb, 240))
    # Glow halo (breathing)
    blur_r = 18 if extra_glow else 14
    _draw_glow_rect(img_rgba, x, y, x2, y2, glow_rgb,
                    intensity=effective_glow, blur_r=blur_r, corner_r=radius)
    # Crisp border
    _rounded_rect(draw, x, y, x2, y2,
                  radius=radius, outline=(*border_rgb, 255), width=3)


def _draw_badge(img_rgba, draw, W, y, text, theme, is_portrait,
                badge_style='pill', glow_phase=0.0):
    """Draw a premium glowing pill badge. Returns badge bottom y."""
    size   = 26 if is_portrait else 22
    font   = _load_font(size, bold=True, heavy=True)
    tw     = _tw(draw, text, font)
    th     = _th(draw, text, font)
    pad_x  = 40
    pad_y  = 14
    bw     = tw + 2 * pad_x
    bh     = th + 2 * pad_y
    bx     = (W - bw) // 2
    by     = y

    glow_rgb   = _rgb(theme.get('glow', theme['border']))
    badge_bg   = _rgb(theme['badge_bg'])
    badge_fg   = _rgb(theme['badge_fg'])
    glow_intensity = theme.get('glow_intensity', 0.85)
    breath = 0.7 + 0.3 * (math.sin(glow_phase) * 0.5 + 0.5)

    # Glow halo
    _draw_glow_rect(img_rgba, bx, by, bx + bw, by + bh,
                    glow_rgb, intensity=glow_intensity * breath,
                    blur_r=12, corner_r=bh // 2)
    # Shadow
    _rounded_rect(draw, bx + 3, by + 3, bx + bw + 3, by + bh + 3,
                  radius=bh // 2, fill=(*_darken(_rgb(theme['bg']), 30), 160))
    # Fill
    _rounded_rect(draw, bx, by, bx + bw, by + bh,
                  radius=bh // 2, fill=(*badge_bg, 255))
    # Text
    _dt(draw, (bx + pad_x, by + pad_y), text, font, (*badge_fg, 255), ink=True)

    return by + bh


def _draw_footer(img_rgba, draw, W, H, theme, glow_phase=0.0):
    """Draw the premium glowing LIKE SHARE SUBSCRIBE footer."""
    text    = _t('footer')
    fsize   = 28
    font    = _load_font(fsize, bold=True, heavy=True)
    tw      = _tw(draw, text, font)
    pill_w  = tw + 100
    pill_h  = 60
    footer_y = H - 90
    px = (W - pill_w) // 2
    py = footer_y + (90 - pill_h) // 2

    border_rgb = _rgb(theme['border'])
    glow_rgb   = _rgb(theme.get('glow', theme['border']))
    bg_rgb     = _rgb(theme['bg'])
    glow_intensity = theme.get('glow_intensity', 0.85)
    breath = 0.65 + 0.35 * (math.sin(glow_phase + math.pi * 0.3) * 0.5 + 0.5)

    # Glow halo
    _draw_glow_rect(img_rgba, px, py, px + pill_w, py + pill_h,
                    glow_rgb, intensity=glow_intensity * breath,
                    blur_r=16, corner_r=pill_h // 2)
    # Shadow
    _rounded_rect(draw, px + 4, py + 4, px + pill_w + 4, py + pill_h + 4,
                  radius=pill_h // 2, fill=(*_darken(bg_rgb, 30), 160))
    # Pill background
    _rounded_rect(draw, px, py, px + pill_w, py + pill_h,
                  radius=pill_h // 2, fill=(*bg_rgb, 230),
                  outline=(*border_rgb, 255), width=3)
    # Text
    th2 = _th(draw, text, font)
    _dt(draw, (px + 50, py + (pill_h - th2) // 2), text, font, (*border_rgb, 255), ink=True)


def _draw_option_row(img_rgba, draw, x, y, w, h, letter, text, theme,
                     correct=False, is_portrait=True, glow_phase=0.0):
    """Draw one MCQ option row with glow on correct answer."""
    radius = 20
    glow_rgb   = _rgb(theme.get('glow', theme['border']))
    correct_rgb = _rgb(theme['correct'])
    border_dim  = _darken(_rgb(theme['border']), 40)

    if correct:
        fill_c   = _alpha_blend(_rgb(theme['card']), correct_rgb, 0.30)
        border_c = correct_rgb
        # Glow on correct answer
        breath = 0.7 + 0.3 * (math.sin(glow_phase + math.pi) * 0.5 + 0.5)
        _draw_glow_rect(img_rgba, x, y, x + w, y + h, correct_rgb,
                        intensity=0.80 * breath, blur_r=10, corner_r=radius)
    else:
        fill_c   = _rgb(theme['card'])
        border_c = border_dim

    _rounded_rect(draw, x, y, x + w, y + h, radius=radius,
                  fill=(*fill_c, 240), outline=(*border_c, 200), width=3)

    # Letter badge circle
    badge_d  = _sz_half(52 if is_portrait else 44)
    badge_x  = x + 22
    badge_cx = badge_x + badge_d // 2
    badge_cy = y + h // 2

    if correct:
        badge_fill = correct_rgb
        badge_fg   = (255, 255, 255)
    else:
        badge_fill = _rgb(theme['badge_bg'])
        badge_fg   = _rgb(theme['badge_fg'])

    if correct:
        _draw_glow_ellipse(img_rgba, badge_cx, badge_cy, badge_d // 2,
                           correct_rgb, intensity=0.75, blur_r=8)

    draw.ellipse([badge_x, badge_cy - badge_d // 2,
                  badge_x + badge_d, badge_cy + badge_d // 2],
                 fill=(*badge_fill, 255), outline=(255, 255, 255, 200), width=2)

    lf = _load_font(_sz_half(22 if is_portrait else 18), bold=True, heavy=True)
    lw = _tw(draw, letter, lf)
    lh = _th(draw, letter, lf)
    _dt(draw, (badge_cx - lw // 2, badge_cy - lh // 2), letter, lf, (*badge_fg, 255), ink=True)

    # Option text — dynamic sizing
    text_x = badge_x + badge_d + 18
    text_w = w - (text_x - x) - 18 - 44          # 44 px reserved on the right for the tick
    text_cx = text_x + text_w // 2

    display = text

    sz_max = _sz(30 if is_portrait else 24)
    sz_min = 16
    font2, lines2, lh2 = _fit_text(draw, display, text_w, h - 20, sz_max, sz_min)
    block_h = len(lines2) * lh2
    ty = y + (h - block_h) // 2
    _draw_text_block(draw, lines2, font2, lh2, text_cx, ty,
                     (255, 255, 255, 255), align='center', max_w=text_w)

    if correct:                                   # vector check mark (font independent)
        ck_cx, ck_cy = x + w - 34, y + h // 2
        draw.line([(ck_cx - 13, ck_cy), (ck_cx - 4, ck_cy + 10), (ck_cx + 14, ck_cy - 11)],
                  fill=(*correct_rgb, 255), width=7, joint='curve')


# ─── Dynamic Option Height ────────────────────────────────────────────────────
def _measure_option_height(draw, opt_text, opt_w, is_portrait):
    """Return the card height needed to fit the option text."""
    badge_d = _sz_half(52 if is_portrait else 44)
    text_w  = opt_w - badge_d - 80 - 44   # badge + margins + tick area
    sz_max  = _sz(30 if is_portrait else 24)
    sz_min  = 16
    font, lines, lh = _fit_text(draw, opt_text, text_w, 400, sz_max, sz_min)
    content_h = len(lines) * lh
    return max(70, content_h + 36)   # 36 px vertical padding


# ─── V11 helpers: even boxes, anti-aliased ring, centred digits ───────────────
def _even_box(x0, y0, x1, y1, W, H):
    """Crop box with even coordinates (video encoders need even sizes / offsets)."""
    x0 = max(0, int(x0)) & ~1
    y0 = max(0, int(y0)) & ~1
    x1 = min(int(W), int(x1)) & ~1
    y1 = min(int(H), int(y1)) & ~1
    return (x0, y0, max(x0 + 2, x1), max(y0 + 2, y1))


def _aa_arc(img_rgba, cx, cy, r, width, rgb, start_deg, end_deg, ss=4):
    """Smooth (anti-aliased) arc / ring, drawn 4x bigger and scaled down."""
    pad  = 4
    size = int(2 * (r + pad))
    S    = size * ss
    layer = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    c = S / 2.0
    R = r * ss
    box = [c - R, c - R, c + R, c + R]
    col = (int(rgb[0]), int(rgb[1]), int(rgb[2]), 255)
    if end_deg - start_deg >= 359.5:
        d.ellipse(box, outline=col, width=width * ss)
    else:
        d.arc(box, start=start_deg, end=end_deg, fill=col, width=width * ss)
    layer = layer.resize((size, size), Image.BOX)
    img_rgba.alpha_composite(layer, dest=(int(cx - size // 2), int(cy - size // 2)))


def _draw_center_text(draw, cx, cy, text, font, fill):
    """Digits exactly in the middle of (cx, cy) - works for Pillow and HarfBuzz fonts."""
    if isinstance(font, _HBFont):
        w = font.width(text)
        b = font.bbox(text)
        font.draw(draw, (cx - w // 2, cy - (b[3] - b[1]) // 2), text, fill, ink=True)
    else:
        bb = draw.textbbox((0, 0), text, font=font)
        draw.text((cx - (bb[0] + bb[2]) / 2.0, cy - (bb[1] + bb[3]) / 2.0),
                  text, font=font, fill=fill)


def _ring_dynamic(img_rgba, cx, cy, r, rgb, frac, num):
    """The moving part of the countdown: coloured arc (frac = how much is left) + number."""
    frac = max(0.0, min(1.0, frac))
    if frac > 0.002:
        _aa_arc(img_rgba, cx, cy, r, 7, rgb, -90 + (1.0 - frac) * 360.0, 270)
    ns = str(num)
    nf = _load_font(34 if len(ns) <= 2 else 24, bold=True, heavy=True)
    _draw_center_text(ImageDraw.Draw(img_rgba), cx, cy, ns, nf, (*rgb, 255))


# ──────────────────────────────────────────────────────────────────────────────
#  PREMIUM SLIDE RENDERERS
# ──────────────────────────────────────────────────────────────────────────────

def _render_hook(W, H, theme, num_q, timer_secs, is_portrait, glow_phase=0.0):
    """Premium cinematic Intro Screen."""
    img_rgba = _make_gradient_bg(W, H, theme, glow_phase)
    draw = ImageDraw.Draw(img_rgba)
    _draw_footer(img_rgba, draw, W, H, theme, glow_phase)

    mg = 44 if is_portrait else 36
    cx = W // 2
    footer_top = H - 118

    # ── Top badge row ──────────────────────────────────────────────────────
    badge_texts = _t('hook_badges')
    badge_text = badge_texts[abs(hash(str(num_q) + str(timer_secs))) % len(badge_texts)]
    badge_bot = _draw_badge(img_rgba, draw, W, mg, badge_text, theme, is_portrait, glow_phase=glow_phase)
    y = badge_bot + 18

    # ── Main central card ──────────────────────────────────────────────────
    content_zone = footer_top - y - 20
    card_pad_top = 24
    card_pad_side = 50

    # Estimate text heights to size card properly
    dummy_draw = ImageDraw.Draw(Image.new('RGBA', (W, H)))
    inner_w = W - 2 * mg - 2 * card_pad_side

    # Line 1: IQ Test header
    line1 = _t('hook_l1')
    f1, ls1, lh1 = _fit_text(dummy_draw, line1, inner_w, 140, 42 if is_portrait else 34, 26, heavy=True)
    b1h = len(ls1) * lh1

    # Line 2: challenge hook
    if num_q > 1:
        line2 = _t('hook_l2_multi').format(n=num_q)
    else:
        line2 = _t('hook_l2_single')
    f2, ls2, lh2 = _fit_text(dummy_draw, line2, inner_w, 160, 48 if is_portrait else 40, 28, heavy=True)
    b2h = len(ls2) * lh2

    # Line 3: timer
    line3 = _t('hook_l3').format(s=timer_secs)
    f3, ls3, lh3 = _fit_text(dummy_draw, line3, inner_w, 120, 40 if is_portrait else 32, 24, heavy=True)
    b3h = len(ls3) * lh3

    gap = 30
    total_text_h = b1h + gap + b2h + gap + b3h
    card_h = total_text_h + card_pad_top * 3
    card_h = max(200, min(card_h, int(content_zone * 0.82)))

    card_x  = mg
    card_x2 = W - mg
    card_y  = y
    card_y2 = card_y + card_h

    # Draw main card with strong glow
    _draw_card(img_rgba, draw, card_x, card_y, card_x2, card_y2, theme,
               radius=40, glow_phase=glow_phase, extra_glow=True)

    # Draw text inside card
    ty = card_y + card_pad_top + (card_h - total_text_h - card_pad_top) // 2

    _draw_text_block(draw, ls1, f1, lh1, cx, ty, (255, 255, 255, 255))
    ty += b1h + gap

    _draw_text_block(draw, ls2, f2, lh2, cx, ty, (*_rgb(theme['accent']), 255))
    ty += b2h + gap

    _draw_text_block(draw, ls3, f3, lh3, cx, ty, (*_rgb(theme['border']), 255))

    # ── Decorative accent dots at corners ─────────────────────────────────
    dot_c  = _rgb(theme.get('glow', theme['border']))
    dot_a  = int(160 * theme.get('glow_intensity', 0.85))
    for (dx, dy) in [(card_x + 20, card_y + 20), (card_x2 - 20, card_y + 20),
                     (card_x + 20, card_y2 - 20), (card_x2 - 20, card_y2 - 20)]:
        draw.ellipse([dx - 6, dy - 6, dx + 6, dy + 6], fill=(*dot_c, dot_a))

    # ── CTA area below main card ───────────────────────────────────────────
    remaining = footer_top - card_y2
    if remaining > 80:
        cta_text = _t('hook_cta')
        cta_font = _load_font(24 if is_portrait else 20, bold=True, heavy=True)
        cta_w    = _tw(draw, cta_text, cta_font)
        cta_h    = _th(draw, cta_text, cta_font)
        cta_y    = card_y2 + (remaining - cta_h) // 2
        _dt(draw, (cx - cta_w // 2, cta_y), cta_text, cta_font,
            (*_rgb(theme['accent']), 220), ink=True)

    return img_rgba.convert('RGB')


def _render_mcq(*args, **kwargs):
    _TL.shrink = 1.0
    try:
        return _render_mcq_impl(*args, **kwargs)
    finally:
        _TL.shrink = 1.0


def _render_mcq_impl(W, H, theme, question, slide_type, timer_secs, is_portrait,
                     glow_phase=0.0):
    """Render entrance, timer, or answer slide — with dynamic sizing."""
    img_rgba = _make_gradient_bg(W, H, theme, glow_phase)
    draw = ImageDraw.Draw(img_rgba)
    _draw_footer(img_rgba, draw, W, H, theme, glow_phase)

    mg   = 44 if is_portrait else 30
    cx   = W // 2
    cw   = W - 2 * mg

    q_text = question['questionText']
    opts   = question['options']
    ci     = question['correctIndex']
    L      = ['A', 'B', 'C', 'D']

    # ── Badge ─────────────────────────────────────────────────────────────
    if slide_type == 'entrance':
        badge_text = _t('badge_entrance')
    elif slide_type == 'timer':
        badge_text = _t('badge_timer')
    else:
        badge_text = _t('badge_answer')

    badge_bot = _draw_badge(img_rgba, draw, W, mg, badge_text, theme, is_portrait,
                            glow_phase=glow_phase)
    y = badge_bot + 18

    # ── Text-size auto-fit ──────────────────────────────────────────────────
    # The user's text size is applied as-is unless the options would leave too
    # little room for the question; then it shrinks a little (never below the
    # original size). Worst case (timer slide layout) is used for every slide of
    # the question so the text size never jumps between slides.
    n_opts    = min(4, len(opts))
    opt_gap   = 16 if is_portrait else 12
    _fh_top   = H - 118
    _t_h      = 120 if is_portrait else 100
    _worst_bt = _fh_top - 16 - _t_h - 16
    _min_q_h  = 190 if is_portrait else 130
    _budget   = _worst_bt - y - 16 - _min_q_h - 8
    _TL.shrink = 1.0
    _floor = 0.5                       # never smaller than half the base size
    for _step in range(40):
        _hs = [_measure_option_height(
                   draw, (opts[i] if i < len(opts) else ''), cw, is_portrait)
               for i in range(n_opts)]
        if sum(_hs) + (n_opts - 1) * opt_gap <= _budget or _eff_scale() <= _floor:
            break
        _TL.shrink = max(_floor / max(TEXT_SCALE, 0.01), _TL.shrink - 0.05)

    # ── Dynamic option heights ─────────────────────────────────────────────
    opt_heights = [_measure_option_height(draw, opts[i] if i < len(opts) else '', cw,
                                          is_portrait)
                   for i in range(n_opts)]

    # ── Layout: work from bottom up ────────────────────────────────────────
    footer_top = H - 118
    timer_h    = 120 if is_portrait else 100
    timer_gap  = 16

    if slide_type == 'timer':
        opts_bottom = footer_top - timer_gap - timer_h - timer_gap
    else:
        opts_bottom = footer_top - opt_gap

    opts_section_h = sum(opt_heights) + (n_opts - 1) * opt_gap
    opts_top       = opts_bottom - opts_section_h
    qbox_gap       = 16
    qbox_available = opts_top - y - qbox_gap

    # ── Question box (dynamic height) ─────────────────────────────────────
    q_inner_w = cw - 80
    ql        = len(q_text)
    sz_max    = 46 if is_portrait else 38
    sz_min    = 20
    if ql > 280: sz_max = 32 if is_portrait else 26
    elif ql > 140: sz_max = 38 if is_portrait else 32

    q_font, q_lines, q_lh = _fit_text(draw, q_text, q_inner_w,
                                       max(60, qbox_available) - 40, _sz(sz_max), sz_min)
    actual_q_text_h = len(q_lines) * q_lh
    qbox_h = max(80, actual_q_text_h + 44)  # dynamic: fits content + padding
    qbox_h = max(60, min(qbox_h, qbox_available))

    _draw_card(img_rgba, draw, mg, y, W - mg, y + qbox_h, theme,
               radius=28, glow_phase=glow_phase)

    qy = y + (qbox_h - actual_q_text_h) // 2
    # V11: when an animation is requested, remember the "clean" question box (card without
    # text) so the typewriter frames can be built later without re-rendering the whole slide.
    _cap = getattr(_TL, 'cap', None)
    if _cap is not None and slide_type == 'entrance':
        _bx = _even_box(mg - 30, y - 30, W - mg + 30, y + qbox_h + 8, W, H)
        _cap['q'] = {'box': _bx, 'crop': img_rgba.crop(_bx).convert('RGB'),
                     'lines': q_lines, 'font': q_font, 'lh': q_lh, 'ty': qy,
                     'cx': mg + 40 + (cw - 80) // 2, 'max_w': q_inner_w,
                     'cursor_rgb': _rgb(theme['accent'])}
    _draw_text_block(draw, q_lines, q_font, q_lh, mg + 40 + (cw - 80) // 2,
                     qy, (255, 255, 255, 255), max_w=q_inner_w)

    # ── Options ───────────────────────────────────────────────────────────
    oy = y + qbox_h + 8
    if _cap is not None and slide_type == 'entrance':      # V11: clean options area + row geometry
        _rows, _yy = [], oy
        for _i in range(n_opts):
            _rows.append((mg, _yy, cw, opt_heights[_i], L[_i],
                          opts[_i] if _i < len(opts) else ""))
            _yy += opt_heights[_i] + opt_gap
        _bx = _even_box(0, oy, W, _yy - opt_gap + 2, W, H)
        _cap['opts'] = {'box': _bx, 'crop': img_rgba.crop(_bx).convert('RGB'),
                        'rows': _rows, 'theme': theme, 'glow_phase': glow_phase,
                        'is_portrait': is_portrait,
                        'shrink': getattr(_TL, 'shrink', 1.0)}
    for i in range(n_opts):
        oh = opt_heights[i]
        is_correct = (slide_type == 'answer') and (i == ci)
        opt_txt = opts[i] if i < len(opts) else ""
        _draw_option_row(img_rgba, draw, mg, oy, cw, oh, L[i], opt_txt,
                         theme, correct=is_correct, is_portrait=is_portrait,
                         glow_phase=glow_phase)
        oy += oh + opt_gap

    # ── Timer box (timer slide only) ──────────────────────────────────────
    if slide_type == 'timer':
        tb_y  = opts_bottom + timer_gap
        tb_y2 = tb_y + timer_h
        if tb_y2 > footer_top - 4:
            tb_y2 = footer_top - 4
            tb_y  = tb_y2 - timer_h

        _draw_card(img_rgba, draw, mg, tb_y, W - mg, tb_y2, theme,
                   accent_border=True, radius=22, glow_phase=glow_phase + math.pi,
                   extra_glow=True)

        # Ring circle with glow
        ring_cx = mg + 68
        ring_cy = (tb_y + tb_y2) // 2
        ring_r  = 36
        ring_rgb = _rgb(theme['accent'])

        _draw_glow_ellipse(img_rgba, ring_cx, ring_cy, ring_r + 4,
                           ring_rgb, intensity=0.85, blur_r=10)

        # dark track (static), then the live arc + number (full ring, number = timer seconds)
        _aa_arc(img_rgba, ring_cx, ring_cy, ring_r, 7, _darken(ring_rgb, 60), -90, 270)
        if _cap is not None:                                   # V11: clean ring for the countdown
            _pd = 18
            _bx = _even_box(ring_cx - ring_r - _pd, ring_cy - ring_r - _pd,
                            ring_cx + ring_r + _pd, ring_cy + ring_r + _pd, W, H)
            _cap['ring'] = {'box': _bx, 'crop': img_rgba.crop(_bx).convert('RGB'),
                            'cx': ring_cx, 'cy': ring_cy, 'r': ring_r, 'rgb': ring_rgb}
        _ring_dynamic(img_rgba, ring_cx, ring_cy, ring_r, ring_rgb, 1.0, timer_secs)

        lf2 = _load_font(26 if is_portrait else 22, bold=True, heavy=True)
        lbl = _t('guess')
        lw = _tw(draw, lbl, lf2); lh_ = _th(draw, lbl, lf2)
        _dt(draw, (ring_cx + ring_r + 24, (tb_y + tb_y2) // 2 - lh_ // 2),
            lbl, lf2, (*ring_rgb, 255), ink=True)

    # ── Offline keyword sticker ─────────────────────────────────────────────
    # Drops a relevant emoji/sticker (in a glowing 3D-style badge) into
    # whatever empty space is left below the options (and above the footer /
    # timer box). Skips silently if there's no room or no keyword match —
    # never disturbs the layout.
    sticker_box_top = oy - opt_gap
    if slide_type == 'timer':
        sticker_box_bottom = tb_y - timer_gap
    else:
        sticker_box_bottom = footer_top - 6
    if sticker_box_bottom - sticker_box_top >= 50:
        place_sticker(img_rgba, draw,
                      (mg, sticker_box_top + 6, W - mg, sticker_box_bottom),
                      q_text, theme=theme)

    return img_rgba.convert('RGB')


def _render_explanation(W, H, theme, sentences, is_portrait, glow_phase=0.0):
    img_rgba = _make_gradient_bg(W, H, theme, glow_phase)
    draw = ImageDraw.Draw(img_rgba)
    _draw_footer(img_rgba, draw, W, H, theme, glow_phase)

    mg = 44 if is_portrait else 30
    cx = W // 2
    cw = W - 2 * mg

    # Explanation header badge
    badge_bot = _draw_badge(img_rgba, draw, W, mg,
                            _t('badge_expl'), theme, is_portrait,
                            glow_phase=glow_phase)
    y = badge_bot + 18

    footer_top = H - 118
    available_h = footer_top - y
    n        = max(1, len(sentences))
    item_gap = 14 if is_portrait else 10
    item_h   = (available_h - (n - 1) * item_gap) // n
    item_h   = max(80, min(item_h, int((320 if is_portrait else 240) * max(1.0, _eff_scale()))))

    accent_rgb = _rgb(theme['accent'])
    border_rgb = _rgb(theme['border'])

    for sent in sentences:
        _draw_card(img_rgba, draw, mg, y, W - mg, y + item_h, theme,
                   radius=22, glow_phase=glow_phase)

        # Premium bullet: glowing diamond
        bw   = int(_sz(26 if is_portrait else 20) * 0.62)      # vector diamond bullet
        bcx, bcy, br = mg + 20 + bw // 2, y + item_h // 2, bw // 2
        draw.polygon([(bcx, bcy - br), (bcx + br, bcy), (bcx, bcy + br), (bcx - br, bcy)],
                     fill=(*accent_rgb, 255))

        txt_x = mg + 20 + bw + 16
        txt_w = (W - mg) - txt_x - 18
        sf, sl, slh = _fit_text(draw, sent, txt_w, item_h - 24,
                                 _sz(30 if is_portrait else 24), 16)
        block_h = len(sl) * slh
        ty = y + (item_h - block_h) // 2
        _draw_text_block(draw, sl, sf, slh, txt_x + txt_w // 2, ty,
                         (240, 248, 255, 255))
        y += item_h + item_gap

    return img_rgba.convert('RGB')


def _render_end(W, H, theme, is_portrait, glow_phase=0.0):
    """Premium cinematic Outro / End Screen."""
    img_rgba = _make_gradient_bg(W, H, theme, glow_phase)
    draw = ImageDraw.Draw(img_rgba)
    _draw_footer(img_rgba, draw, W, H, theme, glow_phase)

    mg  = 44 if is_portrait else 36
    cx  = W // 2
    footer_top = H - 118
    content_h  = footer_top - mg

    glow_rgb   = _rgb(theme.get('glow', theme['border']))
    accent_rgb = _rgb(theme['accent'])
    border_rgb = _rgb(theme['border'])

    # ── Top celebration badge ──────────────────────────────────────────────
    badge_bot = _draw_badge(img_rgba, draw, W, mg,
                            _t('badge_end'),
                            theme, is_portrait, glow_phase=glow_phase)
    y = badge_bot + 16

    # ── Main card ─────────────────────────────────────────────────────────
    card_x  = mg + 20
    card_x2 = W - mg - 20
    card_inner_w = card_x2 - card_x - 80
    card_h  = int(content_h * 0.68)
    card_y  = y
    card_y2 = card_y + card_h

    _draw_card(img_rgba, draw, card_x, card_y, card_x2, card_y2, theme,
               accent_border=True, radius=44, glow_phase=glow_phase,
               extra_glow=True)

    # ── Trophy / star symbol ──────────────────────────────────────────────
    trophy_text = "\U0001f3c6"   # trophy emoji
    trophy_y = card_y + 28
    _timg = _emoji_image(trophy_text, 80 if is_portrait else 64)
    if _timg is not None:
        th = _timg.height
        img_rgba.alpha_composite(_timg, (cx - _timg.width // 2, trophy_y))
    else:
        trophy_font = _load_emoji_font(80 if is_portrait else 64)
        tw = _tw(draw, trophy_text, trophy_font)
        th = _th(draw, trophy_text, trophy_font)
        draw.text((cx - tw // 2, trophy_y), trophy_text,
                  font=trophy_font, fill=(*accent_rgb, 255))

    inner_y = trophy_y + th + 20

    # ── Main call-to-action text ──────────────────────────────────────────
    lines_cfg = [
        (_t('end_l1'), 50 if is_portrait else 42, (255, 255, 255)),
        (_t('end_l2'), 30 if is_portrait else 24, (*accent_rgb,)),
    ]

    for (txt, sz_max, color) in lines_cfg:
        f_, ls_, lh_ = _fit_text(draw, txt, card_inner_w,
                                  card_y2 - inner_y - 80, sz_max, max(20, sz_max - 12),
                                  heavy=True)
        bh_ = len(ls_) * lh_
        _draw_text_block(draw, ls_, f_, lh_, cx, inner_y,
                         (*color[:3], 255) if len(color) == 3 else color)
        inner_y += bh_ + 16

    # ── Social action row ─────────────────────────────────────────────────
    remaining_card = card_y2 - inner_y - 20
    if remaining_card > 50:
        _al = _t('end_actions')
        actions = [(_al[0], accent_rgb), (_al[1], border_rgb),
                   (_al[2], accent_rgb), (_al[3], border_rgb)]
        action_font = _load_font(26 if is_portrait else 22, bold=True, heavy=True)
        total_w = sum(_tw(draw, a[0], action_font) + 30 for a in actions) - 30
        ax = cx - total_w // 2
        ay = inner_y + (remaining_card - _th(draw, actions[0][0], action_font)) // 2

        for (atxt, acolor) in actions:
            aw = _tw(draw, atxt, action_font)
            _dt(draw, (ax, ay), atxt, action_font, (*acolor, 255), ink=True)
            ax += aw + 30

    # ── Second smaller card with channel message ───────────────────────────
    remaining = footer_top - card_y2
    if remaining > 70:
        c2_h  = min(remaining - 20, 90 if is_portrait else 70)
        c2_y  = card_y2 + (remaining - c2_h) // 2
        c2_x  = mg + 40
        c2_x2 = W - mg - 40
        _draw_card(img_rgba, draw, c2_x, c2_y, c2_x2, c2_y + c2_h, theme,
                   radius=22, glow_phase=glow_phase + math.pi * 0.5)
        sub_text = _t('end_sub')
        sub_font = _load_font(22 if is_portrait else 18, bold=True)
        sw = _tw(draw, sub_text, sub_font)
        sh = _th(draw, sub_text, sub_font)
        _dt(draw, (cx - sw // 2, c2_y + (c2_h - sh) // 2), sub_text, sub_font,
            (*border_rgb, 230), ink=True)

    return img_rgba.convert('RGB')


def render_slide(slide_data, W, H, is_portrait):
    """Top-level dispatcher: returns a Pillow RGB Image for the given slide dict."""
    _TL.lang  = slide_data.get('lang', 'en')
    t         = slide_data['type']
    theme_idx = slide_data.get('theme_idx', 0) % len(THEMES)
    theme     = THEMES[theme_idx]
    ts        = slide_data.get('timer_secs', 10)
    gp        = slide_data.get('glow_phase', 0.0)

    if t == 'hook':
        return _render_hook(W, H, theme, slide_data.get('num_q', 1), ts,
                            is_portrait, glow_phase=gp)
    elif t in ('entrance', 'timer', 'answer'):
        return _render_mcq(W, H, theme, slide_data['q'], t, ts, is_portrait,
                           glow_phase=gp)
    elif t == 'explanation':
        return _render_explanation(W, H, theme, slide_data.get('sentences', []),
                                   is_portrait, glow_phase=gp)
    elif t == 'end':
        return _render_end(W, H, theme, is_portrait, glow_phase=gp)
    else:
        img = _make_gradient_bg(W, H, theme, gp)
        d   = ImageDraw.Draw(img)
        _draw_footer(img, d, W, H, theme, gp)
        return img.convert('RGB')


# ─── Video-Background support: foreground "matte" renderer ───────────────────
# The normal renderer paints the slide on a static gradient. For video backgrounds
# we need ONLY the foreground (cards, text, glow, footer) with real transparency.
# Trick: render the very same slide twice - once on pure black, once on pure white.
#   * pixels that look identical in both renders are fully opaque (cards, text)
#   * pixels that differ are semi-transparent (soft glows): alpha = 1 - diff/255
# The black render is already the "premultiplied" colour. This keeps every card,
# glow and sticker looking exactly like before; only the background is removed.
def render_slide_matte(slide_data, W, H, is_portrait, want_cap=False):
    """Returns (premult_rgb, alpha_rgb) PIL RGB images (alpha stored as grey).
    want_cap=True  ->  returns ((premult_rgb, alpha_rgb), cap) where cap holds the clean
    regions needed by the V11 animations (one black-render crop + one white-render crop each)."""
    caps = []
    res  = []
    try:
        for col in ((0, 0, 0), (255, 255, 255)):
            _TL.solid_bg = col
            _TL.cap = {} if want_cap else None
            res.append(render_slide(slide_data, W, H, is_portrait))
            caps.append(_TL.cap)
    finally:
        _TL.solid_bg = None
        _TL.cap = None
    blk, wht = res
    b = np.asarray(blk, dtype=np.int16)
    w = np.asarray(wht, dtype=np.int16)
    a = 255.0 - (w - b).mean(axis=2)
    a = np.clip(a, 0, 255).astype(np.uint8)
    alpha_rgb = Image.fromarray(np.dstack([a, a, a]), 'RGB')
    if not want_cap:
        return blk, alpha_rgb
    cap = {}
    for k, v in (caps[0] or {}).items():
        item = dict(v)
        item['crops'] = [v['crop'], caps[1][k]['crop']]
        cap[k] = item
    return (blk, alpha_rgb), cap


def render_slide_with_cap(slide_data, W, H, is_portrait):
    """Normal (non-video-background) render + clean regions for the V11 animations."""
    _TL.cap = {}
    try:
        img = render_slide(slide_data, W, H, is_portrait)
        cap = _TL.cap
    finally:
        _TL.cap = None
    for v in cap.values():
        v['crops'] = [v['crop']]
    return img, cap


def _matte_to_rgba(premult_rgb, alpha_rgb):
    """Premultiplied RGB + alpha  ->  straight-alpha RGBA (what ffmpeg overlay wants).
    Uses Pillow's built-in premultiplied mode ('RGBa') so the un-premultiply happens in C."""
    r, g, b = premult_rgb.split()
    a = alpha_rgb.split()[0]
    pm = Image.merge('RGBA', (r, g, b, a))
    return Image.frombytes('RGBa', pm.size, pm.tobytes()).convert('RGBA')


# ─── Cinematic Transition Engine ─────────────────────────────────────────────
# Allowed premium transitions (no cube, no star wipe, no PowerPoint effects)
PREMIUM_TRANSITIONS = [
    'fade',          # smooth opacity blend
    'slide_up',      # curr enters from bottom
    'slide_down',    # curr enters from top
    'fade_up',       # blend + slight upward drift
    'fade_down',     # blend + slight downward drift
    'soft_dissolve', # very gentle cross-dissolve
    'scale_fade',    # curr zooms from 110% while fading in
    'zoom_out',      # prev gently zooms out as curr fades in
    'wipe_up',       # curtain wipe from bottom to top
    'wipe_down',     # curtain wipe from top to bottom
    'content_morph', # luminance-boosted dissolve
    'perspective_drift',  # subtle horizontal drift + blend
    'layered_fade',  # double-exposure style
    'opacity_transform',  # eased opacity blend
    'cinematic_reveal',   # slide_up with ease-out curve
]

# Transition timing
_N_TRANS_FRAMES   = 10      # frames per transition
_TRANS_FRAME_DUR  = 0.04    # seconds per frame (25 fps = 0.04s)
_TRANS_TOTAL_DUR  = _N_TRANS_FRAMES * _TRANS_FRAME_DUR  # 0.40 s


def _ease_out(t):
    """Ease-out cubic: fast start, slow end."""
    return 1.0 - (1.0 - t) ** 3


def _ease_in_out(t):
    """Smooth S-curve easing."""
    return t * t * (3 - 2 * t)


def _render_transition_frames(prev_rgb, curr_rgb, transition_type, n=_N_TRANS_FRAMES):
    """
    Generate n transition frames blending from prev_rgb to curr_rgb.
    Both images must be PIL RGB with the same W×H.
    Returns list of PIL RGB images.
    """
    frames = []
    W, H = curr_rgb.size

    for i in range(n):
        raw_t = (i + 1) / (n + 1)  # 0 < raw_t < 1

        try:
            if transition_type == 'fade':
                t = _ease_in_out(raw_t)
                frame = Image.blend(prev_rgb, curr_rgb, alpha=t)

            elif transition_type == 'slide_up':
                t     = _ease_out(raw_t)
                offset = int(H * (1.0 - t))
                frame  = prev_rgb.copy()
                frame.paste(curr_rgb, (0, offset))

            elif transition_type == 'slide_down':
                t     = _ease_out(raw_t)
                offset = int(-H * (1.0 - t))
                frame  = prev_rgb.copy()
                frame.paste(curr_rgb, (0, offset))

            elif transition_type == 'fade_up':
                t      = _ease_in_out(raw_t)
                drift  = int(H * 0.04 * (1.0 - raw_t))
                shifted = Image.new('RGB', (W, H), (0, 0, 0))
                shifted.paste(curr_rgb, (0, -drift))
                frame  = Image.blend(prev_rgb, shifted, alpha=t)

            elif transition_type == 'fade_down':
                t     = _ease_in_out(raw_t)
                drift = int(H * 0.04 * (1.0 - raw_t))
                shifted = Image.new('RGB', (W, H), (0, 0, 0))
                shifted.paste(curr_rgb, (0, drift))
                frame = Image.blend(prev_rgb, shifted, alpha=t)

            elif transition_type in ('soft_dissolve', 'layered_fade',
                                     'opacity_transform'):
                t     = _ease_in_out(raw_t)
                frame = Image.blend(prev_rgb, curr_rgb, alpha=t)

            elif transition_type == 'scale_fade':
                t     = _ease_out(raw_t)
                scale = 1.0 + 0.10 * (1.0 - raw_t)
                nw    = int(W * scale)
                nh    = int(H * scale)
                scaled = curr_rgb.resize((nw, nh), Image.BILINEAR)
                ox    = (nw - W) // 2
                oy    = (nh - H) // 2
                cropped = scaled.crop((ox, oy, ox + W, oy + H))
                frame = Image.blend(prev_rgb, cropped, alpha=t)

            elif transition_type == 'zoom_out':
                t     = _ease_out(raw_t)
                scale = 1.0 + 0.08 * raw_t
                nw    = int(W * scale)
                nh    = int(H * scale)
                scaled_prev = prev_rgb.resize((nw, nh), Image.BILINEAR)
                ox   = (nw - W) // 2
                oy   = (nh - H) // 2
                cropped_prev = scaled_prev.crop((ox, oy, ox + W, oy + H))
                frame = Image.blend(cropped_prev, curr_rgb, alpha=t)

            elif transition_type == 'wipe_up':
                wipe_start = int(H * (1.0 - raw_t))
                frame = prev_rgb.copy()
                if wipe_start < H:
                    patch = curr_rgb.crop((0, wipe_start, W, H))
                    frame.paste(patch, (0, wipe_start))

            elif transition_type == 'wipe_down':
                wipe_end = int(H * raw_t)
                frame = prev_rgb.copy()
                if wipe_end > 0:
                    patch = curr_rgb.crop((0, 0, W, wipe_end))
                    frame.paste(patch, (0, 0))

            elif transition_type == 'content_morph':
                t     = _ease_in_out(raw_t)
                frame = Image.blend(prev_rgb, curr_rgb, alpha=t)
                if HAS_NUMPY and 0.3 < raw_t < 0.7:
                    brightness = 1.0 + 0.12 * math.sin(raw_t * math.pi)
                    arr  = np.array(frame, dtype=np.float32)
                    arr  = np.clip(arr * brightness, 0, 255).astype(np.uint8)
                    frame = Image.fromarray(arr)

            elif transition_type == 'perspective_drift':
                t     = _ease_in_out(raw_t)
                drift = int(W * 0.025 * (1.0 - raw_t))
                drifted = Image.new('RGB', (W, H), (0, 0, 0))
                drifted.paste(curr_rgb, (drift, 0))
                frame = Image.blend(prev_rgb, drifted, alpha=t)

            elif transition_type == 'cinematic_reveal':
                # Ease-out slide_up variant
                t     = _ease_out(raw_t) ** 0.7
                offset = int(H * (1.0 - t))
                frame  = prev_rgb.copy()
                frame.paste(curr_rgb, (0, offset))

            else:
                t     = _ease_in_out(raw_t)
                frame = Image.blend(prev_rgb, curr_rgb, alpha=t)

        except Exception:
            frame = Image.blend(prev_rgb, curr_rgb, alpha=raw_t)

        frames.append(frame.convert('RGB'))

    return frames


def _render_transition_frames_rgba(prev_pair, curr_pair, transition_type, n=_N_TRANS_FRAMES):
    """Same 15 transitions, but for (premult_rgb, alpha_rgb) pairs -> list of RGBA frames.
    The colour layer and the alpha layer go through the identical transition."""
    col = _render_transition_frames(prev_pair[0], curr_pair[0], transition_type, n)
    alp = _render_transition_frames(prev_pair[1], curr_pair[1], transition_type, n)
    return [_matte_to_rgba(c, a) for c, a in zip(col, alp)]



# ═════════════════════════════════════════════════════════════════════════════
#  V11 ANIMATION ENGINE  -  typewriter question / sliding options / live countdown
# ═════════════════════════════════════════════════════════════════════════════
# Why it is fast: every slide is still rendered ONLY ONCE. The part of the screen that
# moves (question box, option rows, countdown ring) is cut out as a small "sprite"
# sequence and ffmpeg lays it over the normal slide image at the right time.
# (In video-background mode the same idea is used, with transparency.)

class _MImg:
    """An RGB image - or, in video-background mode, a (premultiplied RGB + alpha) pair.
    Every operation is mirrored on both parts so the rest of the code does not care."""
    __slots__ = ('c', 'a')

    def __init__(self, c, a=None):
        self.c, self.a = c, a

    def copy(self):
        return _MImg(self.c.copy(), None if self.a is None else self.a.copy())

    def crop(self, box):
        return _MImg(self.c.crop(box), None if self.a is None else self.a.crop(box))

    def paste(self, other, xy):
        self.c.paste(other.c, xy)
        if self.a is not None:
            self.a.paste(other.a, xy)

    def clear(self, box):                      # make a transparent "hole"
        self.c.paste((0, 0, 0), box)
        if self.a is not None:
            self.a.paste((0, 0, 0), box)

    def std(self):                             # what the transition engine expects
        return self.c if self.a is None else (self.c, self.a)

    def sprite(self):                          # what gets written to disk for ffmpeg
        return self.c if self.a is None else _matte_to_rgba(self.c, self.a)

    @staticmethod
    def from_std(img):
        return _MImg(img[0], img[1]) if isinstance(img, tuple) else _MImg(img)

    @staticmethod
    def from_crops(crops):
        """1 crop -> normal image.  2 crops (black render, white render) -> matte pair."""
        if len(crops) == 1:
            return _MImg(crops[0].convert('RGB'))
        b = crops[0].convert('RGB')
        w = crops[1].convert('RGB')
        a = 255.0 - (np.asarray(w, dtype=np.int16) - np.asarray(b, dtype=np.int16)).mean(axis=2)
        a = np.clip(a, 0, 255).astype(np.uint8)
        return _MImg(b, Image.fromarray(np.dstack([a, a, a]), 'RGB'))


class _Region:
    def __init__(self, item):
        self.item  = item
        self.box   = item['box']
        self.x, self.y = self.box[0], self.box[1]
        self.clean = _MImg.from_crops(item['crops'])


def _compose(base, items):
    """Copy of `base` with the given (region, sprite) patches pasted in."""
    if not items:
        return base
    m = base.copy()
    for reg, patch in items:
        m.paste(patch, (reg.x, reg.y))
    return m


def _units(text):
    """Splits text into 'typing units' - a letter together with its matras / joined conjuncts,
    so Hindi never shows half-built characters while typing."""
    out = []
    for ch in text:
        if out and (unicodedata.category(ch) in ('Mn', 'Mc', 'Me') or ch in '\u200c\u200d'
                    or out[-1][-1] == '\u094d'):
            out[-1] += ch
        else:
            out.append(ch)
    return out


def _grid_steps(state_fn, make_fn, n_grid, step, still):
    """Samples the animation every `step` seconds, merges identical neighbours and makes the
    last state last until the end of the slide. Returns [{'key','dur','make'}, ...]
    whose durations add up to exactly `still`."""
    steps = []
    for j in range(n_grid):
        key = state_fn(j * step)
        if steps and steps[-1]['key'] == key:
            steps[-1]['dur'] += step
        else:
            steps.append({'key': key, 'dur': step})
    final = state_fn(1e9)
    rest  = still - n_grid * step
    if not steps:
        steps.append({'key': final, 'dur': max(step, still)})
    elif rest >= 0.02:
        if steps[-1]['key'] == final:
            steps[-1]['dur'] += rest
        else:
            steps.append({'key': final, 'dur': rest})
    else:
        steps[-1]['dur'] += rest
    for st in steps:
        st['make'] = (lambda k=st['key']: make_fn(k))
    return steps


def _draw_typed(reg, q_it, k, cursor):
    """Question box with the first k typing-units visible (+ optional blinking cursor)."""
    fr = reg.clean.copy()
    im = fr.c.convert('RGBA')
    d  = ImageDraw.Draw(im)
    font, lh = q_it['font'], q_it['lh']
    y    = q_it['ty'] - reg.y
    left = k
    for li, line in enumerate(q_it['lines']):
        if left <= 0 and li > 0:
            break
        w  = _tw(d, line, font)
        x  = max(q_it['cx'] - q_it['max_w'] // 2, q_it['cx'] - w // 2) - reg.x
        us = _units(line)
        m  = min(len(us), left)
        pre = ''.join(us[:m])
        if pre.strip():
            _dt(d, (x, y), pre, font, (255, 255, 255, 255))
        if cursor and left <= len(us):                    # typing is happening on this line
            cxp = x + (_tw(d, pre, font) if pre else 0) + 5
            d.rectangle([cxp, y + int(lh * 0.08), cxp + 3, y + int(lh * 0.80)],
                        fill=(*q_it['cursor_rgb'], 255))
        left -= m
        y += lh
    fr.c = im.convert('RGB')
    return fr


def _option_patches(reg, o_it):
    """Draws the option rows ONCE (at their final place) and cuts every row out as a patch."""
    _TL.shrink = o_it['shrink']
    try:
        crops = []
        for c in reg.item['crops']:
            im = c.convert('RGBA')
            d  = ImageDraw.Draw(im)
            for (x, y, w, h, letter, text) in o_it['rows']:
                _draw_option_row(im, d, x - reg.x, y - reg.y, w, h, letter, text,
                                 o_it['theme'], correct=False,
                                 is_portrait=o_it['is_portrait'],
                                 glow_phase=o_it['glow_phase'])
            crops.append(im.convert('RGB'))
    finally:
        _TL.shrink = 1.0
    full = _MImg.from_crops(crops)
    out = []
    for (x, y, w, h, letter, text) in o_it['rows']:
        lx, ly = x - reg.x, y - reg.y
        out.append((lx, ly, full.crop((lx, ly, lx + w + 2, ly + h + 2))))
    return out


def _plan_entrance_anim(cap, matte, W, still):
    """Typewriter question + options sliding in one by one (each one can be switched off)."""
    q_it, o_it = cap.get('q'), cap.get('opts')
    do_type = bool(ANIM_CFG.get('typewriter')) and q_it is not None
    do_opts = bool(ANIM_CFG.get('options')) and o_it is not None and bool(o_it['rows'])
    if not (do_type or do_opts):
        return None
    step = _ANIM_STEP_FAST
    plan = {'tracks': [], 'start_items': [], 'end_items': [], 'regions': []}

    # ── timeline (seconds from the moment the slide's still part begins) ──
    n_units, T_type = 0, 0.0
    if do_type:
        n_units = sum(len(_units(l)) for l in q_it['lines'])
        T_type  = min(1.5, max(0.7, n_units / 26.0))
    n_rows = len(o_it['rows']) if do_opts else 0
    t_opt0 = (T_type + 0.12) if do_type else 0.15
    stag, dur_o = 0.26, 0.40
    T_end = T_type
    if do_opts:
        T_end = max(T_end, t_opt0 + stag * (n_rows - 1) + dur_o)
    sc = min(1.0, max(0.6, still - 0.5) / T_end) if T_end > 0 else 1.0
    T_type, t_opt0, stag, dur_o, T_end = (v * sc for v in (T_type, t_opt0, stag, dur_o, T_end))
    n_grid = int(math.ceil(T_end / step))

    if do_type:
        q_reg = _Region(q_it)
        full_key = (n_units, False)

        def q_state(tau):
            if tau >= T_type:
                return full_key
            k = int(n_units * tau / T_type) if T_type > 0 else n_units
            return (k, int(tau / 0.28) % 2 == 0)

        steps = _grid_steps(q_state, lambda key: _draw_typed(q_reg, q_it, key[0], key[1]),
                            n_grid, step, still)
        plan['tracks'].append({'reg': q_reg, 'steps': steps})
        plan['start_items'].append((q_reg, steps[0]['make']()))
        plan['regions'].append(q_reg)

    if do_opts:
        o_reg   = _Region(o_it)
        patches = _option_patches(o_reg, o_it)
        starts  = [t_opt0 + i * stag for i in range(n_rows)]

        def o_state(tau):
            offs = []
            for i, row in enumerate(o_it['rows']):
                pr = (tau - starts[i]) / dur_o if dur_o > 0 else 1.0
                if pr <= 0:
                    offs.append(None)
                else:
                    offs.append(int(round((W - row[0]) * (1.0 - _ease_out(min(1.0, pr))))))
            return tuple(offs)

        def o_make(key):
            fr = o_reg.clean.copy()
            for (lx, ly, patch), off in zip(patches, key):
                if off is not None:
                    fr.paste(patch, (lx + off, ly))
            return fr

        steps = _grid_steps(o_state, o_make, n_grid, step, still)
        plan['tracks'].append({'reg': o_reg, 'steps': steps})
        plan['start_items'].append((o_reg, steps[0]['make']()))
        plan['regions'].append(o_reg)
    return plan


def _plan_timer_anim(cap, matte, still, timer_secs):
    """Live countdown: number goes timer_secs -> 1 and the ring empties smoothly."""
    r_it = cap.get('ring')
    if r_it is None or not ANIM_CFG.get('countdown'):
        return None
    reg  = _Region(r_it)
    step = _ANIM_STEP_RING
    cx_l, cy_l = r_it['cx'] - reg.x, r_it['cy'] - reg.y
    T = float(max(1, timer_secs))

    def state(tau):
        rem  = T - tau
        num  = max(1, int(math.ceil(rem - 1e-6)))
        frac = max(0.0, min(1.0, rem / T))
        return (num, int(round(frac * 720)))            # half-degree resolution

    def make(key):
        fr = reg.clean.copy()
        im = fr.c.convert('RGBA')
        _ring_dynamic(im, cx_l, cy_l, r_it['r'], r_it['rgb'], key[1] / 720.0, key[0])
        fr.c = im.convert('RGB')
        return fr

    steps = _grid_steps(state, make, int(still / step), step, still)
    return {'tracks': [{'reg': reg, 'steps': steps}], 'start_items': [],
            'end_items': [(reg, make(state(1e9)))], 'regions': [reg]}


def _save_track(track, matte, folder, tag):
    """Writes the sprite frames of one track to disk -> [(path, seconds), ...]."""
    frames = []
    for n, st in enumerate(track['steps']):
        m = st['make']()
        if matte:
            pth = os.path.join(folder, f"{tag}_{n}.png")
            m.sprite().save(pth, 'PNG', compress_level=1)
        else:
            pth = os.path.join(folder, f"{tag}_{n}.jpg")
            m.c.save(pth, 'JPEG', quality=92)
        frames.append((pth, st['dur']))
    return frames


# ─── V11: round logo watermark ────────────────────────────────────────────────
def _footer_pill_span(W, H):
    """Left / right edge of the LIKE-SHARE-SUBSCRIBE pill (so the logo never touches it)."""
    d    = ImageDraw.Draw(Image.new('RGB', (4, 4)))
    font = _load_font(28, bold=True, heavy=True)
    pw   = _tw(d, _t('footer'), font) + 100
    return (W - pw) // 2, (W + pw) // 2


def _prepare_logo(src_path, position, W, H, folder, log_fn):
    """Makes a circular logo PNG (white ring) sized for this video and returns
    {'path','x','y'} for the ffmpeg overlay - or None if it cannot be placed."""
    try:
        edge   = max(24, int(W * 0.035))
        d      = max(48, min(76, int(min(W, H) * 0.07))) & ~1
        left_e, right_e = _footer_pill_span(W, H)
        if position == 'bottom-left':
            room = left_e - 14 - edge
        else:
            room = W - edge - (right_e + 14)
        d = min(d, int(room) & ~1)
        if d < 36:
            log_fn("[LOGO] Not enough room next to the footer - logo skipped for this format.")
            return None
        x = edge if position == 'bottom-left' else W - edge - d
        y = H - 45 - d // 2                                   # centred in the 90px footer band
        im = Image.open(src_path).convert('RGBA')
        w0, h0 = im.size
        sq = min(w0, h0)
        im = im.crop(((w0 - sq) // 2, (h0 - sq) // 2, (w0 - sq) // 2 + sq, (h0 - sq) // 2 + sq))
        ss = 4
        big = im.resize((d * ss, d * ss), Image.LANCZOS)
        mask = Image.new('L', (d * ss, d * ss), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, d * ss - 1, d * ss - 1], fill=255)
        from PIL import ImageChops
        big.putalpha(ImageChops.multiply(big.getchannel('A'), mask))
        ImageDraw.Draw(big).ellipse([ss, ss, d * ss - 1 - ss, d * ss - 1 - ss],
                                    outline=(255, 255, 255, 235), width=3 * ss)
        out = big.resize((d, d), Image.LANCZOS)
        pth = os.path.join(folder, f"logo_{W}x{H}.png")
        out.save(pth, 'PNG')
        return {'path': pth, 'x': int(x) & ~1, 'y': int(y) & ~1}
    except Exception as e:
        log_fn(f"[LOGO] Could not use the logo image: {e}")
        return None


# ─── Slide Builder ────────────────────────────────────────────────────────────
def _build_inner_slides(question, show_explanation, timer_seconds,
                        theme_idx, rng, lang='en'):
    slides = []
    L  = ['A', 'B', 'C', 'D']
    ci = question['correctIndex']
    cl = L[ci] if ci < 4 else 'A'
    ct = question['options'][ci] if ci < len(question['options']) else ''
    S  = _STR[lang]
    cl_spoken = S['letters_spoken'][ci] if ci < 4 else S['letters_spoken'][0]

    # Unique glow phase for each slide
    def _gp():
        return rng.uniform(0, 2 * math.pi)

    ent_dur = 3.5                                   # V11: a bit more time when the question is animated
    if ANIM_CFG.get('typewriter'): ent_dur += 1.0
    if ANIM_CFG.get('options'):    ent_dur += 1.0
    slides.append({'type': 'entrance', 'q': question, 'theme_idx': theme_idx,
                   'speak': '', 'is_tick': False, 'fixed_dur': ent_dur,
                   'timer_secs': timer_seconds, 'glow_phase': _gp()})

    slides.append({'type': 'timer', 'q': question, 'theme_idx': theme_idx,
                   'speak': '', 'is_tick': True,
                   'fixed_dur': float(timer_seconds),
                   'timer_secs': timer_seconds, 'glow_phase': _gp()})

    slides.append({'type': 'answer', 'q': question, 'theme_idx': theme_idx,
                   'speak': (S['speak_answer'].format(L=cl_spoken, text=_speak_clean(ct, lang))
                             if lang == 'hi' else S['speak_answer'].format(L=cl, text=ct)),
                   'is_tick': False, 'fixed_dur': None, 'min_dur': 3.0,
                   'timer_secs': timer_seconds, 'glow_phase': _gp()})

    expl = question.get('explanation', '').strip()
    if show_explanation and expl:
        sents = [s.strip() for s in re.split(r'(?<=[.!?\u0964\u0965])\s+', expl)
                 if s.strip() and len(s.strip()) > 12]
        chunk = 4
        for i in range(0, max(1, len(sents)), chunk):
            group = sents[i:i + chunk]
            if not group:
                continue
            slides.append({'type': 'explanation', 'sentences': group,
                           'theme_idx': theme_idx,
                           'speak': _speak_clean(' '.join(group), lang),
                           'is_tick': False, 'fixed_dur': None, 'min_dur': 3.0,
                           'timer_secs': timer_seconds, 'glow_phase': _gp()})

    return slides


def _pick_themes_no_repeat(rng, n_themes_total, n_slots):
    """Pick n_slots theme indices with no consecutive repeats."""
    result = []
    last   = -1
    for _ in range(n_slots):
        pool = [t for t in range(n_themes_total) if t != last]
        idx  = rng.choice(pool)
        result.append(idx)
        last = idx
    return result


def build_video_slides(group_questions, show_explanation, timer_seconds,
                       hook_theme, q_themes, rng,
                       include_hook=True, include_end=True, lang='en'):
    slides = []
    S = _STR[lang]
    num_q  = len(group_questions)

    def _gp():
        return rng.uniform(0, 2 * math.pi)

    if include_hook:
        slides.append({'type': 'hook', 'num_q': num_q, 'theme_idx': hook_theme,
                       'speak': S['speak_hook'],
                       'is_tick': False, 'fixed_dur': None, 'min_dur': 2.5,
                       'timer_secs': timer_seconds, 'glow_phase': _gp(),
                       'qi': 0})                      # intro shares Q1's bg clip

    for qi, q in enumerate(group_questions):
        inner = _build_inner_slides(q, show_explanation, timer_seconds,
                                    q_themes[qi], rng, lang)
        for _s in inner:
            _s['qi'] = qi                             # which question this slide belongs to
        slides.extend(inner)

    if include_end:
        slides.append({'type': 'end', 'theme_idx': hook_theme,
                       'speak': S['speak_end'],
                       'is_tick': False, 'fixed_dur': None, 'min_dur': 2.5,
                       'timer_secs': timer_seconds, 'glow_phase': _gp(),
                       'qi': max(0, num_q - 1)})      # outro shares the last Q's bg clip

    for _s in slides:
        _s['lang'] = lang
    return slides


# ─── TTS Worker ───────────────────────────────────────────────────────────────
_EDGE_SEM = threading.Semaphore(3)


def _silent_for_text(wav_path, text):
    """No usable voice: keep a sensible reading time so the video timing stays natural."""
    generate_silent_wav(wav_path, max(1.5, min(25.0, 0.45 * len(text.split()))))


def _edge_tts_to_wav(text, wav_path, voice):
    """Microsoft Edge neural voice (needs internet + 'pip install edge-tts')."""
    if not HAS_EDGE:
        _warn_once('noedge', "[TTS WARNING] 'edge-tts' is not installed.  Run:  pip install edge-tts")
        return False
    rate = max(-50, min(100, int(round((TTS_CFG.get('speed', 1.0) - 1.0) * 100))))
    mp3  = wav_path + ".mp3"
    last = None
    for attempt in range(3):
        try:
            async def _go():
                await edge_tts.Communicate(text, voice, rate=f"{rate:+d}%").save(mp3)
            with _EDGE_SEM:
                asyncio.run(_go())
            if os.path.exists(mp3) and os.path.getsize(mp3) > 200:
                r = subprocess.run([FFMPEG_EXE, "-y", "-loglevel", "error", "-i", mp3,
                                    "-ar", str(CANONICAL_RATE), "-ac", "1",
                                    "-c:a", "pcm_s16le", wav_path],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if r.returncode == 0 and os.path.exists(wav_path):
                    try: os.remove(mp3)
                    except Exception: pass
                    return True
                last = r.stderr[-200:].decode(errors='ignore')
        except Exception as e:
            last = e
        time.sleep(1.0 * (attempt + 1))
    _warn_once('edgefail', f"[TTS WARNING] Edge voice '{voice}' failed ({last}). "
                           f"Check your internet connection - falling back to SAPI.")
    return False


def tts_worker(text, wav_path, voice_idx, sapi_rate, result_dict, key, lang='en'):
    """Android voice path: Edge Neural TTS; silence fallback preserves render timing."""
    text = text if text.strip() else " "
    try:
        voice = TTS_CFG['hi_edge_voice'] if lang == 'hi' else TTS_CFG['en_edge_voice']
        if _edge_tts_to_wav(text, wav_path, voice):
            result_dict[key] = wav_path
            return
    except Exception as exc:
        _warn_once('android_tts', f'[TTS] Edge Neural voice unavailable: {exc}')
    _silent_for_text(wav_path, text)
    result_dict[key] = wav_path


# ─── WAV Merge ────────────────────────────────────────────────────────────────
def _merge_wavs(wav_paths, out_path):
    tmp_dir   = tempfile.mkdtemp(prefix="wmerge_")
    init_done = False
    try:
        with wave.open(out_path, 'w') as out_wf:
            for idx, wp in enumerate(wav_paths):
                if not os.path.exists(wp):
                    continue
                try:
                    with wave.open(wp, 'r') as probe:
                        src_rate     = probe.getframerate()
                        src_channels = probe.getnchannels()
                        src_width    = probe.getsampwidth()

                    needs_norm = (src_rate     != CANONICAL_RATE     or
                                  src_channels != CANONICAL_CHANNELS or
                                  src_width    != CANONICAL_WIDTH)

                    if needs_norm:
                        norm_path = os.path.join(tmp_dir, f"n{idx}.wav")
                        _normalize_wav(wp, norm_path)
                        read_path = norm_path
                    else:
                        read_path = wp

                    with wave.open(read_path, 'r') as wf:
                        if not init_done:
                            out_wf.setnchannels(wf.getnchannels())
                            out_wf.setsampwidth(wf.getsampwidth())
                            out_wf.setframerate(wf.getframerate())
                            init_done = True
                        out_wf.writeframes(wf.readframes(wf.getnframes()))

                except Exception:
                    pass

        if not init_done:
            generate_silent_wav(out_path, 1.0)

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ─── FFmpeg helpers ───────────────────────────────────────────────────────────
def _find_ffmpeg():
    try:
        import static_ffmpeg
        paths = static_ffmpeg.add_paths()
        if paths and os.path.exists(paths[0]):
            return paths[0]
    except Exception:
        pass
    found = shutil.which("ffmpeg")
    if found:
        return found
    return "ffmpeg"


def _q_path(pth):
    return pth.replace("\\", "/").replace("'", "'\\''")


def _write_concat(list_path, frames):
    """frames = [(image_path, seconds), ...]  ->  ffconcat file."""
    with open(list_path, 'w', encoding='utf-8') as f:
        f.write("ffconcat version 1.0\n")
        for img, dur in frames:
            f.write(f"file '{_q_path(img)}'\n")
            f.write(f"duration {dur:.4f}\n")
        if frames:
            f.write(f"file '{_q_path(frames[-1][0])}'\n")


def _extras_graph(first_idx, base_label, tracks, logo, tag):
    """V11: filter-graph pieces that lay the animation sprites and the logo over the video.
    first_idx = ffmpeg input number of the first extra input.
    Returns (input_args, filter_chains, final_label, temp_files)."""
    inputs, chains, temp = [], [], []
    cur, idx = base_label, first_idx
    for n, tr in enumerate(tracks or []):
        lp = f"{tag}.trk{n}.txt"
        _write_concat(lp, tr['frames'])
        temp.append(lp)
        inputs += ["-f", "concat", "-safe", "0", "-i", lp]
        pf = "yuva420p" if tr.get('rgba') else "yuv420p"
        chains.append(f"[{idx}:v]format={pf},fps={_VBG_FPS},"
                      f"setpts=PTS+{tr['t0']:.4f}/TB[sp{n}]")
        nxt = f"vx{n}"
        chains.append(f"[{cur}][sp{n}]overlay={tr['x']}:{tr['y']}:format=yuv420:"
                      f"eof_action=pass[{nxt}]")
        cur, idx = nxt, idx + 1
    if logo:
        inputs += ["-loop", "1", "-framerate", str(_VBG_FPS), "-i", logo['path']]
        chains.append(f"[{idx}:v]format=yuva420p[lg]")
        chains.append(f"[{cur}][lg]overlay={logo['x']}:{logo['y']}:format=yuv420:shortest=1[vlogo]")
        cur, idx = "vlogo", idx + 1
    return inputs, chains, cur, temp


def _ffmpeg_assemble(ffmpeg_exe, imgs, durs, merged_wav, W, H, out_path,
                     tracks=None, logo=None):
    list_path = out_path + ".concat.txt"
    extra_temp = []
    try:
        _write_concat(list_path, list(zip(imgs, durs)))

        if not tracks and not logo:                   # ── original fast path (unchanged) ──
            def build(vargs):
                if merged_wav is None:                # video-only chunk
                    return [ffmpeg_exe, "-y", "-f", "concat", "-safe", "0", "-i", list_path,
                            "-vf", f"scale={W}:{H}"] + vargs + ["-an", "-threads", "0", out_path]
                return [
                    ffmpeg_exe, "-y",
                    "-f", "concat", "-safe", "0", "-i", list_path,
                    "-i", merged_wav,
                    "-vf", f"scale={W}:{H}"] + vargs + [
                    "-c:a", "aac", "-b:a", "128k",
                    "-af", "apad",
                    "-movflags", "+faststart",
                    "-threads", "0",
                    "-shortest",
                    out_path
                ]
            return _run_ffmpeg_with_fallback(ffmpeg_exe, build)

        # ── V11 path: slide images + animation sprites + logo in ONE ffmpeg pass ──
        has_a = merged_wav is not None
        ex_in, ex_chains, cur, extra_temp = _extras_graph(2 if has_a else 1, "base", tracks, logo, out_path)
        fc = ";".join([f"[0:v]scale={W}:{H},fps={_VBG_FPS},format=yuv420p[base]"] + ex_chains)
        total = sum(durs)

        def build2(vargs):
            head = [ffmpeg_exe, "-y", "-f", "concat", "-safe", "0", "-i", list_path]
            if has_a:
                head += ["-i", merged_wav]
            return (head + ex_in +
                    ["-filter_complex", fc, "-map", f"[{cur}]"] +
                    (["-map", "1:a"] if has_a else []) + vargs +
                    (["-c:a", "aac", "-b:a", "128k", "-af", "apad"] if has_a else ["-an"]) +
                    ["-movflags", "+faststart", "-threads", "0",
                     "-t", f"{total:.3f}", out_path])
        return _run_ffmpeg_with_fallback(ffmpeg_exe, build2)
    finally:
        for f in [list_path] + extra_temp:
            try: os.remove(f)
            except: pass


# ─── Background Music Mixing ───────────────────────────────────────────────
# Loops the chosen background track for the full length of the video and
# mixes it UNDER the existing voice+tick track. "normalize=0" in amix is the
# key detail: it makes amix a plain addition instead of averaging the two
# inputs down, so the voice/tick track's volume is left completely
# untouched — only the background music's own volume (via the `volume`
# filter on that single input) is adjustable. If the chosen music is
# shorter than the video, `-stream_loop -1` + `duration=first` makes it
# restart from the beginning as many times as needed to fill the video;
# if it's longer, it's simply cut off when the voice+tick track ends.
def _mix_background_music(ffmpeg_exe, merged_wav, bg_music_path, volume, out_path):
    cmd = [
        ffmpeg_exe, "-y",
        "-i", merged_wav,                       # 0: original voice + tick (untouched)
        "-stream_loop", "-1", "-i", bg_music_path,  # 1: background music (looped)
        "-filter_complex",
        f"[1:a]volume={max(0.0, min(1.0, volume)):.3f},"
        f"aformat=sample_rates=44100:channel_layouts=mono[bg];"
        f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]",
        "-map", "[aout]",
        "-ar", "44100", "-ac", "1",
        out_path
    ]
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _pick_bg_music(bg_music_files, bg_music_mode, group_idx, rng):
    """Pick exactly ONE track for this whole video — never more than one at
    a time, per the requirement. 'random' picks any track per video;
    'sequential' walks through the list in the order it was added, cycling
    back to the start once it reaches the end."""
    if not bg_music_files:
        return None
    if bg_music_mode == 'sequential':
        return bg_music_files[group_idx % len(bg_music_files)]
    return rng.choice(bg_music_files)


# ─── Video Backgrounds: planning + ffmpeg assembly ────────────────────────────
class _VideoPicker:
    """Hands out background clips one at a time.
    shuffle=False -> in the order they were added, cycling.
    shuffle=True  -> random shuffle 'bag': every clip is used once before any
                     repeats, and the same clip never plays twice in a row."""
    def __init__(self, files, shuffle):
        self.files, self.shuffle = list(files), shuffle
        self.i, self.bag, self.last = 0, [], None

    def next(self):
        if not self.shuffle:
            v = self.files[self.i % len(self.files)]
            self.i += 1
            return v
        if not self.bag:
            self.bag = self.files[:]
            random.shuffle(self.bag)
            if len(self.files) > 1 and self.bag[-1] == self.last:
                self.bag[0], self.bag[-1] = self.bag[-1], self.bag[0]
        v = self.bag.pop()
        self.last = v
        return v


def _plan_bg_videos(files, shuffle, per_question_different, per_video_different, groups):
    """Decide the background clip for every question of every output video.
    Returns a list (one entry per output video) of lists (one clip per question),
    or None when no clips were added.

    per_question_different : inside ONE output video, each question gets its own clip
                             (False = the whole video uses a single clip)
    per_video_different    : every output video gets different clip(s)
                             (False = all output videos use the same clip(s))"""
    if not files:
        return None
    picker   = _VideoPicker(files, shuffle)
    plans    = []
    template = None
    for grp in groups:
        n = len(grp)
        if not per_video_different and template is not None:
            plans.append([template[j % len(template)] for j in range(n)])
            continue
        if per_question_different:
            plan = [picker.next() for _ in range(n)]
        else:
            v = picker.next()
            plan = [v] * n
        if template is None:
            template = plan
        plans.append(plan)
    return plans


# ─── Encoder selection (GPU if available, else libx264) ──────────────────────
_SW_ENC   = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "22", "-tune", "fastdecode"]
_ENC_CACHE = {}
_ENC_LOCK  = threading.Lock()


def _pick_encoder(ffmpeg_exe):
    """Returns (is_hw, ffmpeg-args). Tries NVIDIA / AMD / Intel hardware H.264 encoders
    once (tiny test encode) and remembers the result. Falls back to libx264."""
    if not USE_GPU_ENCODER:
        return False, list(_SW_ENC)
    with _ENC_LOCK:
        if ffmpeg_exe in _ENC_CACHE:
            return _ENC_CACHE[ffmpeg_exe]
        found = (False, list(_SW_ENC))
        cands = [
            ("NVIDIA NVENC", ["-c:v", "h264_nvenc", "-preset", "p1", "-rc", "vbr",
                              "-cq", "24", "-b:v", "0"]),
            ("AMD AMF",      ["-c:v", "h264_amf", "-quality", "speed", "-rc", "cqp",
                              "-qp_i", "24", "-qp_p", "24"]),
            ("Intel QSV",    ["-c:v", "h264_qsv", "-preset", "veryfast",
                              "-global_quality", "24"]),
        ]
        for name, args in cands:
            try:
                r = subprocess.run(
                    [ffmpeg_exe, "-y", "-hide_banner", "-loglevel", "error",
                     "-f", "lavfi", "-i", "color=c=black:s=1080x1920:r=25:d=0.5"]
                    + args + ["-pix_fmt", "yuv420p", "-f", "null", "-"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25)
                if r.returncode == 0:
                    found = (True, args + ["-pix_fmt", "yuv420p"])
                    print(f"[SPEED] GPU encoder found: {name}")
                    break
            except Exception:
                continue
        _ENC_CACHE[ffmpeg_exe] = found
        return found


def _run_ffmpeg_with_fallback(ffmpeg_exe, build_cmd):
    """build_cmd(video_args) -> full command. Tries the fastest encoder first and
    silently retries with libx264 if the GPU encoder fails for any reason."""
    is_hw, vargs = _pick_encoder(ffmpeg_exe)
    res = subprocess.run(build_cmd(vargs), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode != 0 and is_hw:
        res = subprocess.run(build_cmd(list(_SW_ENC)),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return res


_VBG_FPS = 25


def _ffmpeg_assemble_video_bg(ffmpeg_exe, fg_imgs, durs, img_bgs, audio_wav,
                              W, H, out_path, work_dir, tracks=None, logo=None):
    """ONE ffmpeg pass: looping, MUTED background clip(s) underneath, the transparent
    slide frames on top, and ONLY our own voice/tick audio.
    (No intermediate re-encode of the background clips, and the overlay runs in the
    fast yuva420p path - this is what makes video-bg mode fast.)
    fg_imgs : RGBA png paths     durs : seconds per png     img_bgs : bg clip per png"""
    total = sum(durs)

    # merge consecutive frames that use the same clip into segments
    segs = []                                  # [clip_path, seconds]
    for bgp, d in zip(img_bgs, durs):
        if segs and segs[-1][0] == bgp:
            segs[-1][1] += d
        else:
            segs.append([bgp, d])

    # frame-exact segment lengths (cumulative rounding -> no drift over the video)
    seg_frames, t_acc, done = [], 0.0, 0
    for _, d in segs:
        t_acc += d
        end = int(round(t_acc * _VBG_FPS))
        n = max(1, end - done)
        done += n
        seg_frames.append(n)

    def _q(pth):
        return pth.replace("\\", "/").replace("'", "'\\''")

    fg_list = out_path + ".fg.txt"
    extra_temp = []
    try:
        with open(fg_list, 'w', encoding='utf-8') as f:
            f.write("ffconcat version 1.0\n")
            for img, dur in zip(fg_imgs, durs):
                f.write(f"file '{_q(img)}'\n")
                f.write(f"duration {dur:.4f}\n")
            if fg_imgs:
                f.write(f"file '{_q(fg_imgs[-1])}'\n")

        K = len(segs)
        inputs, chains, labels = [], [], []
        for k, ((bgp, _), nfr) in enumerate(zip(segs, seg_frames)):
            # -stream_loop -1 : repeat the clip forever;  -an : ignore the clip's own audio
            inputs += ["-an", "-stream_loop", "-1",
                       "-t", f"{nfr / _VBG_FPS + 1.0:.3f}", "-i", bgp]
            chains.append(
                f"[{k}:v]fps={_VBG_FPS},"
                f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},setsar=1,trim=end_frame={nfr},setpts=PTS-STARTPTS,"
                f"format=yuv420p[b{k}]")
            labels.append(f"[b{k}]")
        if K == 1:
            chains.append("[b0]null[bg]")
        else:
            chains.append("".join(labels) + f"concat=n={K}:v=1:a=0[bg]")
        chains.append(f"[{K}:v]format=yuva420p,fps={_VBG_FPS}[fg]")
        chains.append("[bg][fg]overlay=0:0:format=yuv420:eof_action=repeat[vbase]")
        has_a = audio_wav is not None
        if has_a:
            chains.append(f"[{K + 1}:a]apad[a]")
        # V11: animation sprites + logo on top (nothing is added when both are empty)
        ex_in, ex_chains, cur, extra_temp = _extras_graph(K + 2 if has_a else K + 1,
                                                          "vbase", tracks, logo, out_path)
        chains += ex_chains
        fc = ";".join(chains)

        def build(vargs):
            return ([ffmpeg_exe, "-y"] + inputs +
                    ["-f", "concat", "-safe", "0", "-i", fg_list] +    # transparent slide frames
                    (["-i", audio_wav] if has_a else []) + ex_in +     # voice + tick (+ bg music)
                    ["-filter_complex", fc, "-map", f"[{cur}]"] +
                    (["-map", "[a]"] if has_a else []) + vargs +
                    (["-c:a", "aac", "-b:a", "128k"] if has_a else ["-an"]) +
                    ["-movflags", "+faststart", "-threads", "0",
                     "-t", f"{total:.3f}", out_path])

        return _run_ffmpeg_with_fallback(ffmpeg_exe, build)
    finally:
        for f in [fg_list] + extra_temp:
            try: os.remove(f)
            except: pass


# ─── Long videos: build in chunks (keeps every ffmpeg command short) ──────────
# A 100-question video has ~300 animation sprite tracks and (with per-question video
# backgrounds) up to 100 background segments. Putting all of them into ONE ffmpeg command
# makes the command line longer than Windows allows (32,767 characters -> "WinError 206:
# The filename or extension is too long"). So long videos are rendered in chunks of
# a few questions each, the chunks are joined with a stream copy (no re-encode), and the
# voice/music track is attached once at the end.
_CHUNK_MAX_TRACKS = 30
_CHUNK_MAX_SEGS   = 20


def _plan_chunks(durs, img_bgs, tracks, cut_idx):
    """Split the timeline into chunks. Returns [(first_entry, last_entry_exclusive), ...].
    Cuts are only made at the start of a slide (cut_idx), so no animation is ever split."""
    n = len(durs)
    cs = [0.0] * (n + 1)
    for i, d in enumerate(durs):
        cs[i + 1] = cs[i] + d
    eps = 1e-3
    wins = [(t['t0'], t['t0'] + sum(d for _, d in t['frames'])) for t in tracks]
    cand = sorted({i for i in cut_idx if 0 < i < n and
                   not any(a + eps < cs[i] < b - eps for a, b in wins)})
    t0s = sorted(t['t0'] for t in tracks)
    import bisect
    tcount = [bisect.bisect_left(t0s, cs[i] - eps) for i in range(n + 1)]
    pref = [0] * (n + 1)                       # pref[i] = number of bg changes among entries < i
    for k in range(1, n + 1):
        pref[k] = pref[k - 1] + (1 if (k - 1 > 0 and img_bgs[k - 1] != img_bgs[k - 2]) else 0)

    def load(s, c):
        nt = tcount[c] - tcount[s]
        ns = 1 + pref[c] - pref[min(s + 1, c)]
        return nt, ns

    def fits(s, c):
        nt, ns = load(s, c)
        return nt <= _CHUNK_MAX_TRACKS and ns <= _CHUNK_MAX_SEGS

    chunks, s = [], 0
    while s < n:
        if fits(s, n):
            chunks.append((s, n))
            break
        best = None
        for c in cand:
            if c <= s:
                continue
            if fits(s, c):
                best = c
            else:
                if best is None:
                    best = c                   # a single slide group is already big: take it
                break
        if best is None:
            chunks.append((s, n))
            break
        chunks.append((s, best))
        s = best
    return chunks, cs


def _assemble_final(ffmpeg_exe, imgs, durs, img_bgs, tracks, logo, audio, W, H,
                    out_path, work_dir, use_vbg, cut_idx):
    """Builds the finished video. Small jobs: exactly one ffmpeg pass (as before).
    Big jobs: chunks + stream-copy join + one audio mux."""
    def single(i0, i1, dd, trk, aud, outp):
        if use_vbg:
            return _ffmpeg_assemble_video_bg(ffmpeg_exe, imgs[i0:i1], dd, img_bgs[i0:i1],
                                             aud, W, H, outp, work_dir,
                                             tracks=trk, logo=logo)
        return _ffmpeg_assemble(ffmpeg_exe, imgs[i0:i1], dd, aud, W, H, outp,
                                tracks=trk, logo=logo)

    chunks, cs = _plan_chunks(durs, img_bgs, tracks, cut_idx)
    if len(chunks) <= 1:
        return single(0, len(imgs), list(durs), tracks, audio, out_path)

    chunk_files, total_frames_done = [], 0
    try:
        for k, (s, c) in enumerate(chunks):
            f_end = int(round(cs[c] * _VBG_FPS))
            f_beg = int(round(cs[s] * _VBG_FPS))
            target = (f_end - f_beg) / float(_VBG_FPS)       # whole frames -> no drift
            dd = list(durs[s:c])
            dd[-1] = max(0.02, dd[-1] + (target - sum(dd)))
            trk = []
            for t in tracks:
                if cs[s] - 1e-3 <= t['t0'] < cs[c] - 1e-3:
                    t2 = dict(t)
                    t2['t0'] = max(0.0, t['t0'] - cs[s])
                    trk.append(t2)
            cp = os.path.join(work_dir, f"chunk{k:04d}.mp4")
            res = single(s, c, dd, trk, None, cp)               # video only
            if res.returncode != 0 or not os.path.exists(cp):
                return res
            chunk_files.append(cp)
            total_frames_done = f_end

        total = total_frames_done / float(_VBG_FPS)
        lst = os.path.join(work_dir, "chunks.txt")
        with open(lst, 'w', encoding='utf-8') as f:
            f.write("ffconcat version 1.0\n")
            for cp in chunk_files:
                f.write(f"file '{_q_path(cp)}'\n")
        cmd = [ffmpeg_exe, "-y", "-f", "concat", "-safe", "0", "-i", lst,
               "-i", audio, "-map", "0:v:0", "-map", "1:a:0",
               "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-af", "apad",
               "-movflags", "+faststart", "-t", f"{total:.3f}", out_path]
        return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    finally:
        for cp in chunk_files:
            try: os.remove(cp)
            except Exception: pass


# ─── V5 Per-Group Video Worker ────────────────────────────────────────────────
def _process_question_group(
    group_idx, group_q_indices, all_questions,
    formats, vi, sapi_rate, out_dir,
    tick_wav_master, ffmpeg_exe,
    show_explanation, timer_seconds, log_fn, cancel_fn,
    include_hook=True, include_end=True,
    bg_music_files=None, bg_music_volume=0.25, bg_music_mode='random',
    bg_video_plan=None
):
    """
    One worker = one group of questions -> one video PER selected format.
      * voice (TTS), slide timing and background music are made ONCE and shared by all formats
      * every format then renders its own slides (layout differs) and runs one ffmpeg pass
    V11 adds: typewriter / sliding options / live countdown (as overlay sprites), logo watermark.
    Returns (list_of_output_paths, question_numbers, seconds).
    """
    n_themes    = len(THEMES)
    q_nums      = [all_questions[idx]["number"] for idx in group_q_indices]
    group_start = time.time()
    label       = (f"Q{q_nums[0]}" if len(q_nums) == 1 else f"Q{q_nums[0]}-Q{q_nums[-1]}")

    # ── Uniqueness Engine: fresh RNG seeded from os.urandom ────────────────
    seed = int.from_bytes(os.urandom(4), 'little')
    rng  = random.Random(seed)

    # Theme selection: random, no consecutive repeats
    all_slots   = 1 + len(group_q_indices)  # hook + one per question
    slot_themes = _pick_themes_no_repeat(rng, n_themes, all_slots)
    hook_theme  = slot_themes[0]
    q_themes    = slot_themes[1:]

    try:
        group_questions = [all_questions[idx] for idx in group_q_indices]
        lang = resolve_lang(group_questions)          # 'en' or 'hi' for this video
        _TL.lang = lang
        group_questions = _prep_questions_for_lang(group_questions, lang)
        if lang == 'hi':
            log_fn(f"[HINDI] {('Q'+str(q_nums[0])) if len(q_nums)==1 else str(q_nums)} -> "
                   f"Hindi text + Hindi voice")
        slides = build_video_slides(group_questions, show_explanation,
                                    timer_seconds, hook_theme, q_themes, rng,
                                    include_hook=include_hook, include_end=include_end,
                                    lang=lang)

        with tempfile.TemporaryDirectory() as td:
            # ── STEP 1: generate all audio in parallel (ONCE for all formats) ──
            audio_files  = {}
            tts_results  = {}
            tts_threads  = []

            for i, s in enumerate(slides):
                wav_path = os.path.join(td, f"a{i}.wav")
                if s['is_tick']:
                    shutil.copy2(tick_wav_master, wav_path)
                    audio_files[i] = wav_path
                elif s.get('fixed_dur') and not s.get('speak', '').strip():
                    generate_silent_wav(wav_path, float(s['fixed_dur']))
                    audio_files[i] = wav_path
                else:
                    speak_text = s.get('speak', '') or ' '
                    t = threading.Thread(
                        target=tts_worker,
                        args=(speak_text, wav_path, vi, sapi_rate, tts_results, i,
                              s.get('lang', 'en')),
                        daemon=True)
                    tts_threads.append(t)
                    t.start()

            for t in tts_threads:
                t.join(timeout=30)

            for i, wav_path in tts_results.items():
                audio_files[i] = wav_path

            if cancel_fn():
                return [], q_nums, 0

            # ── STEP 2: slide durations (the same for every format) ────────────
            slide_durs = []
            for i, s in enumerate(slides):
                wav_path = audio_files.get(i, os.path.join(td, f"a{i}.wav"))
                if not os.path.exists(wav_path):
                    generate_silent_wav(wav_path, 1.5)

                dur = wav_duration(wav_path, 1.5)
                if s['is_tick']:
                    dur = max(dur, float(timer_seconds))
                min_dur = s.get('min_dur', 0.0)
                if min_dur and dur < min_dur:
                    padded_path = os.path.join(td, f"a{i}_padded.wav")
                    pad_secs    = min_dur - dur
                    try:
                        with wave.open(wav_path, 'r') as src_wf:
                            src_frames = src_wf.readframes(src_wf.getnframes())
                            src_rate   = src_wf.getframerate()
                            src_ch     = src_wf.getnchannels()
                            src_sw     = src_wf.getsampwidth()
                        pad_bytes = int(src_rate * pad_secs) * src_ch * src_sw
                        with wave.open(padded_path, 'w') as dst_wf:
                            dst_wf.setnchannels(src_ch)
                            dst_wf.setsampwidth(src_sw)
                            dst_wf.setframerate(src_rate)
                            dst_wf.writeframes(src_frames)
                            dst_wf.writeframes(b'\x00' * pad_bytes)
                        audio_files[i] = padded_path
                        wav_path       = padded_path
                        dur            = wav_duration(padded_path, min_dur)
                    except Exception:
                        dur = max(dur, min_dur)
                slide_durs.append(dur)

            # Pre-select a unique transition for each slide boundary (same in every format)
            trans_per_slide = [rng.choice(PREMIUM_TRANSITIONS) for _ in range(len(slides))]

            # ── STEP 3: merge WAVs (+ optional background music) - ONCE ────────
            ordered_wavs = [audio_files.get(i, os.path.join(td, f"a{i}.wav"))
                            for i in range(len(slides))]
            merged_wav = os.path.join(td, "merged_audio.wav")
            _merge_wavs(ordered_wavs, merged_wav)

            final_audio = merged_wav
            if bg_music_files:
                chosen_track = _pick_bg_music(bg_music_files, bg_music_mode,
                                              group_idx, rng)
                if chosen_track and os.path.exists(chosen_track):
                    mixed_wav = os.path.join(td, "mixed_audio.wav")
                    mix_result = _mix_background_music(
                        ffmpeg_exe, merged_wav, chosen_track,
                        bg_music_volume, mixed_wav)
                    if mix_result.returncode == 0 and os.path.exists(mixed_wav):
                        final_audio = mixed_wav
                        log_fn(f"[BGM] {os.path.basename(chosen_track)} "
                               f"@ {int(bg_music_volume*100)}% -> "
                               f"{'Q'+str(q_nums[0]) if len(q_nums)==1 else str(q_nums)}")
                    else:
                        err = mix_result.stderr[-300:].decode(errors='ignore')
                        log_fn(f"[BGM WARNING] mix failed, using original audio: {err}")

            if cancel_fn():
                return [], q_nums, 0

            use_vbg = bool(bg_video_plan) and HAS_NUMPY

            # ── STEP 4: one finished video per format ─────────────────────────
            def _build_format(fmt):
                fmt_start = time.time()
                W, H, portrait = fmt['W'], fmt['H'], fmt['portrait']
                tag = fmt['key']
                fd  = os.path.join(td, f"f_{tag}")
                os.makedirs(fd, exist_ok=True)
                _TL.lang = lang                       # (thread-local) needed for footer / logo maths

                imgs, durs, img_bgs, tracks = [], [], [], []
                slide_starts = []
                prev_img = None

                for i, s in enumerate(slides):
                    if cancel_fn():
                        return None
                    slide_starts.append(len(imgs))
                    dur    = slide_durs[i]
                    cur_bg = None
                    if use_vbg:
                        cur_bg = bg_video_plan[min(s.get('qi', 0), len(bg_video_plan) - 1)]

                    # Does this slide get an animation?
                    kind = None
                    if s['type'] == 'entrance' and (ANIM_CFG.get('typewriter') or ANIM_CFG.get('options')):
                        kind = 'entrance'
                    elif s['type'] == 'timer' and ANIM_CFG.get('countdown'):
                        kind = 'timer'

                    # Render main slide image (+ the clean regions the animation needs)
                    cap = None
                    if kind:
                        if use_vbg:
                            slide_img, cap = render_slide_matte(s, W, H, portrait, want_cap=True)
                        else:
                            slide_img, cap = render_slide_with_cap(s, W, H, portrait)
                    elif use_vbg:
                        slide_img = render_slide_matte(s, W, H, portrait)   # (premult, alpha)
                    else:
                        slide_img = render_slide(s, W, H, portrait)
                    base = _MImg.from_std(slide_img)

                    has_tr = prev_img is not None and dur > _TRANS_TOTAL_DUR * 2.0
                    still  = max(0.3, dur - _TRANS_TOTAL_DUR) if has_tr else dur

                    plan = None
                    try:
                        if kind == 'entrance':
                            plan = _plan_entrance_anim(cap, use_vbg, W, still)
                        elif kind == 'timer':
                            plan = _plan_timer_anim(cap, use_vbg, still, timer_seconds)
                    except Exception as e:
                        log_fn(f"[ANIM] animation skipped for a slide ({e})")
                        plan = None

                    # ── Cinematic transition into this slide ───────────────
                    if has_tr:
                        curr = _compose(base, plan['start_items']).std() if plan else slide_img
                        trans_type = trans_per_slide[i]
                        if use_vbg:
                            trans_frames = _render_transition_frames_rgba(
                                prev_img, curr, trans_type, _N_TRANS_FRAMES)
                        else:
                            trans_frames = _render_transition_frames(
                                prev_img, curr, trans_type, _N_TRANS_FRAMES)
                        for j, tf in enumerate(trans_frames):
                            if use_vbg:
                                tf_path = os.path.join(fd, f"tr{i}_{j}.png")
                                tf.save(tf_path, 'PNG', compress_level=1)
                            else:
                                tf_path = os.path.join(fd, f"tr{i}_{j}.jpg")
                                tf.save(tf_path, 'JPEG', quality=88)
                            imgs.append(tf_path)
                            durs.append(_TRANS_FRAME_DUR)
                            img_bgs.append(cur_bg)
                        dur = still

                    # ── animation sprites for this slide ───────────────────
                    if plan:
                        t0 = sum(durs)                      # still part starts here
                        for tn, trk in enumerate(plan['tracks']):
                            frames = _save_track(trk, use_vbg, fd, f"sp{i}_{tn}")
                            tracks.append({'x': trk['reg'].x, 'y': trk['reg'].y,
                                           't0': t0, 'frames': frames, 'rgba': use_vbg})

                    # ── the slide's still image ────────────────────────────
                    if use_vbg:
                        still_img = base
                        if plan:                            # transparent holes; sprites fill them
                            still_img = base.copy()
                            for reg in plan['regions']:
                                still_img.clear(reg.box)
                        img_path = os.path.join(fd, f"s{i}.png")
                        still_img.sprite().save(img_path, 'PNG', compress_level=1)
                    else:
                        img_path = os.path.join(fd, f"s{i}.jpg")
                        base.c.save(img_path, 'JPEG', quality=92)
                    imgs.append(img_path)
                    durs.append(dur)
                    img_bgs.append(cur_bg)

                    # what the NEXT transition starts from = the slide's end state
                    prev_img = (_compose(base, plan['end_items']).std() if plan else slide_img)

                if cancel_fn():
                    return None

                # logo (round watermark) for this format
                logo = None
                if LOGO_CFG.get('enabled') and LOGO_CFG.get('path') and os.path.exists(LOGO_CFG['path']):
                    logo = _prepare_logo(LOGO_CFG['path'], LOGO_CFG.get('position', 'bottom-right'),
                                         W, H, fd, log_fn)

                # output filename
                dest_dir = os.path.join(out_dir, fmt['subdir']) if fmt.get('subdir') else out_dir
                os.makedirs(dest_dir, exist_ok=True)
                suffix = f"_{tag}" if fmt.get('subdir') else ""
                if len(q_nums) == 1:
                    out_path = os.path.join(dest_dir, f"Question_{q_nums[0]}_video{suffix}.mp4")
                else:
                    out_path = os.path.join(dest_dir,
                        f"Quiz_Q{q_nums[0]}_to_Q{q_nums[-1]}_video{suffix}.mp4")

                # FFmpeg - one pass: slides (+ video bg) + sprites + logo + audio
                if use_vbg:
                    names = sorted({os.path.basename(x) for x in img_bgs if x})
                    log_fn(f"[VIDEO BG] {', '.join(names)} -> {label}")
                result = _assemble_final(ffmpeg_exe, imgs, durs, img_bgs, tracks, logo,
                                         final_audio, W, H, out_path, fd, use_vbg,
                                         slide_starts)
                took = time.time() - fmt_start
                fl   = f"{label} [{fmt['key']} {W}x{H}]"
                if result.returncode == 0:
                    extra = []
                    if tracks: extra.append(f"{len(tracks)} animation tracks")
                    if logo:   extra.append("logo")
                    log_fn(f"[OK] {fl} done in {took:.1f}s  ({len(slides)} slides"
                           f"{', ' + ', '.join(extra) if extra else ''})  -> {os.path.basename(out_path)}")
                    return out_path
                err = result.stderr[-400:].decode(errors='ignore')
                log_fn(f"[ERROR] {fl} FFmpeg failed ({took:.1f}s): {err}")
                return None

            def _build_format_safe(fmt, use_sem):
                try:
                    if use_sem:
                        with _RENDER_SEM:
                            return _build_format(fmt)
                    return _build_format(fmt)
                except Exception as e:
                    import traceback
                    log_fn(f"[ERROR] {label} [{fmt['key']}] crashed: {e}")
                    log_fn(traceback.format_exc())
                    return None

            if len(formats) == 1:
                outs = [_build_format_safe(formats[0], False)]
            else:
                # several formats: build them side by side (limited by _RENDER_SEM)
                with concurrent.futures.ThreadPoolExecutor(max_workers=len(formats)) as fp:
                    outs = list(fp.map(lambda f: _build_format_safe(f, True), formats))

            out_paths = [o for o in outs if o]
            return out_paths, q_nums, time.time() - group_start

    except Exception as e:
        log_fn(f"[ERROR] Group {q_nums} crashed: {e}")
        import traceback
        log_fn(traceback.format_exc())
        return [], q_nums, time.time() - group_start


