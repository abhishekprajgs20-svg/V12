[app]
title = TXT 2 SHORTS V12
package.name = txt2shorts
package.domain = com.quizinox
source.dir = .
source.include_exts = py,kv,ttf,txt,png,jpg
source.exclude_dirs = .buildozer,.ffmpeg-build,.github,scripts,bin,libs,p4a-recipes,__pycache__
version = 12.0.1
orientation = portrait
fullscreen = 0

# --- Python packages -------------------------------------------------------------------------
# uharfbuzz has a local recipe in ./p4a-recipes (HarfBuzz shaping for Hindi / Devanagari).
# freetype-py + harfbuzz + freetype + pillow + numpy use the official python-for-android recipes.
# aiohttp (and its helper packages) are required by edge-tts for the online neural voices.
requirements = python3,hostpython3,kivy==2.3.0,pyjnius,android,pillow,numpy,freetype-py,uharfbuzz,edge-tts,aiohttp,multidict==6.0.5,yarl==1.9.4,frozenlist==1.4.1,aiosignal==1.3.1,attrs,async-timeout==4.0.3,charset-normalizer==2.1.1,idna,certifi,tabulate,typing-extensions,plyer,androidstorage4kivy

# Pinned, known-compatible toolchain (buildozer 1.5.0 + python-for-android v2024.01.21 + NDK 25b)
p4a.branch = v2024.01.21
p4a.local_recipes = ./p4a-recipes

# --- Android ---------------------------------------------------------------------------------
# The picker (Android system file chooser) needs no storage permission; INTERNET is for the online voice.
android.permissions = INTERNET,ACCESS_NETWORK_STATE,WAKE_LOCK
android.api = 33
android.minapi = 24
android.ndk = 25b
android.ndk_api = 24
android.archs = arm64-v8a,armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = False
android.private_storage = True

# FFmpeg is shipped as a *native library* (libs/<abi>/libffmpegbin.so, built by
# scripts/build_ffmpeg_android.sh).  Android 10+ refuses to execute files from the app's data folder
# but allows executing files from the native-library folder, so this is the only reliable way.
android.add_libs_arm64_v8a = libs/arm64-v8a/*.so
android.add_libs_armeabi_v7a = libs/armeabi-v7a/*.so

[buildozer]
log_level = 2
warn_on_root = 0
