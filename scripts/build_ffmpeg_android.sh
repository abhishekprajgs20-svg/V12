#!/usr/bin/env bash
# Builds a small FFmpeg command-line tool (with libx264 + zlib/PNG support) for both Android ARM ABIs.
#
# IMPORTANT: the result is stored as libs/<abi>/libffmpegbin.so.  Android 10+ does NOT allow apps to
# execute files copied into their private data folder, but it DOES allow executing files that live in
# the app's native-library folder.  Buildozer packs everything in libs/<abi>/ there, and the app runs
# it from  ApplicationInfo.nativeLibraryDir/libffmpegbin.so .
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/.ffmpeg-build"
mkdir -p "$BUILD/src" "$BUILD/prefix"
NDK="${ANDROID_NDK_HOME:-${ANDROID_NDK_ROOT:-}}"
API="${ANDROID_API:-24}"
JOBS="$(nproc 2>/dev/null || echo 2)"
if [[ -z "$NDK" || ! -d "$NDK/toolchains/llvm/prebuilt" ]]; then
  echo "ANDROID_NDK_HOME must point to an installed Android NDK" >&2
  exit 1
fi
HOST_TAG="$(find "$NDK/toolchains/llvm/prebuilt" -mindepth 1 -maxdepth 1 -type d | head -n1 | xargs basename)"
TOOLCHAIN="$NDK/toolchains/llvm/prebuilt/$HOST_TAG/bin"
SYSROOT="$NDK/toolchains/llvm/prebuilt/$HOST_TAG/sysroot"

fetch_sources() {
  if [[ ! -d "$BUILD/src/x264/.git" ]]; then
    git clone --depth 1 --branch stable https://github.com/mirror/x264.git "$BUILD/src/x264"
  fi
  if [[ ! -f "$BUILD/src/ffmpeg/configure" ]]; then
    mkdir -p "$BUILD/src/ffmpeg"
    curl -L --fail --retry 3 https://codeload.github.com/FFmpeg/FFmpeg/tar.gz/refs/tags/n7.1.1 -o "$BUILD/ffmpeg.tar.gz"
    tar -xzf "$BUILD/ffmpeg.tar.gz" -C "$BUILD/src/ffmpeg" --strip-components=1
  fi
}

build_one() {
  local abi="$1" target="$2" arch="$3" cpu="$4" x264host="$5" asm="$6"
  local prefix="$BUILD/prefix/$abi"
  local fdir="$BUILD/ffmpeg-$abi"
  local cc="$TOOLCHAIN/${target}${API}-clang"
  local cxx="$TOOLCHAIN/${target}${API}-clang++"
  mkdir -p "$prefix" "$fdir"
  if [[ ! -x "$cc" ]]; then echo "Missing NDK compiler: $cc" >&2; exit 1; fi

  echo "==> Building x264 for $abi"
  rm -rf "$BUILD/x264-$abi"; cp -r "$BUILD/src/x264" "$BUILD/x264-$abi"
  pushd "$BUILD/x264-$abi" >/dev/null
  CC="$cc" CXX="$cxx" AR="$TOOLCHAIN/llvm-ar" RANLIB="$TOOLCHAIN/llvm-ranlib" STRIP="$TOOLCHAIN/llvm-strip" \
    ./configure --prefix="$prefix" --host="$x264host" --enable-static --enable-pic \
    --disable-cli --disable-opencl --disable-asm
  make -j"$JOBS"
  make install
  popd >/dev/null

  echo "==> Building FFmpeg for $abi"
  local asm_flag=()
  if [[ "$asm" == "noasm" ]]; then asm_flag=(--disable-asm); fi
  pushd "$fdir" >/dev/null
  PKG_CONFIG_PATH="$prefix/lib/pkgconfig" PKG_CONFIG_LIBDIR="$prefix/lib/pkgconfig" \
  "$BUILD/src/ffmpeg/configure" \
    --prefix="$prefix/ffmpeg-install" --target-os=android --arch="$arch" --cpu="$cpu" \
    --enable-cross-compile --cc="$cc" --cxx="$cxx" \
    --ar="$TOOLCHAIN/llvm-ar" --ranlib="$TOOLCHAIN/llvm-ranlib" \
    --strip="$TOOLCHAIN/llvm-strip" --nm="$TOOLCHAIN/llvm-nm" \
    --sysroot="$SYSROOT" --pkg-config=pkg-config --pkg-config-flags=--static \
    --extra-cflags="-I$prefix/include -fPIE -fPIC" \
    --extra-ldflags="-L$prefix/lib -pie -Wl,-z,max-page-size=16384" \
    --enable-gpl --enable-libx264 --enable-zlib --enable-static --disable-shared --enable-pic \
    --disable-doc --disable-debug --disable-autodetect --enable-ffmpeg \
    --disable-ffplay --disable-ffprobe "${asm_flag[@]}"
  make -j"$JOBS"
  make install
  popd >/dev/null

  mkdir -p "$ROOT/libs/$abi"
  install -m 755 "$prefix/ffmpeg-install/bin/ffmpeg" "$ROOT/libs/$abi/libffmpegbin.so"
  "$TOOLCHAIN/llvm-strip" "$ROOT/libs/$abi/libffmpegbin.so" || true
  # The binary is an ARM executable and cannot run on the x86 CI machine, so inspect it statically.
  file "$ROOT/libs/$abi/libffmpegbin.so"
  grep -aq "libx264" "$ROOT/libs/$abi/libffmpegbin.so" || { echo "libx264 missing in $abi build" >&2; exit 1; }
  echo "Built $abi FFmpeg: $(du -h "$ROOT/libs/$abi/libffmpegbin.so" | cut -f1)"
}

fetch_sources
build_one arm64-v8a   aarch64-linux-android      aarch64 armv8-a  aarch64-linux-android   asm
build_one armeabi-v7a armv7a-linux-androideabi   arm     armv7-a  arm-linux-androideabi   noasm
