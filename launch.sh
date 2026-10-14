#!/bin/sh
# Match the Miyoo Flip environment from SpruceOS App/PyUI/launch.sh.
cd /usr/miyoo/bin || exit 1
export PYSDL2_DLL_PATH="/mnt/SDCARD/App/PyUI/dll"
mkdir -p /mnt/SDCARD/Saves/spruce
LOG=/mnt/SDCARD/Saves/spruce/nightlight.log
{
  echo '=== Night Light v2.1 (SDL2 launcher fix) ==='
  date
  echo "PYSDL2_DLL_PATH=$PYSDL2_DLL_PATH"
  if [ ! -d "$PYSDL2_DLL_PATH" ]; then
    echo "ERROR: SpruceOS SDL2 directory missing: $PYSDL2_DLL_PATH"
    exit 1
  fi
  /mnt/SDCARD/spruce/flip/bin/python3 -c 'import sdl2; print("SDL2 import OK")' || {
    echo 'ERROR: SDL2 failed preflight import.'
    exit 1
  }
  /mnt/SDCARD/spruce/flip/bin/python3 -u /mnt/SDCARD/App/NightLight/native_menu.py
  result=$?
  echo "Exit status: $result"
  echo '=== End ==='
} > "$LOG" 2>&1
sync
sleep 1
