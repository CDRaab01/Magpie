#!/bin/bash
# SessionStart hook — bootstrap the Magpie dev toolchain for Claude Code on the web.
#
# Two jobs:
#   1. Server (Python): install FastAPI deps so `pytest` / `ruff` work in a fresh web session.
#   2. Android: point Gradle at an Android SDK (always), and in a remote/web session install the
#      SDK + warm the Gradle cache so `./gradlew :app:testDebugUnitTest` / `:app:assembleDebug` /
#      Roborazzi work.
#
# NETWORK: the Android SDK/Gradle install needs egress to dl.google.com, maven.google.com,
# services.gradle.org, repo1.maven.org and plugins.gradle.org. If the environment's network
# policy blocks these, the install is SKIPPED with a clear message (the session still starts) —
# choose a policy that allows those hosts. See android/BUILD_ENVIRONMENT.md.
#
# Idempotent and non-interactive; safe to run every session (the container caches the result).
set -uo pipefail

log() { echo "[magpie:session-start] $*" >&2; }

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
ANDROID_DIR="$PROJECT_DIR/android"
SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/android-sdk}}"

write_local_properties() {
  # Gradle reads android/local.properties for sdk.dir (the file is gitignored). Only write it
  # once an SDK actually exists, so we never point Gradle at a non-existent directory.
  if [ -x "$SDK_ROOT/cmdline-tools/latest/bin/sdkmanager" ] || [ -d "$SDK_ROOT/platforms" ]; then
    echo "sdk.dir=$SDK_ROOT" > "$ANDROID_DIR/local.properties"
    log "wrote android/local.properties (sdk.dir=$SDK_ROOT)"
  fi
}

# Always safe — helps local sessions where the dev already has an SDK installed.
write_local_properties

# Everything below is heavier setup meant for a remote/web session only. A local session's dev
# already has their own venv + Android Studio SDK; don't mutate their machine.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# --- 1. Server Python deps -----------------------------------------------------------------
if command -v pip >/dev/null 2>&1; then
  log "installing server Python deps (pip install -e server[dev])..."
  pip install -e "$PROJECT_DIR/server[dev]" >/dev/null 2>&1 \
    && log "server deps ready" \
    || log "WARNING: server dep install failed — run 'pip install -e server[dev]' by hand"
fi

# --- 2. Android SDK ------------------------------------------------------------------------
CMDLINE_VER="11076708"  # Android command-line tools build (pin so the hook is reproducible)
SDKMGR="$SDK_ROOT/cmdline-tools/latest/bin/sdkmanager"

if [ ! -x "$SDKMGR" ]; then
  log "installing Android command-line tools..."
  tmp="$(mktemp -d)"
  if curl -fsSL --max-time 120 -o "$tmp/cmdline.zip" \
      "https://dl.google.com/android/repository/commandlinetools-linux-${CMDLINE_VER}_latest.zip" \
      && command -v unzip >/dev/null 2>&1 \
      && unzip -q "$tmp/cmdline.zip" -d "$tmp"; then
    mkdir -p "$SDK_ROOT/cmdline-tools"
    rm -rf "$SDK_ROOT/cmdline-tools/latest"
    mv "$tmp/cmdline-tools" "$SDK_ROOT/cmdline-tools/latest"
    rm -rf "$tmp"
  else
    rm -rf "$tmp"
    log "WARNING: could not fetch Android command-line tools (network policy?)."
    log "Allow dl.google.com + maven.google.com + services.gradle.org, then restart the session."
    exit 0
  fi
fi

export ANDROID_SDK_ROOT="$SDK_ROOT" ANDROID_HOME="$SDK_ROOT"
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  {
    echo "export ANDROID_SDK_ROOT=$SDK_ROOT"
    echo "export ANDROID_HOME=$SDK_ROOT"
  } >> "$CLAUDE_ENV_FILE"
fi

# Note the platform ID: API 37 uses minor-versioned platforms (`android-37.0`), not `android-37`.
log "installing SDK packages (platform-tools, platforms;android-37.0, build-tools;37.0.0)..."
yes | "$SDKMGR" --sdk_root="$SDK_ROOT" --licenses >/dev/null 2>&1 || true
if "$SDKMGR" --sdk_root="$SDK_ROOT" --install \
    "platform-tools" "platforms;android-37.0" "build-tools;37.0.0" >/dev/null 2>&1; then
  write_local_properties
else
  log "WARNING: sdkmanager install failed (network policy?). Skipping SDK packages."
  exit 0
fi

# Warm the Gradle distribution + AGP/deps cache so the first in-session build is fast. The Pulse
# sibling checkout must be present for the composite build (includeBuild(\"../../Pulse\")).
if [ -x "$ANDROID_DIR/gradlew" ]; then
  log "warming the Gradle cache (best-effort)..."
  ( cd "$ANDROID_DIR" && ./gradlew :app:help --no-daemon >/dev/null 2>&1 ) \
    && log "Android toolchain ready." \
    || log "WARNING: Gradle warm-up failed (services.gradle.org / Pulse checkout?). Build may be slow on first run."
fi
