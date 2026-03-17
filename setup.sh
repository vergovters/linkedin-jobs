#!/usr/bin/env bash
# One-time setup: create venv, install deps, install Playwright Chromium.
# On Mac: double-click Setup.command instead. No IDE or system Python required if we download Python.

set -e
cd "$(dirname "$0")"
RELEASE="20260310"
PYBASE="cpython-3.10.20+${RELEASE}"
PYTHON_URL_MAC_ARM="https://github.com/astral-sh/python-build-standalone/releases/download/${RELEASE}/${PYBASE}-aarch64-apple-darwin-install_only.tar.gz"
PYTHON_URL_MAC_INTEL="https://github.com/astral-sh/python-build-standalone/releases/download/${RELEASE}/${PYBASE}-x86_64-apple-darwin-install_only.tar.gz"

find_python() {
  if [[ -x "./python/bin/python3" ]]; then
    echo "./python/bin/python3"
    return
  fi
  if command -v python3 &>/dev/null; then
    command -v python3
    return
  fi
  if command -v python &>/dev/null; then
    command -v python
    return
  fi
  echo ""
}

download_python_mac() {
  local arch
  arch=$(uname -m)
  local url=""
  if [[ "$arch" == "arm64" || "$arch" == "aarch64" ]]; then
    url="$PYTHON_URL_MAC_ARM"
  elif [[ "$arch" == "x86_64" ]]; then
    url="$PYTHON_URL_MAC_INTEL"
  fi
  if [[ -z "$url" ]]; then return 1; fi

  echo "Downloading Python into this folder (one-time, ~20 MB)..."
  if ! curl -sSLf -o python.tar.gz "$url"; then
    echo "Download failed. Install Python from https://www.python.org/downloads/ and run Setup again."
    return 1
  fi
  echo "Unpacking..."
  tar -xzf python.tar.gz
  rm -f python.tar.gz
  # Archive extracts to something like cpython-3.10.20+20260310-aarch64-apple-darwin-install_only/
  local dir
  for dir in ${PYBASE}-*-apple-darwin-install_only; do
    if [[ -d "$dir" ]]; then
      mv "$dir" python
      break
    fi
  done
  if [[ ! -x "./python/bin/python3" ]]; then
    echo "Unpack failed: python/bin/python3 not found."
    return 1
  fi
  echo "Python is ready in this folder."
  return 0
}

PY=$(find_python)
if [[ -z "$PY" ]]; then
  if [[ "$(uname -s)" == "Darwin" ]]; then
    if ! download_python_mac; then
      exit 1
    fi
    PY="./python/bin/python3"
  else
    echo "Python not found. Install it from https://www.python.org/downloads/"
    echo "Then run this script again."
    exit 1
  fi
fi

echo "Using: $PY"
"$PY" -m venv .venv
.venv/bin/pip install -q -r requirements.txt
.venv/bin/playwright install chromium

echo ""
echo "Setup complete. You can close this window."
echo "Next time: double-click Run.command (or run ./run.sh) to start the app."
