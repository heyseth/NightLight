#!/bin/sh
# Match the Miyoo Flip environment from SpruceOS App/PyUI/launch.sh.
cd /usr/miyoo/bin || exit 1
export PYSDL2_DLL_PATH="/mnt/SDCARD/App/PyUI/dll"
mkdir -p /mnt/SDCARD/Saves/spruce
LOG=/mnt/SDCARD/Saves/spruce/nightlight.log
{
  echo '=== Night Light v2.2 (persistent native menu) ==='
  date
  echo "PYSDL2_DLL_PATH=$PYSDL2_DLL_PATH"
  if [ ! -d "$PYSDL2_DLL_PATH" ]; then
    echo "ERROR: SpruceOS SDL2 directory missing: $PYSDL2_DLL_PATH"
    exit 1
  fi
  /mnt/SDCARD/spruce/flip/bin/MainUI /mnt/SDCARD/App/NightLight/native_menu.py \
    -device MIYOO_FLIP \
    -logDir /mnt/SDCARD/Saves/spruce \
    -pyUiConfig /mnt/SDCARD/App/PyUI/py-ui-config.json \
    -cfwConfig /mnt/SDCARD/Saves/spruce/spruce-config.json \
    -optionListFile nightlight \
    -optionListTitle 'Night Light'
  result=$?
  echo "Exit status: $result"
  echo '=== End ==='
} > "$LOG" 2>&1
exit "$result"
