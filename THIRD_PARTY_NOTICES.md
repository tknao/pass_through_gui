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
- FFmpeg source — corresponding commit `072101bd52` / 対応コミット
  （バージョン文字列 `N-106550-g072101bd52` の `g` は git-describe が付ける
  マーカーで、ハッシュの一部ではありません）:
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

### If you redistribute the exe / exe を再配布する場合

The bundled FFmpeg binaries stay under GPLv3 wherever they travel. If you
redistribute this `.exe` (in whole or in part), the GPL obligations for the
FFmpeg portion travel with it — in short: include this notice and the GPL v3
text with the binary, and provide (or offer to provide) the Corresponding
Source of the FFmpeg build you ship — the upstream repository and commit
listed above, or the reproducible BtbN build it came from. The MIT license of
the app source is unaffected.

同梱 FFmpeg バイナリは、どこへ配布しても GPLv3 のままです。この exe を
（全部でも一部でも）再配布する場合は、FFmpeg 部分に対する GPLv3 の義務も
一緒に移動します。要点は、**この notice と GPL v3 本文をバイナリに随伴**し、
同梱した FFmpeg ビルドの **Corresponding Source（上記のアップストリーム
リポジトリとコミット、または由来となった BtbN の再現ビルド）を提供する
（または提供を申し出る）** ことです。アプリソースの MIT ライセンスには
影響ありません。

Our GitHub Releases therefore ship: `pass_through_gui.exe` +
`THIRD_PARTY_NOTICES.md` + `gpl-3.0.txt`.

## Other / その他

- **Python** (PSF license) and **Tkinter/Tcl-Tk** — bundled into the exe by
  PyInstaller. See <https://docs.python.org/3/license.html> and
  <https://tcl.tk>.
- **PyInstaller** (GPL v2 with runtime exception) is used only as a build
  tool; its runtime exception covers the bundled bootloader.
  See <https://pyinstaller.org>.
- **SDL2** (zlib license) — statically linked into the bundled `ffplay.exe`
  (the FFmpeg build is configured with `--enable-sdl2`, and no SDL2 DLL is
  shipped). See <https://www.libsdl.org>.
