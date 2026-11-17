"""pass_through_gui — USBキャプチャー映像をプロジェクターへ超低遅延表示する tkinter アプリ。

ffplay を同梱し、デバイス選択・設定・開始/停止を GUI で行う。
PyInstaller onefile で ffplay/ffmpeg と依存 DLL を同梱する（frozen 対応）。
"""
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tkinter as tk
from ctypes import wintypes
from tkinter import messagebox, ttk

_LOGPREFIX = re.compile(r'^(\[[^\]]*\]\s*)+')
_DEVICE_MARKER = re.compile(r'^"(.*)"\s+\((video|audio)\)$')

DEFAULT_CONFIG = {
    "video_device_id": "",
    "audio_device_id": "",
    "video_size": "auto",       # "auto" = デバイス推奨（-video_size 省略）
    "framerate": "auto",        # "auto" = デバイス推奨（-framerate 省略）
    "monitor_index": -1,     # -1 = 自動（非プライマリ）
    "fullscreen": True,
    "audio_output": True,
    "low_latency": True,
}

FAST_EXIT_SECONDS = 3.0         # これより速い終了は失敗扱い（ffplay は失敗時 exit 0）

# ---- 多言語対応 ----
LANGUAGES = {"ja": "日本語", "en": "English"}

TRANSLATIONS = {
    "ja": {
        "app.title": "パススルー表示（キャプチャー → プロジェクター）",
        "status.ready": "準備完了",
        "language.section": "言語 / Language",
        "language.label": "言語:",
        "section.input": "1. 入力デバイス",
        "section.display": "2. 表示設定",
        "section.controls": "3. 操作",
        "label.video": "映像デバイス:",
        "label.audio": "音声デバイス:",
        "button.rescan": "再検出",
        "label.resolution": "解像度:",
        "label.fps": "FPS:",
        "label.output": "表示先:",
        "check.fullscreen": "フルスクリーンで表示",
        "check.audio": "音声も出力",
        "check.lowlatency": "低遅延(最速)",
        "button.start": "▶ 開始",
        "button.stop": "■ 停止",
        "status.idle": "停止中",
        "status.stopped": "停止しました",
        "status.detecting": "デバイスを検出中…",
        "status.detected": "検出: 映像 {v} / 音声 {a}",
        "status.select_video": "映像デバイスを選択してください",
        "status.no_ffplay": "ffplay が見つかりません（同梱 exe で起動してください）",
        "status.running": "パススルー表示中（Esc で終了）",
        "status.elapsed": "実行中 {sec}s",
        "hint.devices": "※ キャプチャーボードを挿したら「再検出」で更新できます",
        "hint.no_devices": "デバイスが見つかりません。キャプチャーボードを接続して「再検出」",
        "format.auto": "自動（デバイス推奨）",
        "monitor.auto": "自動（プライマリ以外＝プロジェクター）",
        "monitor.entry": "モニター{n}: {name} ({w}x{h}@{x},{y})",
        "monitor.primary": " (プライマリ)",
        "dialog.title": "パススルー表示",
        "runtime.exited": "ffplay が終了しました (code {code})",
    },
    "en": {
        "app.title": "Pass-Through Display (Capture → Projector)",
        "status.ready": "Ready",
        "language.section": "Language",
        "language.label": "Language:",
        "section.input": "1. Input Devices",
        "section.display": "2. Display Settings",
        "section.controls": "3. Controls",
        "label.video": "Video device:",
        "label.audio": "Audio device:",
        "button.rescan": "Rescan",
        "label.resolution": "Resolution:",
        "label.fps": "FPS:",
        "label.output": "Output to:",
        "check.fullscreen": "Fullscreen",
        "check.audio": "Output audio",
        "check.lowlatency": "Low latency (fastest)",
        "button.start": "▶ Start",
        "button.stop": "■ Stop",
        "status.idle": "Stopped",
        "status.stopped": "Stopped",
        "status.detecting": "Detecting devices…",
        "status.detected": "Detected: {v} video / {a} audio",
        "status.select_video": "Please select a video device",
        "status.no_ffplay": "ffplay not found (run the bundled exe)",
        "status.running": "Pass-through active (Esc to exit)",
        "status.elapsed": "Running {sec}s",
        "hint.devices": "Tip: plug in the capture device, then click Rescan",
        "hint.no_devices": "No devices found. Connect a capture device and click Rescan",
        "format.auto": "Auto (device default)",
        "monitor.auto": "Auto (non-primary = projector)",
        "monitor.entry": "Monitor {n}: {name} ({w}x{h}@{x},{y})",
        "monitor.primary": " (primary)",
        "dialog.title": "Pass-Through Display",
        "runtime.exited": "ffplay exited (code {code})",
    },
}


def tr(lang: str = "ja", key: str = "", **kwargs) -> str:
    """言語に応じた文字列。辞書外の言語・未訳キーは ja へフォールバック。
    プレースホルダは {name} 形式。置換失敗時は原文をそのまま返す。"""
    table = TRANSLATIONS.get(lang) or TRANSLATIONS["ja"]
    s = table.get(key)
    if s is None:
        s = TRANSLATIONS["ja"].get(key, key)
    if kwargs:
        try:
            s = s.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return s


def _strip_log_prefix(line: str) -> str:
    """ffmpeg の行頭 [dshow @ ...] 等を除去する。"""
    return _LOGPREFIX.sub('', line).strip()


def parse_dshow_devices(stderr_text: str):
    """`ffmpeg -list_devices true -f dshow -i dummy` の stderr を解析。

    戻り値: {"video": [(フレンドリ名, alternative name), ...],
             "audio": [(フレンドリ名, alternative name), ...]}
    フレンドリ名だけあり Alternative name が無いレコードはスキップする。

    2 形式を扱う:
    - 新: 節ヘッダ "DirectShow video devices" 直下に "名前" → Alternative name
    - 旧: 1 行ごとに "(video)"/"(audio)" マーカー付き "名前" → Alternative name
      （同梱 ffmpeg 2022 ビルドはこちら）
    """
    video, audio = [], []
    section = None        # 'video' | 'audio' | None
    pending_name = None
    for raw in stderr_text.splitlines():
        line = _strip_log_prefix(raw)
        if not line:
            continue
        if 'DirectShow video devices' in line:
            section, pending_name = 'video', None
            continue
        if 'DirectShow audio devices' in line:
            section, pending_name = 'audio', None
            continue
        m = _DEVICE_MARKER.match(line)
        if m:                                # 旧形式: "名前" (video|audio)
            section = 'video' if m.group(2) == 'video' else 'audio'
            pending_name = m.group(1)
            continue
        if section is None:
            continue
        if line.startswith('"'):
            pending_name = line.strip('"')
            continue
        if line.startswith('Alternative name "') and pending_name:
            alt = line[len('Alternative name "'):].rstrip('"')
            (video if section == 'video' else audio).append((pending_name, alt))
            pending_name = None
    return {"video": video, "audio": audio}


def _device_id_suffix(alt: str) -> str:
    """デバイスIDから『どの実体か』を見分ける短い識別子（ベストエフォート）を抽出。

    同じフレンドリ名のデバイスが複数あるとき、ラベルへ付けるための物:
    - pnp 系 (video): '#' 区切りの最後から2番目のセグメント＝インスタンスID
      （例 6&189c91c8&0&0000）
    - cm 系 (audio) : wave_ の後ろにある GUID（例 76C9D41D）
    どちらにも該当しなければ空文字（識別子ナシ）。
    """
    s = alt
    for tail in ("\\global", "\\drv"):
        if s.endswith(tail):
            s = s[:-len(tail)]
    m = re.search(r"wave_\{([^}]*)\}", s, re.IGNORECASE)
    if m:
        return m.group(1)[:8]
    if "#" in s:
        # "prefix#vendor&pid#インスタンスID#{クラスGUID}" の最後から2番目の
        # セグメントがインスタンスID（接続場所の識別子）。末尾の {GUID} は除去。
        parts = s.split("#")
        chunk = parts[-2] if len(parts) >= 2 else parts[-1]
        chunk = re.sub(r"\{[^}]*\}", "", chunk).strip("\\&")
        return chunk
    return ""


def _unique_labels(pairs):
    """[(フレンドリ名, デバイスID)...] を一意なラベル付き一覧へ変換する。

    同名デバイスはどれを指すか区別できるよう「名前 (2) [識別子]」の形にする
    （1台だけなら識別子なしの素の名前）。
    戻り値: [(ラベル, フレンドリ名, デバイスID), ...]（入力の順序を維持）
    """
    counts = {}
    for name, _alt in pairs:
        counts[name] = counts.get(name, 0) + 1
    seen = {}
    result = []
    for name, alt in pairs:
        n = seen.get(name, 0) + 1
        seen[name] = n
        if counts[name] == 1:
            label = name
        else:
            tag = _device_id_suffix(alt)
            label = f"{name} ({n})" + (f" [{tag}]" if tag else "")
        result.append((label, name, alt))
    return result


_SIZE_RE = re.compile(r'^\d{2,5}x\d{2,5}$')


def _clean_size(s) -> str:
    s = str(s).strip()
    return s if _SIZE_RE.match(s) else "1920x1080"


def _clean_fps(f) -> int:
    try:
        v = int(f)
    except (TypeError, ValueError):
        return 30
    return v if 1 <= v <= 240 else 30


def build_ffplay_cmd(ffplay_path, video_size, framerate, video_dev,
                     audio_dev=None, monitor=None, fullscreen=True,
                     low_latency=True, window_title="HDMI Pass-Through"):
    """ffplay 起動用 argv リストを組み立てる（shell=False で渡すこと）。"""
    if not video_dev:
        raise ValueError("video_dev is required")
    cmd = [ffplay_path, "-f", "dshow"]
    if str(video_size).strip().lower() != "auto":        # auto はデバイス推奨（省略）
        cmd += ["-video_size", _clean_size(video_size)]
    if str(framerate).strip().lower() != "auto":
        cmd += ["-framerate", str(_clean_fps(framerate))]
    input_spec = f"video={video_dev}"
    if audio_dev:
        input_spec += f":audio={audio_dev}"
    cmd += ["-i", input_spec]
    if fullscreen and monitor is not None:
        cmd += ["-left", str(monitor["x"]), "-top", str(monitor["y"])]
    if fullscreen:
        cmd += ["-fs"]
    cmd += ["-window_title", window_title]
    if low_latency:
        cmd += ["-fflags", "nobuffer", "-flags", "low_delay", "-framedrop",
                "-probesize", "32k", "-analyzeduration", "0"]
    return cmd


def assemble_ffplay_args(cfg, monitors, ffplay_path):
    """設定 dict + モニター一覧から ffplay argv を組み立てる（GUI/開始時に使用）。"""
    idx = cfg.get("monitor_index", -1)
    try:
        idx = int(idx)                 # 型違い（文字列/None/小数）は安全に int 化
    except (TypeError, ValueError):
        idx = -1                       # 化けられなければ自動へ
    monitor = None
    if idx == -1 or not (0 <= idx < len(monitors)):
        # 自動＝非プライマリを選択（バッチと同挙動）。範囲外（モニター取り外し等）も自動へ。
        for m in monitors:
            if not m.get("primary"):
                monitor = m
                break
    else:
        monitor = monitors[idx]
    audio_dev = cfg.get("audio_device_id") or None
    if not cfg.get("audio_output", True):
        audio_dev = None
    return build_ffplay_cmd(
        ffplay_path,
        cfg.get("video_size", "auto"),
        cfg.get("framerate", "auto"),
        cfg.get("video_device_id", ""),
        audio_dev=audio_dev,
        monitor=monitor,
        fullscreen=bool(cfg.get("fullscreen", True)),
        low_latency=bool(cfg.get("low_latency", True)),
    )


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


_CCHDEVICENAME = 32


class _MONITORINFOEX(ctypes.Structure):
    """GetMonitorInfoW 用拡張構造体（MONITORINFO + szDevice）。"""
    _fields_ = [("cbSize", ctypes.c_ulong),
                ("rcMonitor", _RECT),
                ("rcWork", _RECT),
                ("dwFlags", ctypes.c_ulong),
                ("szDevice", ctypes.c_wchar * _CCHDEVICENAME)]


_MONITORINFOF_PRIMARY = 0x00000001
def ffplay_exit_report(code, elapsed, stderr_tail=""):
    """ffplay 終了の分類。戻り値 (is_failure: bool, ユーザー向けメッセージ)。

    この ffplay ビルドは入力失敗でも exit code 0 を返すため、
    「起動から3秒以内に終了」した場合も失敗扱いにして stderr を提示する。
    """
    error = (code is not None and code != 0) or elapsed < FAST_EXIT_SECONDS
    lines = [ln for ln in stderr_tail.splitlines() if ln.strip()]
    detail = ""
    for ln in reversed(lines):
        if "nan" in ln:          # ffplay の再生ステータス行は無視
            break
        detail = ln.strip()
        break
    if error:
        msg = f"ffplay が終了しました (code {code})"
        if detail:
            msg += f"\n{detail}"
        return True, msg
    return False, "停止しました"


_EnumMonProc = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)


def monitors_from_api():
    """EnumDisplayMonitors + GetMonitorInfoW で全モニターの仮想スクリーン座標を取得。

    各要素 = {"index": int, "x": int, "y": int, "w": int, "h": int,
              "primary": bool, "name": str}。失敗時は []。
    """
    monitors = []

    def _cb(hmon, hdc, lprc, lparam):
        info = _MONITORINFOEX()
        info.cbSize = ctypes.sizeof(_MONITORINFOEX)
        if ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            rc = info.rcMonitor
            monitors.append({
                "x": rc.left, "y": rc.top,
                "w": rc.right - rc.left, "h": rc.bottom - rc.top,
                "primary": bool(info.dwFlags & _MONITORINFOF_PRIMARY),
                "name": info.szDevice,
            })
        return True

    callback = _EnumMonProc(_cb)
    if not ctypes.windll.user32.EnumDisplayMonitors(0, 0, callback, 0):
        return []
    monitors.sort(key=lambda m: not m["primary"])       # プライマリ先頭
    for i, m in enumerate(monitors):
        m["index"] = i
    return monitors


def config_path() -> str:
    if getattr(sys, "frozen", False):
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "pass_through_gui_config.json")


def default_config() -> dict:
    return dict(DEFAULT_CONFIG)


def load_config(path=None) -> dict:
    cfg = default_config()
    try:
        with open(path or config_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            for key in cfg:
                if key in data:
                    cfg[key] = data[key]
    except Exception:
        pass
    return cfg


def save_config(cfg, path=None) -> None:
    payload = default_config()
    payload.update({k: v for k, v in cfg.items() if k in payload})
    try:
        with open(path or config_path(), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


CREATE_NO_WINDOW = 0x08000000
_MEIPASS = getattr(sys, "_MEIPASS", None)


def tool_candidates(tool_exe):
    cands = []
    if _MEIPASS:
        cands.append(os.path.join(_MEIPASS, "ffmpeg", tool_exe))
    cands.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ffmpeg", tool_exe))
    if getattr(sys, "frozen", False):
        cands.append(os.path.join(os.path.dirname(os.path.abspath(sys.executable)),
                                  "ffmpeg", tool_exe))
    cands.append(os.path.join("C:/ffmpeg/bin", tool_exe))
    cands.append(tool_exe)
    return cands


def find_tool(tool_exe):
    for cand in tool_candidates(tool_exe):
        if os.path.isfile(cand):
            return cand
    return shutil.which(tool_exe) or None


def run_list_devices() -> str:
    ffmpeg = find_tool("ffmpeg.exe")
    if not ffmpeg:
        return ""
    try:
        p = subprocess.run(
            [ffmpeg, "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
            capture_output=True, timeout=15,
            creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0)
    except Exception:
        return ""
    return (p.stderr or b"").decode("utf-8", errors="replace")


def ffplay_env() -> dict:
    return {
        "SDL_WINDOWS_DPI_AWARENESS": "disabled",          # スケーリングズレ防止
        "SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS": "0",          # GUI 操作で全画面解除しない
    }


class DisplayController:
    """ffplay プロセスの起動・停止管理（GUI 終了時も必ず片付ける）。"""

    def __init__(self, popen=None):
        self._popen = popen or subprocess.Popen
        self.proc = None
        self._stderr_path = None

    def build_env(self) -> dict:
        env = dict(os.environ)
        env.update(ffplay_env())
        return env

    def start(self, argv, stderr_path=None):
        self.stop()
        self._stderr_path = stderr_path
        stderr_fh = open(stderr_path, "wb", buffering=0) if stderr_path else None
        self.proc = self._popen(argv, env=self.build_env(),
                                stderr=stderr_fh,
                                creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0)

    def stderr_tail(self, limit=800) -> str:
        """終了後、前回 start の stderr 末尾を読み出す（無ければ空文字）。"""
        if not self._stderr_path or not os.path.exists(self._stderr_path):
            return ""
        try:
            with open(self._stderr_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - limit))
                return f.read()
        except Exception:
            return ""

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def exit_code(self):
        return self.proc.poll() if self.proc is not None else None

    def stop(self):
        if self.proc is None:
            return
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        # self.proc は残す: exit_code() で終了状態を参照できるようにする。
        # running() は poll() が非 None になるため False のまま。


MONITOR_AUTO_LABEL = "自動（プライマリ以外＝プロジェクター）"
FORMAT_AUTO_LABEL = "自動（デバイス推奨）"


class App:
    def __init__(self, root, config_path=None):
        self.root = root
        self.root.title("パススルー表示（キャプチャー → プロジェクター）")
        self.root.geometry("560x540")
        self._config_path = config_path
        self.cfg = load_config(config_path)
        self.monitors = monitors_from_api()
        self.controller = DisplayController()
        self._video_map = {}          # コンボ表示名 -> alternative name
        self._audio_map = {}
        self._monitor_by_label = {}   # コンボ表示名 -> index
        self._stderr_path = None      # 直近 start の ffplay stderr 一時ファイル
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_widgets()
        self._apply_cfg_to_widgets()
        self.refresh_devices()

    # ---- UI 構築 ----
    def _build_widgets(self):
        pad = {"padx": 8, "pady": 4}
        self.status_var = tk.StringVar(value="準備完了")
        tk.Label(self.root, textvariable=self.status_var, anchor="w",
                 fg="#0a6", relief="sunken").pack(fill="x", padx=8, pady=6)

        frame = ttk.LabelFrame(self.root, text="1. 入力デバイス")
        frame.pack(fill="x", padx=8, pady=4)
        row = ttk.Frame(frame)
        row.pack(fill="x", **pad)
        ttk.Label(row, text="映像デバイス:").pack(side="left")
        self.video_combo = ttk.Combobox(row, state="readonly")
        self.video_combo.pack(side="left", fill="x", expand=True, padx=(4, 0))
        ttk.Button(row, text="再検出", command=self.refresh_devices).pack(side="left", padx=(6, 0))
        row = ttk.Frame(frame)
        row.pack(fill="x", **pad)
        ttk.Label(row, text="音声デバイス:").pack(side="left")
        self.audio_combo = ttk.Combobox(row, state="readonly")
        self.audio_combo.pack(side="left", fill="x", expand=True, padx=(4, 0))
        self.device_hint = tk.StringVar(value="※ キャプチャーボードを挿したら「再検出」で更新できます")
        ttk.Label(frame, textvariable=self.device_hint, foreground="#666").pack(anchor="w", **pad)

        frame = ttk.LabelFrame(self.root, text="2. 表示設定")
        frame.pack(fill="x", padx=8, pady=4)
        row = ttk.Frame(frame)
        row.pack(fill="x", **pad)
        ttk.Label(row, text="解像度:").pack(side="left")
        self.size_combo = ttk.Combobox(
            row, values=[FORMAT_AUTO_LABEL, "1920x1080", "1280x720", "3840x2160", "640x480"])
        self.size_combo.pack(side="left", fill="x", expand=True, padx=(4, 0))
        ttk.Label(row, text="FPS:").pack(side="left", padx=(12, 0))
        self.fps_combo = ttk.Combobox(
            row, width=8, values=[FORMAT_AUTO_LABEL, "30", "25", "60", "24"])
        self.fps_combo.pack(side="left", padx=(4, 0))
        row = ttk.Frame(frame)
        row.pack(fill="x", **pad)
        ttk.Label(row, text="表示先:").pack(side="left")
        self.monitor_combo = ttk.Combobox(row, state="readonly")
        self.monitor_combo.pack(side="left", fill="x", expand=True, padx=(4, 0))
        row = ttk.Frame(frame)
        row.pack(fill="x", **pad)
        self.chk_fullscreen = tk.BooleanVar(value=True)
        self.chk_audio = tk.BooleanVar(value=True)
        self.chk_lowlatency = tk.BooleanVar(value=True)
        ttk.Checkbutton(row, text="フルスクリーンで表示", variable=self.chk_fullscreen).pack(side="left")
        ttk.Checkbutton(row, text="音声も出力", variable=self.chk_audio).pack(side="left", padx=(12, 0))
        ttk.Checkbutton(row, text="低遅延(最速)", variable=self.chk_lowlatency).pack(side="left", padx=(12, 0))

        frame = ttk.LabelFrame(self.root, text="3. 操作")
        frame.pack(fill="x", padx=8, pady=4)
        row = ttk.Frame(frame)
        row.pack(fill="x", **pad)
        self.btn_start = ttk.Button(row, text="▶ 開始", command=self.start)
        self.btn_start.pack(side="left")
        self.btn_stop = ttk.Button(row, text="■ 停止", command=self.stop, state="disabled")
        self.btn_stop.pack(side="left", padx=(8, 0))
        self.elapsed_var = tk.StringVar(value="停止中")
        ttk.Label(row, textvariable=self.elapsed_var).pack(side="right")

    def _refresh_monitors(self):
        """モニター一覧を再取得して表示先コンボへ反映（ホットプラグ追従）。"""
        self.monitors = monitors_from_api()
        prev = self.monitor_combo.get()
        self.monitor_combo["values"] = self._monitor_labels()
        # 現在の選択を維持（無ければ自動へフォールバック）
        if prev in self._monitor_by_label:
            self.monitor_combo.set(prev)
        else:
            self.monitor_combo.set(MONITOR_AUTO_LABEL)

    def _monitor_labels(self):
        labels = [MONITOR_AUTO_LABEL]
        self._monitor_by_label = {MONITOR_AUTO_LABEL: -1}
        for m in self.monitors:
            tag = " (プライマリ)" if m["primary"] else ""
            lab = f"モニター{m['index'] + 1}: {m['name']} ({m['w']}x{m['h']}@{m['x']},{m['y']}){tag}"
            labels.append(lab)
            self._monitor_by_label[lab] = m["index"]
        return labels

    def _apply_cfg_to_widgets(self):
        vs = str(self.cfg.get("video_size", "auto"))
        self.size_combo.set(FORMAT_AUTO_LABEL if vs == "auto" else vs)
        fs = str(self.cfg.get("framerate", "auto"))
        self.fps_combo.set(FORMAT_AUTO_LABEL if fs == "auto" else fs)
        self.chk_fullscreen.set(bool(self.cfg.get("fullscreen", True)))
        self.chk_audio.set(bool(self.cfg.get("audio_output", True)))
        self.chk_lowlatency.set(bool(self.cfg.get("low_latency", True)))
        self.monitor_combo["values"] = self._monitor_labels()
        idx = self.cfg.get("monitor_index", -1)
        for lab, i in self._monitor_by_label.items():
            if i == idx:
                self.monitor_combo.set(lab)
                break

    # ---- デバイス列挙 ----
    def refresh_devices(self):
        self.status_var.set("デバイスを検出中…")
        self._refresh_monitors()          # プロジェクターのホットプラグにも追従
        parsed = parse_dshow_devices(run_list_devices())
        # 同名デバイス（同じキャプチャーボードを2台等）も漏れなく表示できるよう、
        # 一意ラベル（重複時は「名前 (n) [識別子]」）をキーにして保持する。
        video = _unique_labels(parsed["video"])
        audio = _unique_labels(parsed["audio"])
        self._video_map = {label: alt for label, _name, alt in video}
        self._audio_map = {label: alt for label, _name, alt in audio}
        self.video_combo["values"] = list(self._video_map)
        self.audio_combo["values"] = [""] + list(self._audio_map)
        if not self._video_map:
            self.video_combo.set("")
            self.device_hint.set("デバイスが見つかりません。キャプチャーボードを接続して「再検出」")
        else:
            self.device_hint.set("※ キャプチャーボードを挿したら「再検出」で更新できます")
        self.status_var.set(f"検出: 映像 {len(self._video_map)} / 音声 {len(self._audio_map)}")
        self._keep_selection_after_refresh()

    def _keep_selection_after_refresh(self):
        prev_v = self.cfg.get("video_device_id", "")
        for name, alt in self._video_map.items():
            if alt == prev_v:
                self.video_combo.set(name)
                break
        prev_a = self.cfg.get("audio_device_id", "")
        for name, alt in self._audio_map.items():
            if alt == prev_a:
                self.audio_combo.set(name)
                break

    # ---- 開始/停止 ----
    def _current_cfg(self) -> dict:
        cfg = default_config()
        cfg.update(self.cfg)
        sel_v = self.video_combo.get()
        sel_a = self.audio_combo.get()
        cfg["video_device_id"] = self._video_map.get(sel_v, "")
        cfg["audio_device_id"] = self._audio_map.get(sel_a, "") if sel_a else ""
        vs = self.size_combo.get().strip()
        cfg["video_size"] = "auto" if vs == FORMAT_AUTO_LABEL else vs
        fs = self.fps_combo.get().strip()
        cfg["framerate"] = "auto" if fs == FORMAT_AUTO_LABEL else fs
        lab = self.monitor_combo.get()
        cfg["monitor_index"] = self._monitor_by_label.get(lab, -1)
        cfg["fullscreen"] = bool(self.chk_fullscreen.get())
        cfg["audio_output"] = bool(self.chk_audio.get())
        cfg["low_latency"] = bool(self.chk_lowlatency.get())
        return cfg

    def start(self):
        if not self._video_map.get(self.video_combo.get()):
            self.status_var.set("映像デバイスを選択してください")
            return
        self._refresh_monitors()          # 起動後にプロジェクターが増えても再検出
        self.cfg = self._current_cfg()
        save_config(self.cfg, self._config_path)
        ffplay = find_tool("ffplay.exe")
        if not ffplay:
            self.status_var.set("ffplay が見つかりません（同梱 exe で起動してください）")
            return
        argv = assemble_ffplay_args(self.cfg, self.monitors, ffplay)
        try:
            fd, self._stderr_path = tempfile.mkstemp(prefix="pass_ffplay_", suffix=".log")
            os.close(fd)
        except OSError:
            self._stderr_path = None
        self.controller.start(argv, stderr_path=self._stderr_path)
        self._t0 = time.time()
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.status_var.set("ffplay 起動中…")
        self.root.after(500, self._poll)

    def stop(self):
        self.controller.stop()
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.elapsed_var.set("停止")
        self.status_var.set("停止しました")

    def _poll(self):
        if self.controller.running():
            secs = int(time.time() - self._t0)
            self.elapsed_var.set(f"実行中 {secs}s")
            self.status_var.set("パススルー表示中（Esc で終了）")
            self.root.after(500, self._poll)
            return
        code = self.controller.exit_code()
        elapsed = time.time() - self._t0
        is_failure, msg = ffplay_exit_report(code, elapsed, self.controller.stderr_tail())
        if is_failure:
            messagebox.showwarning("パススルー表示", msg)
        self.status_var.set(msg)
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.elapsed_var.set("停止")
        if self._stderr_path:
            try:
                os.remove(self._stderr_path)
            except Exception:
                pass
            self._stderr_path = None

    def _on_close(self):
        self.controller.stop()
        self.root.destroy()


def self_test() -> int:
    print("== pass_through_gui selftest ==")
    ffplay = find_tool("ffplay.exe")
    ffmpeg = find_tool("ffmpeg.exe")
    print(f"ffplay : {ffplay or 'NOT FOUND'}")
    print(f"ffmpeg : {ffmpeg or 'NOT FOUND'}")
    mons = monitors_from_api()
    print(f"monitors : {len(mons)}")
    for m in mons:
        print(f"  - {m['name']} {'primary' if m['primary'] else ''} "
              f"{m['x']},{m['y']} {m['w']}x{m['h']}")
    parsed = parse_dshow_devices(run_list_devices())
    print(f"video devices: {[n for n, _ in parsed['video']] or '（なし）'}")
    print(f"audio devices: {[n for n, _ in parsed['audio']] or '（なし）'}")
    print("selftest OK")
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        return self_test()
    if "--debug" in argv:
        # コマンド生成だけ表示（起動しない）
        cfg = load_config()
        mons = monitors_from_api()
        fp = find_tool("ffplay.exe") or "ffplay.exe"
        if not cfg.get("video_device_id"):
            # 未設定状態でも構造が分かるようプレースホルダで表示
            cfg = dict(cfg)
            cfg["video_device_id"] = "@device_pnp_\\?\\usb#vid_0000&pid_0000\\global"
            cfg["audio_device_id"] = ""
            cfg["audio_output"] = False
        print(assemble_ffplay_args(cfg, mons, fp))
        return 0
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
