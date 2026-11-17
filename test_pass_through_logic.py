import unittest

import json
import os
import sys
import tempfile
import time
import unittest

from pass_through_gui import (App, DEFAULT_CONFIG, DisplayController,
                              LANGUAGES, TRANSLATIONS, tr,
                              _clean_fps, _clean_size, _device_id_suffix,
                              _unique_labels, assemble_ffplay_args,
                              build_ffplay_cmd, default_config, ffplay_env,
                              ffplay_exit_report, find_tool, load_config,
                              monitors_from_api, parse_dshow_devices,
                              run_list_devices, save_config, tool_candidates)


class ParseDshowDevicesTests(unittest.TestCase):

    def test_video_and_audio_parsed(self):
        text = (
            'ffmpeg version ...\n'
            '[dshow @ 000001] DirectShow video devices (some may be both video and audio devices):\n'
            '  "HDMI Capture"\n'
            '     Alternative name "@device_pnp_\\\\?\\usb#vid_07ca&pid_3513&mi_00#6&189c91c8&0&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\\global"\n'
            'DirectShow audio devices:\n'
            '  "マイク(USB)"\n'
            '     Alternative name "@device_cm_{33D9A762-90C8-11D0-BD43-00A0C911CE86}\\wave_{76C9D41D-2DC5-4D26-961A-1538F0783150}"\n'
        )
        out = parse_dshow_devices(text)
        self.assertEqual(len(out["video"]), 1)
        v_name, v_id = out["video"][0]
        self.assertEqual(v_name, "HDMI Capture")
        self.assertTrue(v_id.startswith("@device_pnp_"))
        self.assertIn("&pid_3513", v_id)   # & は保持（shell 不使用のため）
        self.assertEqual(len(out["audio"]), 1)
        self.assertEqual(out["audio"][0][0], "マイク(USB)")

    def test_entry_without_alternative_name_is_skipped(self):
        text = (
            'DirectShow video devices (some may be both video and audio devices):\n'
            '  "NoID Device"\n'
            'DirectShow audio devices:\n'
            '  "Mic2"\n'
            '     Alternative name "@device_cm_{X}\\wave_{Y}"\n'
        )
        out = parse_dshow_devices(text)
        self.assertEqual(out["video"], [])          # Alternative name 無しは落とす
        self.assertEqual(len(out["audio"]), 1)      # 他セクションは正常
        self.assertEqual(out["audio"][0][0], "Mic2")

    def test_empty_output_yields_empty_lists(self):
        self.assertEqual(parse_dshow_devices(""), {"video": [], "audio": []})
        self.assertEqual(parse_dshow_devices("no devices at all"), {"video": [], "audio": []})

    def test_old_marker_format_with_dshow_prefix(self):
        # 同梱 ffmpeg(2022ビルド) は節ヘッダ無しの「"名前" (video)/(audio)」形式
        text = (
            '[dshow @ 000001x] "HDMI Capture" (video)\r\n'
            '[dshow @ 000001x]   Alternative name "@device_pnp_\\\\?\\usb#vid_07ca&pid_3513\\global"\r\n'
            '[dshow @ 000001x] "Headset Microphone" (audio)\r\n'
            '[dshow @ 000001x]   Alternative name "@device_cm_{C}\\wave_{D}"\r\n'
        )
        out = parse_dshow_devices(text)
        self.assertEqual([n for n, _ in out["video"]], ["HDMI Capture"])
        self.assertEqual([n for n, _ in out["audio"]], ["Headset Microphone"])
        self.assertIn("&pid_3513", out["video"][0][1])

    def test_marker_format_entry_without_alt_name_is_skipped(self):
        text = (
            '[dshow @ 0] "Capture NoId" (video)\r\n'
            '[dshow @ 0] "Mic3" (audio)\r\n'
            '[dshow @ 0]   Alternative name "@device_cm_{X}\\wave_{Y}"\r\n'
        )
        out = parse_dshow_devices(text)
        self.assertEqual(out["video"], [])
        self.assertEqual([n for n, _ in out["audio"]], ["Mic3"])


class BuildFfplayCmdTests(unittest.TestCase):
    MON = {"x": -1920, "y": 0, "w": 1920, "h": 1080, "primary": False, "name": "P"}
    VID = "@device_pnp_\\?\\usb#vid_07ca&pid_3513&mi_00#6&x\\global"
    AUD = "@device_cm_{33D9A762-90C8-11D0-BD43-00A0C911CE86}\\wave_{76C9D41D-2DC5-4D26-961A-1538F0783150}"

    def test_fullscreen_with_monitor_and_audio(self):
        cmd = build_ffplay_cmd("ffplay.exe", "1920x1080", 30, self.VID, self.AUD,
                               monitor=self.MON, fullscreen=True, low_latency=True)
        self.assertEqual(cmd[0], "ffplay.exe")
        self.assertEqual(cmd[1:5], ["-f", "dshow", "-video_size", "1920x1080"])
        i = cmd.index("-i")
        self.assertEqual(cmd[i + 1], f"video={self.VID}:audio={self.AUD}")
        self.assertIn("-left", cmd)
        self.assertEqual(cmd[cmd.index("-left") + 1], "-1920")
        self.assertEqual(cmd[cmd.index("-top") + 1], "0")
        self.assertIn("-fs", cmd)
        for flag in ("-fflags", "nobuffer", "-flags", "low_delay", "-framedrop",
                     "-probesize", "32k", "-analyzeduration", "0"):
            self.assertIn(flag, cmd)

    def test_device_ids_preserved_verbatim(self):
        # \\ ? & # は argv 要素としてそのまま渡る（shell=False 前提）
        cmd = build_ffplay_cmd("ffplay.exe", "1920x1080", 30, self.VID, None,
                               monitor=None, fullscreen=False, low_latency=False)
        i = cmd.index("-i")
        self.assertEqual(cmd[i + 1], f"video={self.VID}")

    def test_audio_off_and_no_low_latency(self):
        cmd = build_ffplay_cmd("ffplay.exe", "1920x1080", 30, self.VID, None,
                               monitor=None, fullscreen=False, low_latency=False)
        i = cmd.index("-i")
        self.assertNotIn(":audio=", cmd[i + 1])
        self.assertNotIn("-fflags", cmd)
        self.assertNotIn("-fs", cmd)

    def test_no_left_top_without_fullscreen(self):
        cmd = build_ffplay_cmd("ffplay.exe", "1280x720", 25, self.VID, None,
                               monitor=self.MON, fullscreen=False, low_latency=True)
        self.assertNotIn("-left", cmd)
        self.assertNotIn("-top", cmd)

    def test_clean_size_and_fps_fallbacks(self):
        self.assertEqual(_clean_size(""), "1920x1080")
        self.assertEqual(_clean_size("abc"), "1920x1080")
        self.assertEqual(_clean_size("720x480"), "720x480")
        self.assertEqual(_clean_fps(0), 30)
        self.assertEqual(_clean_fps(-3), 30)
        self.assertEqual(_clean_fps("NaN"), 30)
        self.assertEqual(_clean_fps("25"), 25)

    def test_auto_size_fps_omitted_from_argv(self):
        cmd = build_ffplay_cmd("ffplay.exe", "auto", "auto", self.VID, None,
                               monitor=self.MON, fullscreen=True, low_latency=True)
        self.assertNotIn("-video_size", cmd)
        self.assertNotIn("-framerate", cmd)
        self.assertIn("-fs", cmd)


class MonitorTests(unittest.TestCase):
    def test_monitors_from_api_shape(self):
        mons = monitors_from_api()
        self.assertIsInstance(mons, list)
        # Windows デスクトップ（GUI 実行対象）には必ず 1 枚以上存在する。
        # 空リスト＝WinAPI 呼び出しの失敗＝実装バグを検出するため非空を要求する。
        self.assertGreaterEqual(len(mons), 1)
        for m in mons:
            for key in ("index", "x", "y", "w", "h", "primary", "name"):
                self.assertIn(key, m)
            self.assertGreater(m["w"], 0)
            self.assertGreater(m["h"], 0)
        primaries = [m for m in mons if m["primary"]]
        self.assertEqual(len(primaries), 1)
        self.assertEqual(mons[0]["index"], 0)
        # 自動モニター解決の前提（is not None）
        self.assertIsNotNone(sys.modules["pass_through_gui"].monitors_from_api)


class ToolResolutionTests(unittest.TestCase):
    def test_candidates_include_bundled_and_known_dirs(self):
        cands = tool_candidates("ffplay.exe")
        self.assertEqual(cands[-1], "ffplay.exe")          # PATH フォールバック
        self.assertTrue(any("ffplay.exe" in c and "ffmpeg" in c for c in cands[:-1]))

    def test_find_tool_located_on_this_machine(self):
        # 開発マシンには C:/ffmpeg/bin/ffplay.exe がある想定
        exe = find_tool("ffplay.exe")
        self.assertTrue(exe is None or os.path.exists(exe))


class FfplayEnvTests(unittest.TestCase):
    def test_sdl_env(self):
        env = ffplay_env()
        self.assertEqual(env["SDL_WINDOWS_DPI_AWARENESS"], "disabled")
        self.assertEqual(env["SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS"], "0")


class RunListDevicesTests(unittest.TestCase):
    def test_returns_text_or_empty(self):
        text = run_list_devices()
        self.assertIsInstance(text, str)
        # 戻り値は文字列で、あれば必ずパース可能な dict を返す（例外なし）。
        parsed = parse_dshow_devices(text)
        self.assertEqual(set(parsed), {"video", "audio"})


class DisplayControllerTests(unittest.TestCase):
    def test_start_running_stop(self):
        ctrl = DisplayController()
        self.assertFalse(ctrl.running())
        ctrl.start([sys.executable, "-c", "import time; time.sleep(60)"])
        self.assertTrue(ctrl.running())
        self.assertIsNone(ctrl.exit_code())
        ctrl.stop()
        self.assertFalse(ctrl.running())
        self.assertIsNotNone(ctrl.exit_code())

    def test_stop_without_start_is_safe(self):
        ctrl = DisplayController()
        ctrl.stop()   # 何も起きない
        self.assertFalse(ctrl.running())

    def test_build_env_includes_sdl_and_existing(self):
        ctrl = DisplayController()
        env = ctrl.build_env()
        self.assertEqual(env["SDL_WINDOWS_DPI_AWARENESS"], "disabled")
        self.assertIn("PATH", env)

    def test_restart_after_stop(self):
        ctrl = DisplayController()
        ctrl.start([sys.executable, "-c", "import time; time.sleep(60)"])
        ctrl.stop()
        ctrl.start([sys.executable, "-c", "import time; time.sleep(60)"])
        self.assertTrue(ctrl.running())
        ctrl.stop()

    def test_process_early_exit_reported(self):
        # ffplay 早死（例: デバイス使用中）を GUI 側の _poll が拾う前提を固定。
        # running() が False に戻り exit_code() が終了コードを返すこと。
        ctrl = DisplayController()
        ctrl.start([sys.executable, "-c", "import sys; sys.exit(2)"])
        deadline = time.time() + 5
        while ctrl.running() and time.time() < deadline:
            time.sleep(0.05)
        self.assertFalse(ctrl.running())
        self.assertEqual(ctrl.exit_code(), 2)

    def test_start_captures_stderr_to_path(self):
        # ffplay の stderr をファイルへ取り、終了後に stderr_tail() で読めること。
        # （この ffplay 2022ビルドは失敗時に exit 0 を返すため stderr 表示が重要）
        with tempfile.TemporaryDirectory() as d:
            sp = os.path.join(d, "err.log")
            ctrl = DisplayController()
            ctrl.start([sys.executable, "-c",
                        "import sys; sys.stderr.write('boom-dshow-error'); sys.exit(0)"],
                       stderr_path=sp)
            deadline = time.time() + 5
            while ctrl.running() and time.time() < deadline:
                time.sleep(0.05)
            self.assertFalse(ctrl.running())
            self.assertEqual(ctrl.exit_code(), 0)
            self.assertIn("boom-dshow-error", ctrl.stderr_tail())

    def test_stderr_tail_empty_when_not_captured(self):
        ctrl = DisplayController()
        self.assertEqual(ctrl.stderr_tail(), "")


class FfplayExitReportTests(unittest.TestCase):
    def test_fast_exit_is_failure_even_with_code_zero(self):
        # この ffplay は失敗しても exit 0 を返す → 即終了は失敗扱いで stderr を提示
        failure, msg = ffplay_exit_report(0, 0.2, "Could not set video options")
        self.assertTrue(failure)
        self.assertIn("Could not set video options", msg)

    def test_normal_clean_stop_after_running(self):
        failure, msg = ffplay_exit_report(0, 10.0, "")
        self.assertFalse(failure)

    def test_nonzero_code_is_failure_anytime(self):
        failure, _ = ffplay_exit_report(2, 10.0, "")
        self.assertTrue(failure)

    def test_detail_preserved_in_message(self):
        _, msg = ffplay_exit_report(0, 0.2, "I/O error video=@x")
        self.assertIn("I/O error", msg)


class _StubController:
    """App.start() の検証用スタブ（実際のプロセスは起動しない）。"""

    def __init__(self):
        self.args = None
        self.stopped = False

    def start(self, argv, stderr_path=None):
        self.args = argv
        self.stderr_path = stderr_path

    def stop(self):
        self.stopped = True

    def running(self):
        return False


class AppMonitorRefreshTests(unittest.TestCase):
    PRIM = {"index": 0, "x": 0, "y": 0, "w": 1463, "h": 823, "primary": True, "name": "P"}
    SEC = {"index": 1, "x": 1707, "y": 0, "w": 1280, "h": 720, "primary": False, "name": "S"}

    def _make_app(self, tmpdir):
        import tkinter as tk
        import pass_through_gui as mod
        root = tk.Tk()
        root.withdraw()   # テスト中は非表示
        app = mod.App(root, config_path=os.path.join(tmpdir, "cfg.json"))
        return root, app, mod

    def test_monitor_refresh_detects_newly_connected(self):
        import pass_through_gui as mod
        with tempfile.TemporaryDirectory() as d:
            root, app, mod = self._make_app(d)
            original = mod.monitors_from_api
            try:
                mod.monitors_from_api = lambda: [dict(self.PRIM)]
                app._refresh_monitors()
                self.assertEqual(len(app.monitors), 1)
                mod.monitors_from_api = lambda: [dict(self.PRIM), dict(self.SEC)]
                app._refresh_monitors()          # プロジェクター接続後
                self.assertEqual(len(app.monitors), 2)
                self.assertTrue(any(not m["primary"] for m in app.monitors))
                self.assertIn("モニター2: S", app.monitor_combo["values"][2])
            finally:
                mod.monitors_from_api = original
                root.destroy()

    def test_start_refreshes_monitors_before_launch(self):
        import pass_through_gui as mod
        with tempfile.TemporaryDirectory() as d:
            root, app, mod = self._make_app(d)
            original_m, original_f = mod.monitors_from_api, mod.find_tool
            stub = _StubController()
            try:
                app.controller = stub
                app._video_map = {"Fake Cam": "alt_video"}
                app.video_combo["values"] = ["Fake Cam"]
                app.video_combo.set("Fake Cam")
                mod.find_tool = lambda tool: "ffplay.exe"
                # 起動時は 1 枚だったが、開始時にプロジェクターが増えている想定
                app.monitors = [dict(self.PRIM)]
                mod.monitors_from_api = lambda: [dict(self.PRIM), dict(self.SEC)]
                app.start()
                self.assertIsNotNone(stub.args)
                self.assertEqual(len(app.monitors), 2)   # 開始時に再列挙された
                i = stub.args.index("-left")
                self.assertEqual(stub.args[i + 1], "1707")   # 新 2nd モニターへ
            finally:
                mod.monitors_from_api = original_m
                mod.find_tool = original_f
                root.destroy()


class ConfigTests(unittest.TestCase):
    def test_defaults_complete(self):
        cfg = default_config()
        self.assertEqual(cfg["video_size"], "auto")   # デバイス推奨（形式不一致を防ぐ）
        self.assertEqual(cfg["framerate"], "auto")
        self.assertEqual(cfg["monitor_index"], -1)
        self.assertTrue(cfg["fullscreen"] and cfg["audio_output"] and cfg["low_latency"])
        self.assertIsNot(default_config(), default_config())   # 毎回新しい dict

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "cfg.json")
            cfg = default_config()
            cfg["video_size"] = "1280x720"
            cfg["monitor_index"] = 1
            cfg["framerate"] = 25
            save_config(cfg, p)
            loaded = load_config(p)
            self.assertEqual(loaded["video_size"], "1280x720")
            self.assertEqual(loaded["monitor_index"], 1)
            self.assertEqual(loaded["framerate"], 25)

    def test_corrupt_json_returns_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "cfg.json")
            with open(p, "w", encoding="utf-8") as f:
                f.write("{not json!")
            self.assertEqual(load_config(p), default_config())

    def test_unknown_keys_ignored_and_defaults_filled(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "cfg.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"video_size": "640x480", "hacker_key": 1}, f)
            loaded = load_config(p)
            self.assertEqual(loaded["video_size"], "640x480")
            self.assertEqual(loaded["monitor_index"], -1)   # 欠落は既定値
            self.assertNotIn("hacker_key", loaded)          # 不明キーは無視


class AssembleFfplayArgsTests(unittest.TestCase):
    IDX_MON = {"x": 0, "y": 0, "w": 1920, "h": 1080, "primary": True, "name": "A"}
    SEC_MON = {"x": -1920, "y": 0, "w": 1920, "h": 1080, "primary": False, "name": "P"}
    MONITORS = [IDX_MON, SEC_MON]

    def _cfg(self, **kw):
        base = {"video_device_id": "@v", "audio_device_id": "@a",
                "video_size": "1920x1080", "framerate": 30,
                "monitor_index": -1, "fullscreen": True,
                "audio_output": True, "low_latency": True}
        base.update(kw)
        return base

    def test_auto_picks_first_non_primary(self):
        cmd = assemble_ffplay_args(self._cfg(), self.MONITORS, "ffplay")
        i = cmd.index("-left")
        self.assertEqual(cmd[i + 1], "-1920")      # プロジェクターの X

    def test_auto_with_only_primary_has_no_position(self):
        cmd = assemble_ffplay_args(self._cfg(), [self.IDX_MON], "ffplay")
        self.assertNotIn("-left", cmd)

    def test_explicit_index_uses_that_monitor(self):
        cmd = assemble_ffplay_args(self._cfg(monitor_index=0), self.MONITORS, "ffplay")
        self.assertEqual(cmd[cmd.index("-left") + 1], "0")

    def test_out_of_range_falls_back_to_auto(self):
        cmd = assemble_ffplay_args(self._cfg(monitor_index=99), self.MONITORS, "ffplay")
        self.assertEqual(cmd[cmd.index("-left") + 1], "-1920")   # 自動＝非プライマリ

    def test_monitor_index_type_garbage_does_not_crash(self):
        # 型違い（文字列/None/小数/非数値）でも例外にせず argv を返し、自動へ落とす
        for bad in ("3", None, 1.5, "oops"):
            cmd = assemble_ffplay_args(self._cfg(monitor_index=bad), self.MONITORS, "ffplay")
            self.assertIn("-i", cmd)
            self.assertEqual(cmd[cmd.index("-left") + 1], "-1920")

    def test_audio_output_off_drops_audio(self):
        cmd = assemble_ffplay_args(self._cfg(audio_output=False), self.MONITORS, "ffplay")
        i = cmd.index("-i")
        self.assertNotIn(":audio=", cmd[i + 1])

    def test_garbage_size_fps_falls_back(self):
        cmd = assemble_ffplay_args(self._cfg(video_size="", framerate="oops"),
                                   self.MONITORS, "ffplay")
        i = cmd.index("-video_size")
        self.assertEqual(cmd[i + 1], "1920x1080")
        self.assertEqual(cmd[cmd.index("-framerate") + 1], "30")

    def test_auto_config_omits_size_and_fps(self):
        cmd = assemble_ffplay_args(self._cfg(video_size="auto", framerate="auto"),
                                   self.MONITORS, "ffplay")
        self.assertNotIn("-video_size", cmd)
        self.assertNotIn("-framerate", cmd)
        self.assertIn("-fs", cmd)


class DeviceLabelTests(unittest.TestCase):
    """同名デバイスでも一意なラベルへ変換できる（_unique_labels / _device_id_suffix）。"""

    def test_unique_names_keep_bare_labels(self):
        pairs = [("Cam A", "@a1"), ("Mic B", "@b1")]
        labels = [lab for lab, _name, _alt in _unique_labels(pairs)]
        self.assertEqual(labels, ["Cam A", "Mic B"])

    def test_duplicate_video_names_get_counter_and_instance_suffix(self):
        pairs = [
            ("HDMI Capture", "@device_pnp_\\\\?\\usb#vid_07ca&pid_3513&mi_00#6&189c91c8&0&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\\global"),
            ("HDMI Capture", "@device_pnp_\\\\?\\usb#vid_07ca&pid_3513&mi_00#7&183c1a2c&0&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\\global"),
        ]
        out = _unique_labels(pairs)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0][0], "HDMI Capture (1) [6&189c91c8&0&0000]")
        self.assertEqual(out[1][0], "HDMI Capture (2) [7&183c1a2c&0&0000]")
        self.assertEqual(out[0][1], "HDMI Capture")
        self.assertEqual(out[0][2], pairs[0][1])   # デバイスIDは元のまま

    def test_duplicate_audio_names_get_wave_guid_suffix(self):
        pairs = [
            ("USB Mic", "@device_cm_{33D9A762-90C8-11D0-BD43-00A0C911CE86}\\wave_{76C9D41D-2DC5-4D26-961A-1538F0783150}"),
            ("USB Mic", "@device_cm_{33D9A762-90C8-11D0-BD43-00A0C911CE86}\\wave_{F0E9B831-11AA-42C1-9DD5-2C7E1B4F6A08}"),
        ]
        out = _unique_labels(pairs)
        self.assertEqual(out[0][0], "USB Mic (1) [76C9D41D]")
        self.assertEqual(out[1][0], "USB Mic (2) [F0E9B831]")

    def test_duplicate_without_extractable_suffix_still_unique(self):
        out = _unique_labels([("Weird", "@device_odx^?\\x"),
                              ("Weird", "@device_odx^?\\y")])
        self.assertEqual([lab for lab, _name, _alt in out],
                         ["Weird (1)", "Weird (2)"])

    def test_suffix_extraction_empty_for_unrecognized_ids(self):
        self.assertEqual(_device_id_suffix(""), "")
        self.assertEqual(_device_id_suffix("@device_odx^?xyz"), "")


class AppDuplicateDeviceTests(unittest.TestCase):
    """同名キャプチャーデバイスが2台でも両方コンボに現れ、別IDを選べる。"""

    DUP_TEXT = (
        "DirectShow video devices (some may be both video and audio devices):\n"
        '  "HDMI Capture"\n'
        '     Alternative name "@device_pnp_\\\\?\\usb#vid_07ca&pid_3513&mi_00#6&189c91c8&0&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\\global"\n'
        '  "HDMI Capture"\n'
        '     Alternative name "@device_pnp_\\\\?\\usb#vid_07ca&pid_3513&mi_00#7&183c1a2c&0&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\\global"\n'
        "DirectShow audio devices:\n"
        '  "マイク(USB)"\n'
        '     Alternative name "@device_cm_{33D9A762-90C8-11D0-BD43-00A0C911CE86}\\wave_{76C9D41D-2DC5-4D26-961A-1538F0783150}"\n'
    )

    def test_two_same_name_video_devices_are_both_selectable(self):
        import tkinter as tk
        import pass_through_gui as mod
        with tempfile.TemporaryDirectory() as d:
            root = tk.Tk()
            root.withdraw()
            original = mod.run_list_devices
            try:
                mod.run_list_devices = lambda: self.DUP_TEXT
                app = mod.App(root, config_path=os.path.join(d, "cfg.json"))
                values = list(app.video_combo["values"])
                self.assertEqual(len(values), 2)             # 2台とも表示される
                self.assertIn("HDMI Capture (1)", values[0])
                self.assertIn("[6&189c91c8", values[0])
                self.assertIn("[7&183c1a2c", values[1])
                self.assertNotEqual(app._video_map[values[0]],
                                    app._video_map[values[1]])
                # 2台目を選ぶとその先のデバイスIDが設定・開始時に使われる
                app.video_combo.set(values[1])
                cfg = app._current_cfg()
                self.assertIn("&mi_00#7&183c1a2c", cfg["video_device_id"])
                self.assertEqual(len(app.audio_combo["values"]), 2)  # 空欄+マイク1台
            finally:
                mod.run_list_devices = original
                root.destroy()


class TranslationTests(unittest.TestCase):
    def test_ja_translation(self):
        self.assertEqual(tr("ja", "button.start"), "▶ 開始")

    def test_en_translation(self):
        self.assertEqual(tr("en", "button.start"), "▶ Start")

    def test_unknown_language_falls_back_to_japanese(self):
        self.assertEqual(tr("fr", "button.start"), "▶ 開始")

    def test_unknown_key_returns_key_itself(self):
        self.assertEqual(tr("ja", "no.such.key"), "no.such.key")

    def test_placeholder_formatting(self):
        self.assertEqual(tr("ja", "status.detected", v=2, a=1),
                         "検出: 映像 2 / 音声 1")

    def test_en_detected_formatting(self):
        self.assertEqual(tr("en", "status.detected", v=2, a=1),
                         "Detected: 2 video / 1 audio")

    def test_all_languages_cover_same_keys(self):
        self.assertEqual(set(TRANSLATIONS["ja"]), set(TRANSLATIONS["en"]))

    def test_languages_are_ja_and_en(self):
        self.assertEqual(set(LANGUAGES), {"ja", "en"})


if __name__ == "__main__":
    unittest.main()
