# Night Light

A warm light / blue light filter for spruceOS on the **Miyoo Flip v2**. Uses the
display's hardware gamma lookup table to reduce blue and green,
giving the screen a warmer tone.

## Install

1. Download `NightLight.zip` from the [latest release](https://github.com/heyseth/NightLight/releases/latest).
2. Extract the ZIP and copy the included `NightLight` folder into your SD card's `App` folder.
3. Check that `launch.sh` is at `App/NightLight/launch.sh`.
4. Open **Night Light** from the Apps menu in spruceOS.

## Usage

- Toggle **Warm light** with A or Left/Right.
- Adjust **Intensity** and **Orange tone** with Left/Right in 5% steps.
- Select **Apply & Exit** with A to apply and save changes.
- Select **Discard & Exit**, or press B, to cancel.

Changes take effect after the menu closes. To restore neutral colours, turn
**Warm light** off and select **Apply & Exit**. Settings are saved to
`/mnt/SDCARD/Saves/spruce/nightlight-settings.json`; there is no automatic
reapplication at boot.

## Performance

The filter uses display hardware with no background process or extra CPU/GPU
work during gameplay. No gameplay performance impact is expected.

## Compatibility

Tested on the **Miyoo Flip v2** with kernel `5.10.160`. Other spruceOS devices,
including the original Miyoo Flip, are unverified and should not be assumed
compatible.

The launcher uses the Flip-specific MainUI runtime path and `MIYOO_FLIP` device
configuration. The display driver requires an active **640x480 display**, a
**1024-entry gamma table**, and DRM atomic gamma support on `/dev/dri/card0`.
It refuses displays with a different resolution or gamma table size.

The hardware gamma approach may work on other devices with suitable display
drivers, but spruceOS alone does not guarantee compatibility. Supporting another
device would require adapting the launcher, detecting its display capabilities,
and testing on the hardware.
