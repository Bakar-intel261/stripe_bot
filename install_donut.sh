#!/bin/bash
# install_donut.sh - Installs Donut Browser on Ubuntu

set -e

echo "📦 Installing Donut Browser..."

# Install dependencies
sudo apt-get update
sudo apt-get install -y \
    wget \
    libfuse2 \
    libx11-xcb1 \
    libxcb-dri3-0 \
    libdrm2 \
    libgbm1 \
    libasound2

# Download Donut
wget -O /tmp/donut.AppImage https://github.com/DonutBrowser/donut-browser/releases/latest/download/donut-latest.AppImage
chmod +x /tmp/donut.AppImage

# Extract and run
cd /tmp
./donut.AppImage --appimage-extract
mkdir -p ~/.local/bin
mv squashfs-root ~/.local/bin/donut

# Start Donut
nohup ~/.local/bin/donut/AppRun &

echo "✅ Donut Browser installed!"