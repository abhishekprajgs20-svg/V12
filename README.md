# TXT 2 SHORTS V12 — Universal Android source project

This project adapts the supplied V12 renderer to a touch-first Android app. It is configured to build for **ARM64 (`arm64-v8a`) and legacy 32-bit ARM (`armeabi-v7a`)** Android phones, with Android 7.0 / API 24 as the minimum target. This covers the CPU architectures used by the vast majority of Android phones; it does not include x86/x86_64 emulator builds.

## Status (v12.0.1)

Source project, built in the cloud by GitHub Actions (no Android SDK needed on your PC).
Fixed in this version: English fonts bundled (Open Sans), FFmpeg shipped as `libs/<abi>/libffmpegbin.so`
and run from the native-library folder (works on Android 10+), local `uharfbuzz` recipe for Hindi shaping,
pinned toolchain (buildozer 1.5.0, p4a v2024.01.21, NDK r25b, API 33), proper Android file picker,
automatic copy of finished videos to Movies, screen kept awake while rendering.
Tested on desktop Linux: parsing, Hindi + English rendering, full UI-to-video flow. NOT yet tested on a real phone.
If the Actions build fails, download the `build-log` artifact and send the first error.

## Device-adaptive behavior

- Reads Android `/proc/meminfo` to estimate installed RAM.
- Auto rendering uses one worker below 8 GB RAM and two workers at 8 GB or above; users can override with one or two workers.
- Unknown RAM defaults conservatively to one worker.
- CPU encoding is used; desktop NVENC / AMD AMF / Intel QSV are not assumed on phones.
- Lower-end phones may render more slowly. High resolution, long videos, multiple output formats, and video backgrounds increase memory and processing demands.

## Build on Ubuntu / WSL

1. Install Java 17, Android SDK command-line tools, Android NDK r25b, and Buildozer.
2. Obtain legally distributable Android FFmpeg builds for both ARM ABIs and integrate the ABI selection/staging step described above.
3. Verify the native dependency recipes for both ABIs.
4. From this folder run `buildozer android debug`.
5. Test the resulting APK on at least one 32-bit ARM device and one 64-bit ARM device, plus current Android versions, before distribution.

## Features and Android differences

The retained renderer includes the V12 themes, transitions, text/quiz parsing, animated overlays, intro/outro, explanation, watermark, music mixing, video backgrounds, chunked generation, and output-format definitions. The mobile UI replaces the original Windows Tkinter interface and Windows SAPI5 speech layer; Android voice generation uses Edge Neural TTS over the internet. Neural voice generation therefore needs a working internet connection.

The app has a Movies/Gallery export action using `androidstorage4kivy`. Android file-picker `content://` URI handling and storage behavior vary by Android version and provider; these paths still need end-to-end validation on real devices. A successful build alone is not proof of universal compatibility.

## Syntax check

```bash
python -m py_compile main.py engine_v12.py
```

## One-click GitHub cloud build (Windows)

The uploader is adapted from the user's previously working `upload_to_github.py` workflow. It uses the GitHub REST Git Database API directly; **Git for Windows is not required** and no local Git command is called.

Included files:

- `RUN_GITHUB_BUILDER.bat` — detects Python and automatically installs the `requests` package if missing.
- `upload_to_github.py` — finds this TXT 2 SHORTS project, creates or reuses a GitHub repository, uploads files through GitHub's API, tracks the workflow run for the exact commit, and downloads the APK artifact.
- `.github/workflows/android-apk.yml` — cloud Android build workflow.
- `scripts/build_ffmpeg_android.sh` — compiles Android-native FFmpeg + x264 for ARM64 and ARMv7 in the GitHub runner.

### What you need

1. Python 3.9 or newer installed on Windows and internet access.
2. A GitHub account.
3. A **GitHub classic Personal Access Token** with `repo` and `workflow` scopes. The token must be allowed to create repositories and update workflow files. Do not paste the token into chat or save it in a source file.
4. GitHub Actions enabled for the account/repository.

### Run it

1. Extract the complete ZIP.
2. Open the `txt2shorts_android` folder.
3. Double-click `RUN_GITHUB_BUILDER.bat`.
4. Enter the repository name, GitHub username and classic PAT when prompted. PAT entry is hidden. Choose private/public when creating a new repository.
5. Keep the window open. The uploader creates or reuses the repository, uploads this project's files using the GitHub API, waits for the matching Android workflow, and downloads `TXT2SHORTS_V12_Universal.apk` into this folder if the build succeeds.

The uploader preserves unrelated files in an existing repository and overlays the Android project files. It does not force-push or delete existing branch history. It does not require GitHub Desktop or Git for Windows.

### Common errors

- `HTTP 401`: token is invalid, expired, or revoked.
- `HTTP 403`: token permissions, repository creation rights, organization policy, Actions policy, or API rate limits may be blocking the request.
- `HTTP 404`: repository may not be accessible to the token, or the workflow/branch is not available.
- Upload succeeds but no Actions run appears: open the repository's **Actions** tab and enable GitHub Actions; check whether organization policy disables workflows.
- An Actions run appears and fails: open the printed build URL and inspect the first failed step. Share only the error/log, never the PAT.

### Important build caveat

The uploader can create/reuse the repository, upload source and retrieve the APK artifact. It does **not** guarantee that the Android project will compile successfully. The workflow must still pass Android SDK/NDK, FFmpeg/x264 compilation, python-for-android recipes for native dependencies, and physical-device tests. A failed build is reported as a build failure; it is not presented as a ready APK.
