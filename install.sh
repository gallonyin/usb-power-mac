#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd "$(dirname "$0")" && pwd)
bin_dir="$HOME/.local/bin"
target="$bin_dir/usb-power"
mkdir -p "$bin_dir"

if [[ -e $target || -L $target ]]; then
  if [[ $(readlink "$target" 2>/dev/null || true) != "$project_dir/usb-power" ]]; then
    backup="$target.backup-$(date +%Y%m%d%H%M%S)"
    mv "$target" "$backup"
    echo "Previous command saved as $backup"
  fi
fi
ln -sfn "$project_dir/usb-power" "$target"
chmod +x "$project_dir/usb-power" "$project_dir/open-usb-power.command"

if [[ :$PATH: != *":$bin_dir:"* ]]; then
  echo "Add this to your shell profile to use usb-power globally:"
  echo "  export PATH=\"$bin_dir:\$PATH\""
fi

echo "Installed $target"
echo "Run: usb-power web"
