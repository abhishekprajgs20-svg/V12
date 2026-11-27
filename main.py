"""TXT 2 SHORTS V12 — Android companion UI for the original V12 renderer."""
import os, sys, math, time, shutil, tempfile, threading, concurrent.futures, platform
from pathlib import Path
import subprocess

try:                                   # CA bundle for the online (Edge) voice
    import certifi
    os.environ.setdefault('SSL_CERT_FILE', certifi.where())
    os.environ.setdefault('REQUESTS_CA_BUNDLE', certifi.where())
except Exception:
    pass

IS_ANDROID = 'ANDROID_ARGUMENT' in os.environ or os.path.exists('/system/build.prop')

from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import StringProperty, NumericProperty, BooleanProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.checkbox import CheckBox
from kivy.uix.spinner import Spinner
from kivy.uix.slider import Slider
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout

try:
    from plyer import filechooser
except Exception:
    filechooser = None

import engine_v12 as engine

KV = r'''
#:import dp kivy.metrics.dp
<DarkButton@Button>:
    background_normal: ''
    background_down: ''
    background_color: (0.02,0.78,0.76,1) if self.state == 'normal' else (0.0,0.55,0.55,1)
    color: (0.03,0.06,0.10,1)
    bold: True
    size_hint_y: None
    height: dp(46)
<DarkLabel@Label>:
    color: (0.91,0.94,0.98,1)
    size_hint_y: None
    height: self.texture_size[1] + dp(12)
    text_size: self.width, None
    halign: 'left'
    valign: 'middle'
<Panel@BoxLayout>:
    orientation: 'vertical'
    size_hint_y: None
    height: self.minimum_height
    padding: dp(12)
    spacing: dp(8)
    canvas.before:
        Color:
            rgba: (0.08,0.11,0.17,1)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(14)]
<RootUI>:
    orientation: 'vertical'
    spacing: dp(8)
    padding: dp(10)
    canvas.before:
        Color:
            rgba: (0.035,0.05,0.09,1)
        Rectangle:
            pos: self.pos
            size: self.size
    BoxLayout:
        size_hint_y: None
        height: dp(54)
        orientation: 'vertical'
        DarkLabel:
            text: '[b][color=00CEC9]TXT 2 SHORTS V12[/color]  MOBILE[/b]'
            markup: True
            font_size: '20sp'
            height: dp(30)
        Label:
            text: 'Premium Cinematic Quiz Video Generator'
            color: (0.58,0.66,0.76,1)
            font_size: '11sp'
    ScrollView:
        do_scroll_x: False
        GridLayout:
            id: content
            cols: 1
            spacing: dp(9)
            size_hint_y: None
            height: self.minimum_height
            Panel:
                DarkLabel:
                    text: '[b]01 · INPUT[/b]'
                    markup: True
                DarkButton:
                    id: input_btn
                    text: root.input_label
                    on_release: root.pick_input()
                DarkLabel:
                    id: question_count
                    text: root.question_summary
            Panel:
                DarkLabel:
                    text: '[b]02 · OUTPUT & VOICE[/b]'
                    markup: True
                DarkLabel:
                    text: 'Output folder: videos (inside app storage)'
                DarkLabel:
                    text: 'Language mode'
                Spinner:
                    id: language
                    text: 'Auto-detect (per video)'
                    values: ['Auto-detect (per video)','English','Hindi']
                    size_hint_y: None
                    height: dp(44)
                DarkLabel:
                    text: 'Voice engine (Android uses Edge Neural online)'
                Spinner:
                    id: voice_engine
                    text: 'Edge Neural (online)'
                    values: ['Edge Neural (online)']
                    size_hint_y: None
                    height: dp(44)
                DarkLabel:
                    text: 'Hindi Neural voice'
                Spinner:
                    id: hindi_voice
                    text: 'Madhur · Male'
                    values: ['Madhur · Male','Swara · Female']
                    size_hint_y: None
                    height: dp(44)
                DarkLabel:
                    text: 'English Neural voice'
                Spinner:
                    id: english_voice
                    text: 'Prabhat · Male (India)'
                    values: ['Prabhat · Male (India)','Neerja · Female (India)','Aria · Female (US)','Guy · Male (US)']
                    size_hint_y: None
                    height: dp(44)
                DarkLabel:
                    text: 'Speech speed: ' + str(round(root.speed,1)) + 'x'
                Slider:
                    id: speed
                    min: 0.5
                    max: 2.5
                    value: 1.0
                    on_value: root.speed = self.value
                    size_hint_y: None
                    height: dp(34)
                DarkLabel:
                    text: 'Single output resolution'
                Spinner:
                    id: resolution
                    text: '1080x1920 (Portrait 9:16 Shorts)'
                    values: ['1080x1920 (Portrait 9:16 Shorts)','1920x1080 (Landscape 16:9)','1280x720 (Landscape 16:9 HD)']
                    size_hint_y: None
                    height: dp(44)
                DarkLabel:
                    text: 'Rendering workers (Auto adapts to phone RAM)' 
                Spinner:
                    id: workers
                    text: 'Auto — Recommended'
                    values: ['Auto — Recommended','1 — Safe','2 — Fast']
                    size_hint_y: None
                    height: dp(44)
            Panel:
                DarkLabel:
                    text: '[b]03 · VIDEO SETTINGS[/b]'
                    markup: True
                DarkLabel:
                    text: 'Questions per video'
                Spinner:
                    id: qpv
                    text: '1'
                    values: ['1','3','5','10','15','20','Custom 30','Custom 50','Custom 100','Custom 200']
                    size_hint_y: None
                    height: dp(44)
                DarkLabel:
                    text: 'Countdown duration (3–120 seconds)'
                Spinner:
                    id: timer
                    text: '10'
                    values: ['5','7','10','15','20','30','45','60','90','120']
                    size_hint_y: None
                    height: dp(44)
                DarkLabel:
                    text: 'Text size: ' + str(int(root.text_scale)) + '%'
                Slider:
                    id: text_scale
                    min: 80
                    max: 200
                    step: 5
                    value: 125
                    on_value: root.text_scale = self.value
                    size_hint_y: None
                    height: dp(34)
                DarkLabel:
                    text: '55+ original themes · random per-slide selection (V12 uniqueness engine)'
                DarkLabel:
                    text: 'Enable / disable original slide elements'
                CheckBoxLine:
                    id: explanations
                    text: 'Show explanation slides'
                    active: True
                CheckBoxLine:
                    id: intro
                    text: 'Include cinematic intro'
                    active: True
                CheckBoxLine:
                    id: outro
                    text: 'Include cinematic outro'
                    active: True
            Panel:
                DarkLabel:
                    text: '[b]04 · V11 PRO ANIMATIONS[/b]'
                    markup: True
                CheckBoxLine:
                    id: typewriter
                    text: 'Typewriter question animation'
                    active: True
                CheckBoxLine:
                    id: options_anim
                    text: 'Options slide in one-by-one'
                    active: True
                CheckBoxLine:
                    id: countdown_anim
                    text: 'Animated countdown ring and number'
                    active: True
                CheckBoxLine:
                    id: multi_format
                    text: 'Export multiple formats in one run'
                    active: False
                DarkLabel:
                    text: 'Select formats (used when multi-format is ON)'
                CheckBoxLine:
                    id: f_9x16
                    text: '9:16 · Shorts / Reels / TikTok (1080×1920)'
                    active: True
                CheckBoxLine:
                    id: f_4x5
                    text: '4:5 · Instagram portrait (1080×1350)'
                CheckBoxLine:
                    id: f_1x1
                    text: '1:1 · Square (1080×1080)'
                CheckBoxLine:
                    id: f_4x3
                    text: '4:3 · Classic (1440×1080)'
                CheckBoxLine:
                    id: f_16x9
                    text: '16:9 · YouTube (1920×1080)'
                CheckBoxLine:
                    id: f_16x9hd
                    text: '16:9 HD (1280×720)'
                CheckBoxLine:
                    id: f_2x3
                    text: '2:3 · Pinterest (1000×1500)'
                CheckBoxLine:
                    id: logo_enabled
                    text: 'Show round logo watermark'
                DarkButton:
                    text: 'Choose logo image'
                    on_release: root.pick_logo()
                DarkLabel:
                    id: logo_label
                    text: root.logo_name
                Spinner:
                    id: logo_pos
                    text: 'bottom-right'
                    values: ['bottom-right','bottom-left']
                    size_hint_y: None
                    height: dp(44)
            Panel:
                DarkLabel:
                    text: '[b]05 · BACKGROUND MUSIC[/b]'
                    markup: True
                DarkButton:
                    text: '+ Add MP3 / WAV music'
                    on_release: root.pick_music()
                DarkLabel:
                    id: music_list
                    text: root.music_summary
                DarkLabel:
                    text: 'Music volume: ' + str(int(root.music_volume)) + '%'
                Slider:
                    id: music_volume
                    min: 0
                    max: 100
                    step: 5
                    value: 25
                    on_value: root.music_volume = self.value
                    size_hint_y: None
                    height: dp(34)
                Spinner:
                    id: music_mode
                    text: 'Random — one track per video'
                    values: ['Random — one track per video','In order added']
                    size_hint_y: None
                    height: dp(44)
                DarkButton:
                    text: 'Clear music list'
                    on_release: root.clear_music()
            Panel:
                DarkLabel:
                    text: '[b]06 · VIDEO BACKGROUNDS[/b]'
                    markup: True
                DarkButton:
                    text: '+ Add MP4 background clips'
                    on_release: root.pick_backgrounds()
                DarkLabel:
                    id: video_list
                    text: root.video_summary
                Spinner:
                    id: bg_order
                    text: 'Same sequence (as added)'
                    values: ['Same sequence (as added)','Random shuffle']
                    size_hint_y: None
                    height: dp(44)
                Spinner:
                    id: bg_perq
                    text: 'Different clip for each question'
                    values: ['Different clip for each question','One clip for the whole video']
                    size_hint_y: None
                    height: dp(44)
                Spinner:
                    id: bg_pervid
                    text: 'Different clip in each video'
                    values: ['Different clip in each video','Same clip in every video']
                    size_hint_y: None
                    height: dp(44)
                DarkButton:
                    text: 'Clear video backgrounds'
                    on_release: root.clear_backgrounds()
            Panel:
                DarkLabel:
                    text: '[b]07 · GENERATION[/b]'
                    markup: True
                DarkLabel:
                    id: status
                    text: root.status_text
                ProgressBar:
                    id: progress
                    max: 1
                    value: root.progress_value
                    size_hint_y: None
                    height: dp(12)
                DarkButton:
                    id: start
                    text: 'GENERATE VIDEOS'
                    on_release: root.start_render()
                Button:
                    id: cancel
                    text: 'Cancel generation'
                    disabled: True
                    size_hint_y: None
                    height: dp(42)
                    on_release: root.cancel_render()
                DarkLabel:
                    text: 'Generated videos are saved in the app Videos folder.'
                DarkButton:
                    text: 'Copy generated videos to phone Gallery / Movies'
                    on_release: root.export_to_gallery()
                TextInput:
                    id: logs
                    text: root.log_text
                    readonly: True
                    multiline: True
                    size_hint_y: None
                    height: dp(180)
                    background_color: (0.02,0.03,0.06,1)
                    foreground_color: (0.72,0.88,0.92,1)
                    font_size: '11sp'
                    padding: dp(8)
'''

Builder.load_string(KV)

from kivy.factory import Factory
class CheckBoxLine(BoxLayout):
    text = StringProperty('')
    active = BooleanProperty(False)
    def __init__(self, **kwargs):
        super().__init__(orientation='horizontal', size_hint_y=None, height=dp(38), spacing=dp(8), **kwargs)
        self.add_widget(CheckBox(active=self.active, size_hint=(None,1), width=dp(38), on_active=self._changed))
        self.lbl = Label(text=self.text, color=(.9,.93,.97,1), halign='left', valign='middle')
        self.lbl.bind(size=lambda w,s: setattr(w,'text_size',s))
        self.add_widget(self.lbl)
    def _changed(self, inst, val): self.active = val
    def on_text(self, *_):
        if hasattr(self,'lbl'): self.lbl.text=self.text
    def on_active(self, *_):
        if self.children and isinstance(self.children[-1], CheckBox): self.children[-1].active=self.active
Factory.register('CheckBoxLine', cls=CheckBoxLine)

class RootUI(BoxLayout):
    input_label = StringProperty('Choose your .TXT question file')
    question_summary = StringProperty('No file selected · 0 questions parsed')
    status_text = StringProperty('Ready · Waiting for input')
    progress_value = NumericProperty(0)
    log_text = StringProperty('')
    speed = NumericProperty(1.0)
    text_scale = NumericProperty(125)
    music_volume = NumericProperty(25)
    logo_name = StringProperty('No logo selected')
    music_summary = StringProperty('No background music added')
    video_summary = StringProperty('No video backgrounds added · original gradient backgrounds will be used')
    theme_names = [t['name'] for t in engine.THEMES]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.input_path = ''
        self.logo_path = ''
        self.music_files = []
        self.video_files = []
        self.questions = []
        self.cancel_flag = False
        self._render_thread = None
        self.output_files = []
        self.output_dir = os.path.join(App.get_running_app().user_data_dir, 'videos')
        os.makedirs(self.output_dir, exist_ok=True)
        self.total_ram_gb = self._detect_total_ram_gb()
        self.recommended_workers = 2 if self.total_ram_gb >= 8 else 1
        self.ffmpeg = self._locate_ffmpeg()
        if self.ffmpeg:
            self._log('[SYSTEM] FFmpeg engine found: ' + self.ffmpeg)
        else:
            self._log('[SYSTEM] FFmpeg could not be started. Rebuild the APK with the included GitHub workflow.')
        self._log(f'[DEVICE] Detected RAM: {self.total_ram_gb:.1f} GB · recommended render workers: {self.recommended_workers}')
        self._log(f'[SYSTEM] {len(engine.THEMES)} premium themes and {len(engine.PREMIUM_TRANSITIONS)} transitions loaded.')
        self._log('[SYSTEM] Original V12 renderer module loaded; Windows-only UI/SAPI layer replaced for Android.')

    def _detect_total_ram_gb(self):
        # Linux/Android exposes total physical RAM through /proc/meminfo.
        try:
            with open('/proc/meminfo', 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('MemTotal:'):
                        return int(line.split()[1]) / 1024 / 1024
        except Exception:
            pass
        return 4.0  # conservative fallback for unknown devices

    def _locate_ffmpeg(self):
        """Android: FFmpeg ships as libffmpegbin.so inside the native-library folder (the only place
        Android 10+ lets an app execute a file from).  Desktop test: system ffmpeg."""
        cands = []
        if IS_ANDROID:
            try:
                from jnius import autoclass
                act = autoclass('org.kivy.android.PythonActivity').mActivity
                cands.append(os.path.join(str(act.getApplicationInfo().nativeLibraryDir), 'libffmpegbin.so'))
            except Exception as exc:
                self._log('[FFMPEG] nativeLibraryDir lookup failed: ' + repr(exc))
            app_files = os.environ.get('ANDROID_ARGUMENT', '')
            cands.append(os.path.join(os.path.dirname(os.path.dirname(app_files)) if app_files else '', 'lib', 'libffmpegbin.so'))
        else:
            cands.append(shutil.which('ffmpeg') or '')
        for c in cands:
            if c and os.path.isfile(c):
                try:
                    r = subprocess.run([c, '-hide_banner', '-version'], stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, timeout=20)
                    if r.returncode == 0:
                        return c
                    self._log('[FFMPEG] test run failed: ' + r.stdout.decode(errors='ignore')[:200])
                except Exception as exc:
                    self._log('[FFMPEG] cannot execute ' + c + ': ' + repr(exc))
        return None

    def _log(self, message):
        def add(_dt):
            self.log_text = (self.log_text + str(message) + '\n')[-18000:]
            if 'logs' in self.ids:
                self.ids.logs.text = self.log_text
        Clock.schedule_once(add, 0)

    def _popup(self, title, message):
        box = BoxLayout(orientation='vertical', padding=dp(12), spacing=dp(10))
        box.add_widget(Label(text=message, color=(.92,.94,.98,1)))
        btn = Button(text='OK', size_hint_y=None, height=dp(44))
        box.add_widget(btn)
        pop = Popup(title=title, content=box, size_hint=(.88,.42))
        btn.bind(on_release=pop.dismiss); pop.open()

    def _pick(self, callback, filters, mime='*/*', multiple=False):
        if IS_ANDROID:
            try:
                from androidstorage4kivy import Chooser
                def cb(uris):
                    def work(dt):
                        paths = []
                        try:
                            from androidstorage4kivy import SharedStorage
                            ss = SharedStorage()
                            for u in uris or []:
                                pth = ss.copy_from_shared(u)
                                if pth: paths.append(pth)
                        except Exception as exc:
                            self._log('[PICKER] ' + repr(exc))
                        callback(paths)
                    Clock.schedule_once(work, 0)
                self._chooser = Chooser(cb)
                self._chooser.choose_content(mime, multiple=multiple)
                return
            except Exception as exc:
                self._log('[PICKER] Android chooser failed: ' + repr(exc))
        if filechooser is None:
            self._popup('File picker unavailable', 'No file picker available in this build.')
            return
        try:
            filechooser.open_file(on_selection=callback, filters=filters, multiple=multiple)
        except TypeError:
            filechooser.open_file(on_selection=callback, filters=filters)

    def pick_input(self): self._pick(self._got_input, ['*.txt'], '*/*')
    def _got_input(self, selection):
        if not selection: return
        p = selection[0]
        try:
            self.input_path = self._copy_if_needed(p, 'input.txt')
            self.questions = engine.parse_input_file(self.input_path)
            self.input_label = os.path.basename(self.input_path)
            self.question_summary = f'{len(self.questions)} questions parsed'
            self.output_dir = os.path.join(App.get_running_app().user_data_dir, 'videos')
            self._log(f'[INFO] Parsed {len(self.questions)} questions from {self.input_label}')
            if not self.questions: self._popup('No questions found', 'The selected TXT did not contain valid Q1, Q2... blocks.')
        except Exception as e:
            self._popup('Input error', str(e)); self._log('[ERROR] '+str(e))

    def _copy_if_needed(self, path, name):
        path = str(path)
        if path.startswith('content://'):
            raise RuntimeError('Picker returned a content URI that could not be copied. Try another file manager.')
        if os.path.exists(path):
            dest = os.path.join(App.get_running_app().user_data_dir, name)
            if os.path.abspath(path) != os.path.abspath(dest): shutil.copy2(path, dest)
            return dest
        raise FileNotFoundError(path)

    def pick_logo(self): self._pick(self._got_logo, ['*.png','*.jpg','*.jpeg','*.webp','*.bmp'], 'image/*')
    def _got_logo(self, selection):
        if selection:
            try:
                self.logo_path=self._copy_if_needed(selection[0], 'watermark_logo'+Path(selection[0]).suffix)
                self.logo_name=os.path.basename(self.logo_path); self.ids.logo_enabled.active=True
            except Exception as e: self._popup('Logo error', str(e))

    def pick_music(self): self._pick(self._got_music, ['*.mp3','*.wav','*.m4a'], 'audio/*', True)
    def _got_music(self, selection):
        for i,p in enumerate(selection or []):
            try:
                dst=self._copy_if_needed(p, f'music_{len(self.music_files)+i}'+Path(p).suffix)
                if dst not in self.music_files: self.music_files.append(dst)
            except Exception as e: self._log('[MUSIC] '+str(e))
        self.music_summary='\n'.join(os.path.basename(x) for x in self.music_files) or 'No background music added'
        self.ids.music_list.text=self.music_summary

    def pick_backgrounds(self): self._pick(self._got_backgrounds, ['*.mp4','*.mov','*.mkv','*.webm','*.avi','*.m4v'], 'video/*', True)
    def _got_backgrounds(self, selection):
        for i,p in enumerate(selection or []):
            try:
                dst=self._copy_if_needed(p, f'video_bg_{len(self.video_files)+i}'+Path(p).suffix)
                if dst not in self.video_files: self.video_files.append(dst)
            except Exception as e: self._log('[VIDEO BG] '+str(e))
        self.video_summary='\n'.join(os.path.basename(x) for x in self.video_files) or 'No video backgrounds added'
        self.ids.video_list.text=self.video_summary

    def clear_music(self):
        self.music_files=[]; self.music_summary='No background music added'; self.ids.music_list.text=self.music_summary
    def clear_backgrounds(self):
        self.video_files=[]; self.video_summary='No video backgrounds added · original gradient backgrounds will be used'; self.ids.video_list.text=self.video_summary

    def _spinner_qpv(self):
        val=self.ids.qpv.text
        if val.startswith('Custom '): return int(val.split()[1])
        return int(val)

    def start_render(self):
        if self._render_thread and self._render_thread.is_alive(): return
        if not self.questions:
            self._popup('Select input', 'Choose a valid TXT file first.'); return
        if not self.ffmpeg:
            self._popup('FFmpeg missing', 'This APK is missing its matching Android ARM FFmpeg executable. Rebuild it using the included GitHub Actions workflow; desktop FFmpeg binaries cannot run on Android.')
            return
        if self.ids.logo_enabled.active and not self.logo_path:
            self._popup('Logo missing','Choose a logo image or turn off the watermark.'); return
        if self.ids.multi_format.active:
            keys=['9x16','4x5','1x1','4x3','16x9','16x9_hd','2x3']
            ids=['f_9x16','f_4x5','f_1x1','f_4x3','f_16x9','f_16x9hd','f_2x3']
            chosen=[k for k,i in zip(keys,ids) if self.ids[i].active]
            if not chosen: self._popup('No format selected','Tick at least one output format.'); return
        self.cancel_flag=False
        self.ids.start.disabled=True; self.ids.cancel.disabled=False
        self.progress_value=0; self.status_text='Preparing video engine…'
        self._keep_awake(True)
        self._render_thread=threading.Thread(target=self._render, daemon=True)
        self._render_thread.start()

    def cancel_render(self):
        self.cancel_flag=True; self.status_text='Cancelling after current render step…'; self._log('[SYSTEM] Cancel requested.')

    def _render(self):
        started=time.time(); total_ok=0
        try:
            eng=engine
            eng._LOG_FN=self._log
            eng.FFMPEG_EXE=self.ffmpeg
            eng.USE_GPU_ENCODER=False
            eng.FORCE_LANG={'English':'en','Hindi':'hi'}.get(self.ids.language.text,'auto')
            eng.TTS_CFG['engine']='edge'
            eng.TTS_CFG['speed']=float(self.speed)
            eng.TTS_CFG['hi_edge_voice']='hi-IN-SwaraNeural' if self.ids.hindi_voice.text.startswith('Swara') else 'hi-IN-MadhurNeural'
            voice_map={'Prabhat · Male (India)':'en-IN-PrabhatNeural','Neerja · Female (India)':'en-IN-NeerjaNeural','Aria · Female (US)':'en-US-AriaNeural','Guy · Male (US)':'en-US-GuyNeural'}
            eng.TTS_CFG['en_edge_voice']=voice_map.get(self.ids.english_voice.text,'en-IN-PrabhatNeural')
            eng.TEXT_SCALE=max(.5,min(3.0,float(self.text_scale)/100.0))
            eng.ANIM_CFG.update(typewriter=self.ids.typewriter.active, options=self.ids.options_anim.active, countdown=self.ids.countdown_anim.active)
            eng.LOGO_CFG.update(enabled=self.ids.logo_enabled.active, path=self.logo_path, position=self.ids.logo_pos.text)
            if self.ids.multi_format.active:
                keys=['9x16','4x5','1x1','4x3','16x9','16x9_hd','2x3']
                formats=[dict(key=k,label=next(x[1] for x in eng.OUTPUT_FORMATS if x[0]==k),W=next(x[2] for x in eng.OUTPUT_FORMATS if x[0]==k),H=next(x[3] for x in eng.OUTPUT_FORMATS if x[0]==k),portrait=next(x[3] for x in eng.OUTPUT_FORMATS if x[0]==k)>=next(x[2] for x in eng.OUTPUT_FORMATS if x[0]==k),subdir=k) for k,i in zip(keys,['f_9x16','f_4x5','f_1x1','f_4x3','f_16x9','f_16x9hd','f_2x3']) if self.ids[i].active]
            else:
                rs=self.ids.resolution.text; W,H=map(int,rs.split(' ')[0].split('x'))
                formats=[dict(key='single',label=rs,W=W,H=H,portrait=H>W,subdir=None)]
            qpv=self._spinner_qpv(); timer=max(3,min(120,int(self.ids.timer.text)))
            groups=[list(range(i,min(i+qpv,len(self.questions)))) for i in range(0,len(self.questions),qpv)]
            bg_plans=None
            if self.video_files:
                bg_plans=eng._plan_bg_videos(self.video_files, self.ids.bg_order.text=='Random shuffle', self.ids.bg_perq.text.startswith('Different'), self.ids.bg_pervid.text.startswith('Different'), groups)
            os.makedirs(self.output_dir,exist_ok=True)
            with tempfile.TemporaryDirectory(dir=App.get_running_app().user_data_dir) as td:
                tick=os.path.join(td,'tick_master.wav'); eng.generate_ticking_audio(tick,duration_sec=float(timer)+1)
                worker_choice=self.ids.workers.text
                workers=self.recommended_workers if worker_choice.startswith('Auto') else (1 if worker_choice.startswith('1') else 2)
                eng._RENDER_SEM=threading.Semaphore(workers)
                eng._log if hasattr(eng,'_log') else None
                self._log(f'[START] {len(self.questions)} questions → {len(groups)} video group(s), {len(formats)} format(s), timer={timer}s, workers={workers}')
                for gi,grp in enumerate(groups):
                    if self.cancel_flag: break
                    outs, nums, elapsed=eng._process_question_group(
                        gi,grp,self.questions,formats,0,0,self.output_dir,tick,self.ffmpeg,
                        self.ids.explanations.active,timer,self._log,lambda:self.cancel_flag,
                        self.ids.intro.active,self.ids.outro.active,
                        self.music_files,float(self.music_volume)/100.0,
                        'sequential' if self.ids.music_mode.text=='In order added' else 'random',
                        bg_plans[gi] if bg_plans else None)
                    total_ok+=len(outs)
                    self.output_files.extend([x for x in outs if x and os.path.isfile(x)])
                    Clock.schedule_once(lambda dt,p=(gi+1)/len(groups): self._set_progress(p),0)
                    self._log(f'[DONE] Group {gi+1}/{len(groups)} · {len(outs)} output(s) · {elapsed:.1f}s')
            duration=time.time()-started
            self._log(f'[COMPLETE] {total_ok} video file(s) created in {duration:.1f}s. Folder: {self.output_dir}')
            Clock.schedule_once(lambda dt:self._finish(total_ok,duration),0)
        except Exception as e:
            self._log('[FATAL] '+repr(e))
            Clock.schedule_once(lambda dt:self._fail(str(e)),0)

    def _keep_awake(self, on):
        if not IS_ANDROID: return
        try:
            from jnius import autoclass
            from android.runnable import run_on_ui_thread
            LP = autoclass('android.view.WindowManager$LayoutParams')
            act = autoclass('org.kivy.android.PythonActivity').mActivity
            @run_on_ui_thread
            def f():
                w = act.getWindow()
                (w.addFlags if on else w.clearFlags)(LP.FLAG_KEEP_SCREEN_ON)
            f()
        except Exception as exc:
            self._log('[SYSTEM] keep-awake unavailable: ' + repr(exc))

    def export_to_gallery(self, quiet=False):
        if not self.output_files:
            if quiet: return
            self._popup('No videos yet', 'Generate at least one video first.')
            return
        try:
            from androidstorage4kivy import SharedStorage
            from jnius import autoclass
            Environment = autoclass('android.os.Environment')
            ss = SharedStorage()
            copied = 0
            for path in self.output_files:
                if os.path.isfile(path) and ss.copy_to_shared(path, collection=Environment.DIRECTORY_MOVIES):
                    copied += 1
            if not quiet: self._popup('Export finished', f'{copied} video(s) copied to Movies on your phone.')
            self._log(f'[EXPORT] {copied}/{len(self.output_files)} video(s) copied to shared Movies storage.')
        except Exception as exc:
            if quiet:
                self._log('[EXPORT] ' + repr(exc)); return
            self._popup('Gallery export unavailable', 'Could not export to the phone Gallery. Check the androidstorage4kivy Android build dependency.\n\n' + str(exc))

    def _set_progress(self,p):
        self.progress_value=p; self.status_text=f'Generating… {int(p*100)}%'
    def _finish(self,n,secs):
        self._keep_awake(False)
        if IS_ANDROID: self.export_to_gallery(quiet=True)
        self.ids.start.disabled=False; self.ids.cancel.disabled=True
        self.status_text=f'Complete · {n} video file(s) · {secs:.1f}s'
        self._popup('Generation complete',f'{n} video file(s) generated.\n\nCopied to Movies in your Gallery (and kept in app storage).')
    def _fail(self,msg):
        self._keep_awake(False)
        self.ids.start.disabled=False; self.ids.cancel.disabled=True; self.status_text='Generation failed'
        self._popup('Generation failed',msg)

class Txt2ShortsAndroid(App):
    title='TXT 2 SHORTS V12 Mobile'
    def build(self): return RootUI()

if __name__=='__main__':
    Txt2ShortsAndroid().run()
