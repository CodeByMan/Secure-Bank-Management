#!/usr/bin/env bash
set -euo pipefail

# This script downloads third-party vendor assets into static/vendor.
# Run: ./scripts/install_vendor_assets.sh

VENDOR_DIR="$(pwd)/static/vendor"
mkdir -p "$VENDOR_DIR/nprogress"
mkdir -p "$VENDOR_DIR/alpine"

echo "Fetching NProgress..."
curl -L -o "$VENDOR_DIR/nprogress/nprogress.min.css" "https://cdnjs.cloudflare.com/ajax/libs/nprogress/0.2.0/nprogress.min.css"
curl -L -o "$VENDOR_DIR/nprogress/nprogress.min.js" "https://cdnjs.cloudflare.com/ajax/libs/nprogress/0.2.0/nprogress.min.js"

echo "Fetching Alpine.js..."
curl -L -o "$VENDOR_DIR/alpine/alpine.min.js" "https://cdn.jsdelivr.net/npm/alpinejs@3.13.3/dist/cdn.min.js"

echo "Vendor assets installed to $VENDOR_DIR"
