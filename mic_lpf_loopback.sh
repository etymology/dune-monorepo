#!/usr/bin/env bash
set -euo pipefail

SRC='alsa_input.usb-C-Media_Electronics_Inc._USB_Audio_Device-00.mono-fallback'
OUT="${2:-$(pactl get-default-sink)}"

# First argument is cutoff frequency in Hz.
# Default: 10000 Hz.
CUTOFF_HZ="${1:-3000}"

# More stages = steeper low-pass rolloff.
STAGES="${STAGES:-100}"

LPF_MODULE="$(
  pactl load-module module-ladspa-sink \
    sink_name="mic_lpf_${CUTOFF_HZ}hz" \
    master="$OUT" \
    plugin=lowpass_iir_1891 \
    label=lowpass_iir \
    control="${CUTOFF_HZ},${STAGES}" \
    sink_properties=device.description="Mic low-pass ${CUTOFF_HZ}Hz"
)"

LOOP_MODULE="$(
  pactl load-module module-loopback \
    source="$SRC" \
    sink="mic_lpf_${CUTOFF_HZ}hz" \
    latency_msec=20
)"

echo "Source:      $SRC"
echo "Output sink: $OUT"
echo "Cutoff:      ${CUTOFF_HZ} Hz"
echo "Stages:      $STAGES"
echo
echo "LPF module:  $LPF_MODULE"
echo "Loop module: $LOOP_MODULE"
echo
echo "Unload with:"
echo "pactl unload-module $LOOP_MODULE"
echo "pactl unload-module $LPF_MODULE"