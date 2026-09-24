#!/usr/bin/env bash
# Linux one-time USB setup for QuickTime (Valeria) screen capture.
#
# Distro usbmuxd cannot drive the iPhone's QuickTime USB alt-config, so the
# phone never exposes the H.264 interface ("no QT-capable config"). This
# script builds the usbmuxd fork (dynamic-config-switch branch, on top of
# upstream master which supports USBMUXD_DEFAULT_DEVICE_MODE) and switches
# the running systemd service to it with USBMUXD_DEFAULT_DEVICE_MODE=2.
# Follows docs/guides/valeria-linux-setup.md in the Valeria fork, adapted
# for Arch and Debian/Ubuntu.
#
# What it changes: build tools (if missing), /usr/local/{bin,lib,...}
# (libplist, libimobiledevice-glue, usbmuxd fork) and ONE systemd drop-in:
# /etc/systemd/system/usbmuxd.service.d/override.conf. The distro usbmuxd
# package (and its udev rules) is left installed; the drop-in only redirects
# ExecStart at the fork binary. Revert any time with: bash $0 --revert
#
# Needs root for install/configure/restart only (build runs as you).
# Exit codes: 0 ok, 1 error, 3 needs-root-while-non-interactive.
set -euo pipefail

FORK_URL="https://github.com/renegadelink/usbmuxd"
FORK_BRANCH="dynamic-config-switch"
UPSTREAM="https://github.com/libimobiledevice"
WORKDIR="${VALERIA_BUILD_DIR:-/tmp/freetunes-valeria-build}"
PREFIX="/usr/local"
FORK_BIN="$PREFIX/sbin/usbmuxd"
DROPIN_DIR="/etc/systemd/system/usbmuxd.service.d"
DROPIN_FILE="$DROPIN_DIR/override.conf"
SETUP_URL="https://github.com/renegadelink/pymobiledevice3/blob/feature/screen-mirror-browser-viewer/docs/guides/valeria-linux-setup.md"

BUILD_ONLY=0
REVERT=0
usage() {
  sed -n '2,/^set /p' "$0" | sed 's/^# \{0,1\}//'
  echo "usage: bash $(basename "$0") [--build-only] [--revert]"
  exit 0
}
for arg in "$@"; do
  case "$arg" in
    --build-only) BUILD_ONLY=1 ;;
    --revert) REVERT=1 ;;
    -h | --help) usage ;;
    *) echo "error: unknown flag $arg (see --help)" >&2; exit 1 ;;
  esac
done

log() { printf '[valeria-usb] %s\n' "$*"; }
die() { printf '[valeria-usb] ERROR: %s\n' "$*" >&2; exit 1; }

# Run "$@" as root. When there is no terminal to type the sudo password
# into (e.g. launched from the freetunes backend), fail fast with exit 3
# instead of hanging on a prompt nobody can answer.
with_sudo() {
  if [ "$(id -u)" = 0 ]; then "$@"; return; fi
  if sudo -n true 2>/dev/null; then sudo "$@"; return; fi
  if [ -t 0 ]; then sudo -v && sudo "$@"; return; fi
  echo "NEEDS-ROOT: this step needs root, and there is no terminal here" >&2
  echo "to type the sudo password into (you launched it from the web UI," >&2
  echo "an IDE runner, or a pipe — not a real terminal). Open a terminal" >&2
  echo "(konsole, gnome-terminal, …), cd to the repo, and run:" >&2
  echo "  bash $0" >&2
  echo "tip: run 'sudo -v' first to cache the password so it asks once." >&2
  exit 3
}

distro() { # arch | debian | unknown
  local id="" like=""
  if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    id="${ID:-}"
    like="${ID_LIKE:-}"
  fi
  case " $id $like " in
    *" arch "* | *" archlinux "* | *" manjaro "* | *" endeavouros "* | *" cachyos "*)
      echo arch ;;
    *" debian "* | *" ubuntu "* | *" linuxmint "* | *" pop "* | *" raspbian "*)
      echo debian ;;
    *) echo unknown ;;
  esac
}

missing_tools() {
  local missing=""
  local t
  for t in gcc make autoconf automake libtool pkg-config git; do
    command -v "$t" >/dev/null 2>&1 || missing="$missing $t"
  done
  if [ ! -f /usr/include/libusb-1.0/libusb.h ]; then missing="$missing libusb-headers"; fi
  printf '%s' "$missing"
}

install_deps() {
  local missing="$1"
  [ -z "$missing" ] && { log "build tools already present"; return; }
  log "installing build tools:$missing"
  case "$(distro)" in
    arch)
      # No -Syu on purpose: a full system upgrade must stay the user's own
      # decision. If the local db cannot satisfy this, say so plainly.
      with_sudo pacman -S --needed --noconfirm base-devel git libusb \
        || die "pacman could not install$missing — run 'sudo pacman -Syu' first, then re-run this script" ;;
    debian)
      with_sudo apt-get update
      with_sudo apt-get install -y autoconf automake libtool pkg-config \
        build-essential git libusb-1.0-0-dev ;;
    *)
      die "unknown distro — install by hand:$missing plus libusb headers, then re-run" ;;
  esac
}

clone_update() { # url dir [branch]
  local url="$1" dir="$2" branch="${3:-}"
  if [ -d "$dir/.git" ]; then
    log "updating $(basename "$dir")"
    git -C "$dir" fetch --depth 1 origin "${branch:-HEAD}" 2>/dev/null || git -C "$dir" fetch origin || true
    if [ -n "$branch" ]; then git -C "$dir" checkout -q "$branch" 2>/dev/null || true; fi
    git -C "$dir" pull --ff-only 2>/dev/null || true
  else
    log "cloning $(basename "$dir")${branch:+ ($branch)}"
    if [ -n "$branch" ]; then git clone --depth 1 -b "$branch" "$url" "$dir"
    else git clone --depth 1 "$url" "$dir"; fi
  fi
}

build_one() { # dir [extra-configure-args...]
  local dir="$1"; shift
  log "building $(basename "$dir")"
  (cd "$dir" && ./autogen.sh >/dev/null && ./configure --prefix="$PREFIX" "$@" >/dev/null && make -j"$(nproc)" )
}

install_one() { # dir
  log "installing $(basename "$1")"
  with_sudo make -C "$1" install
}

revert() {
  log "reverting to the distro usbmuxd (removes the systemd drop-in only)"
  with_sudo systemctl stop usbmuxd 2>/dev/null || true
  if [ -f "$DROPIN_FILE" ]; then with_sudo rm -f "$DROPIN_FILE"; fi
  with_sudo rmdir "$DROPIN_DIR" 2>/dev/null || true
  # Users of the old guide may have removed the distro package outright.
  if [ "$(distro)" = debian ] && [ ! -x /usr/sbin/usbmuxd ] && [ ! -x /usr/bin/usbmuxd ]; then
    log "distro usbmuxd binary missing — reinstalling the package"
    with_sudo apt-get install -y --reinstall usbmuxd
  fi
  with_sudo systemctl daemon-reload
  with_sudo systemctl restart usbmuxd
  with_sudo systemctl enable usbmuxd 2>/dev/null || true
  sleep 1
  systemctl is-active --quiet usbmuxd && log "reverted: $(systemctl show usbmuxd -p ExecStart | head -c 120)" \
    || die "usbmuxd did not come back — 'systemctl status usbmuxd' and 'journalctl -u usbmuxd -n 30' say why"
}

if [ "$REVERT" = 1 ]; then revert; exit 0; fi

mkdir -p "$WORKDIR"
install_deps "$(missing_tools)"
clone_update "$UPSTREAM/libplist" "$WORKDIR/libplist"
clone_update "$UPSTREAM/libimobiledevice-glue" "$WORKDIR/libimobiledevice-glue"
clone_update "$FORK_URL" "$WORKDIR/usbmuxd" "$FORK_BRANCH"

build_one "$WORKDIR/libplist"
build_one "$WORKDIR/libimobiledevice-glue"
build_one "$WORKDIR/usbmuxd" --without-preflight

if [ "$BUILD_ONLY" = 1 ]; then
  log "build-only done. Re-run without --build-only (needs root) to install and switch the service."
  exit 0
fi

install_one "$WORKDIR/libplist"
install_one "$WORKDIR/libimobiledevice-glue"
install_one "$WORKDIR/usbmuxd"
if command -v ldconfig >/dev/null 2>&1; then with_sudo ldconfig; fi

[ -x "$FORK_BIN" ] || die "fork binary missing after install: $FORK_BIN"
log "fork binary: $("$FORK_BIN" --version 2>/dev/null | head -1)"
grep -a -q USBMUXD_DEFAULT_DEVICE_MODE "$FORK_BIN" \
  || die "$FORK_BIN has no USBMUXD_DEFAULT_DEVICE_MODE support — wrong branch? expected $FORK_BRANCH"

# Mirror the distro unit's flags onto the fork binary, keeping only flags
# the fork understands (a renamed/removed flag would kill the service).
UNIT=""
for cand in /usr/lib/systemd/system/usbmuxd.service /lib/systemd/system/usbmuxd.service; do
  [ -f "$cand" ] && UNIT="$cand" && break
done
[ -n "$UNIT" ] || die "no usbmuxd.service unit found — is usbmuxd installed?"
OLD_START="$(grep -m1 '^ExecStart=' "$UNIT" | cut -d= -f2-)"
log "distro unit: $UNIT"
log "distro ExecStart: $OLD_START"
HELP="$("$FORK_BIN" --help 2>&1 || true)"
NEW_START="$FORK_BIN"
PREV_KEEP=0
# Word-split on purpose: ExecStart is a simple argv line.
# shellcheck disable=SC2086
for tok in $OLD_START; do
  case "$tok" in
    /*) continue ;; # the old binary path itself
    --*)
      name="${tok%%=*}"
      if printf '%s' "$HELP" | grep -q -F -- "$name"; then NEW_START="$NEW_START $tok"; PREV_KEEP=1
      else log "dropping unsupported flag $tok"; PREV_KEEP=0; fi ;;
    *) [ "$PREV_KEEP" = 1 ] && NEW_START="$NEW_START $tok" ;;
  esac
done
log "fork ExecStart: $NEW_START"

log "writing $DROPIN_FILE"
with_sudo mkdir -p "$DROPIN_DIR"
TMP_DROPIN="$(mktemp)"
printf '[Service]\nEnvironment=USBMUXD_DEFAULT_DEVICE_MODE=2\nExecStart=\nExecStart=%s\n' "$NEW_START" >"$TMP_DROPIN"
with_sudo cp "$TMP_DROPIN" "$DROPIN_FILE"
rm -f "$TMP_DROPIN"
with_sudo systemctl daemon-reload
with_sudo systemctl enable --now usbmuxd
sleep 2
systemctl is-active --quiet usbmuxd || {
  log "usbmuxd failed to start — last words:"
  journalctl -u usbmuxd --no-pager -n 30 2>/dev/null || systemctl status usbmuxd --no-pager
  die "service did not come up; revert with: bash $0 --revert"
}
SHOW="$(systemctl show usbmuxd -p ExecStart,Environment)"
printf '%s\n' "$SHOW" | grep -q '/usr/local' || die "service is not running the fork binary — revert with: bash $0 --revert"
printf '%s\n' "$SHOW" | grep -q 'USBMUXD_DEFAULT_DEVICE_MODE=2' || die "drop-in env did not apply — revert with: bash $0 --revert"
log "service is running the fork with USBMUXD_DEFAULT_DEVICE_MODE=2"

if command -v pymobiledevice3 >/dev/null 2>&1; then
  log "devices seen by pymobiledevice3:"
  pymobiledevice3 usbmux list 2>&1 | head -5 || true
fi
log "done. Replug the iPhone, tap Trust, then press Start QuickTime in freetunes."
log "If it still fails, the full guide is: $SETUP_URL"
