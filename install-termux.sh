#!/data/data/com.termux/files/usr/bin/bash
set -e
pkg update -y
pkg install -y python ffmpeg git
python -m pip install --upgrade pip
mkdir -p "$HOME/MovieAutoPublisher"
echo "Install complete. Copy this project into ~/MovieAutoPublisher and run: python process.py"
