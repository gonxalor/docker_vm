#!/bin/bash

# Start Mosquitto
mosquitto -c /mosquitto/config/mosquitto.conf -d
sleep 1

# Start Dialog Manager with optional args from $DIALOG_PARAMS
python dialog_manager.py ${PARAMS} & 

# Start T2S2T with optional args from $TTS_PARAMS
exec python -u text2speech2text.py ${PARAMS} 2>/dev/null