# Third-Party Notices / 第三者配布物について

## FFmpeg (GPL v3)

This application bundles, in its built `.exe`, binaries from the FFmpeg project
— `ffmpeg.exe`, `ffplay.exe` and their shared libraries (`avcodec`, `avformat`,
`avutil`, `avdevice`, `avfilter`, `swscale`, `swresample`, etc.) — and
distributes them as part of the packaged executable.

本アプリは、ビルド済み exe の中に FFmpeg プロジェクトの
`ffmpeg.exe` / `ffplay.exe` とその共有ライブラリ（`avcodec` / `avformat` /
`avutil` / `avdevice` / `avfilter` / `swscale` / `swresample` 等）を
同梱して配布します。

### Build identity / 同梱ビルドの識別子

| Item | Value |
|---|---|
| Version string | `ffmpeg version N-106550-g072101bd52-20220410` |
| Build date | 2022-04-10 |
| Platform | Windows x86_64 (win64), shared build |
| Key configure flags | `--enable-gpl --enable-version3` (among others) |

### License / ライセンス

The bundled FFmpeg build is licensed under the **GNU General Public License
v3** (due to `--enable-gpl --enable-version3`).

同梱している FFmpeg ビルドは **GPL v3** ライセンスです
（configure フラグ `--enable-gpl --enable-version3` による）。

- GPL v3 full text / 全文: <https://www.gnu.org/licenses/gpl-3.0.html>
- FFmpeg source (corresponding commit `g072101bd52` / 対応コミット):
  <https://git.ffmpeg.org/ffmpeg.git>
- Reproducible builds of this release / 再現ビルドの入手元:
  <https://github.com/BtbN/FFmpeg-Builds/releases>

### Relationship to this application / 本アプリとの関係

This application itself (the Python / tkinter source code in this repository)
is licensed under the **MIT License** and is independent of FFmpeg. FFmpeg
binaries are launched as separate processes (via `subprocess`) and are not
linked into the application code, so the GPL applies only to the bundled
FFmpeg binaries, not to the MIT-licensed source in this repository.

本アプリ自体（このリポジトリの Python / tkinter ソースコード）は
**MIT ライセンス** であり、FFmpeg とは独立しています。FFmpeg バイナリは
別プロセスとして起動されるだけでアプリのコードにリンクされていないため、
GPL は同梱バイナリ部分のみに適用され、このリポジトリの MIT ソースには
適用されません。

## Other / その他

- **Python** (PSF license) and **Tkinter/Tcl-Tk** — bundled into the exe by
  PyInstaller. See <https://docs.python.org/3/license.html> and
  <https://tcl.tk>.
- **PyInstaller** (GPL v2 with runtime exception) is used only as a build
  tool; its runtime exception covers the bundled bootloader.
  See <https://pyinstaller.org>.
