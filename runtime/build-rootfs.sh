#!/usr/bin/env bash
# Build the private Kali rootfs for Kali Linux Windows Substitute.
#
# This runs on a Linux build host (Kali, Debian or Ubuntu, or inside WSL/CI).
# It needs root, debootstrap, and python3 + pyyaml on the host.
#
# Result:
#   runtime/dist/kalisub-rootfs.tar.gz   <- import with: wsl --import KaliSubstitute ...
#
# Typical use on a machine that already has WSL2 + a Debian/Ubuntu distro:
#
#   sudo apt-get update && sudo apt-get install -y debootstrap python3-yaml
#   sudo ./runtime/build-rootfs.sh
#
# Then, from Windows, the app's "Set up runtime" button imports the tarball.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
WORK="$HERE/.work/rootfs"
OUT_DIR="$HERE/dist"
OVERLAY="$HERE/rootfs"

MIRROR="${KALI_MIRROR:-http://http.kali.org/kali}"
SUITE="${KALI_SUITE:-kali-rolling}"

# Baseline packages: a small, safe, high-value starter set. Everything else is
# installed on demand from inside the app.
BASELINE_PACKAGES=(
  ca-certificates curl wget gnupg less file
  unzip
  kali-archive-keyring
  python3
  dnsutils whois nmap
  whatweb
  sqlmap gobuster ffuf wordlists dirb
  hydra john hashcat
  tcpdump tshark
  netcat-traditional socat
  foremost binwalk testdisk libimage-exiftool-perl sleuthkit
)

require_root() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "please run as root (sudo $0)" >&2
    exit 1
  fi
}

check_tools() {
  for tool in debootstrap tar gzip python3; do
    command -v "$tool" >/dev/null 2>&1 || {
      echo "missing build tool: $tool" >&2
      exit 1
    }
  done
  python3 -c "import yaml" 2>/dev/null || {
    echo "python3 needs PyYAML (apt-get install python3-yaml)" >&2
    exit 1
  }
}

bootstrap() {
  echo "==> bootstrapping $SUITE from $MIRROR"
  rm -rf "$WORK"
  mkdir -p "$WORK"

  # Some hosts ship debootstrap without the Kali suite script. Kali is
  # Debian-based, so the Debian "sid" script is a safe stand-in. We also
  # install kali-archive-keyring explicitly: without it apt inside the image
  # cannot verify the Kali mirror, and every tool install would fail later.
  local scripts=/usr/share/debootstrap/scripts
  if [ ! -e "$scripts/$SUITE" ] && [ -e "$scripts/sid" ]; then
    echo "    debootstrap has no '$SUITE' script; aliasing to sid"
    cp "$scripts/sid" "$scripts/$SUITE"
  fi

  debootstrap --variant=minbase --arch=amd64 \
    --include=apt,gnupg,ca-certificates,kali-archive-keyring \
    "$SUITE" "$WORK" "$MIRROR"
}

enter_chroot() {
  mount --bind /dev "$WORK/dev"
  mount -t proc proc "$WORK/proc"
  mount -t sysfs sys "$WORK/sys"
  trap 'umount -l "$WORK/dev" "$WORK/proc" "$WORK/sys" 2>/dev/null || true' EXIT
}

install_packages() {
  echo "==> installing baseline packages inside the image"
  chroot "$WORK" /bin/bash -c "
    set -e
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y --no-install-recommends ${BASELINE_PACKAGES[*]}
    apt-get clean
    rm -rf /var/lib/apt/lists/*
  "
}

verify_apt() {
  # Guard against shipping an image whose apt cannot verify the mirror (for
  # example a missing kali-archive-keyring). If this fails, tool install and
  # uninstall would be broken for every user, so fail the build loudly.
  echo "==> verifying apt inside the image"
  chroot "$WORK" /bin/bash -c "
    set -e
    apt-get update -qq
    apt-get clean
    rm -rf /var/lib/apt/lists/*
  "
}

install_overlay() {
  echo "==> installing overlay + agent"
  mkdir -p "$WORK/etc/kalisub" "$WORK/usr/local/bin" "$WORK/usr/local/lib/kalisub" "$WORK/var/log"
  cp -r "$OVERLAY/." "$WORK/"
  cp "$HERE/agent/agent.py" "$WORK/usr/local/lib/kalisub/agent.py"
  cp "$HERE/rootfs/usr/local/bin/kalisub-agent-start" "$WORK/usr/local/bin/kalisub-agent-start"
  chmod +x "$WORK/usr/local/bin/kalisub-agent-start"

  python3 "$HERE/tools/make_manifest.py" "$REPO_ROOT/catalog/tools.yaml" \
    "$WORK/etc/kalisub/tools.json"

  # Placeholder token. The Windows app rewrites this on first provision.
  cat > "$WORK/etc/kalisub/agent.env" <<'EOF'
AGENT_TOKEN=change-me-on-first-run
KALISUB_PORT=5055
EOF
  chmod 600 "$WORK/etc/kalisub/agent.env"

  verify_apt
}

pack() {
  echo "==> packing rootfs"
  mkdir -p "$OUT_DIR"
  tar -C "$WORK" -czf "$OUT_DIR/kalisub-rootfs.tar.gz" --numeric-owner .
  sha256sum "$OUT_DIR/kalisub-rootfs.tar.gz" | tee "$OUT_DIR/kalisub-rootfs.tar.gz.sha256"
  echo "==> done: $OUT_DIR/kalisub-rootfs.tar.gz"
}

require_root
check_tools
bootstrap
enter_chroot
install_packages
install_overlay
echo "==> unmounting the chroot"
umount -l "$WORK/dev" "$WORK/proc" "$WORK/sys" 2>/dev/null || true
trap - EXIT
pack
echo "==> done. Import it with the app's 'Set up runtime' button."
