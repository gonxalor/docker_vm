#!/bin/bash

# Start Mosquitto
mosquitto -c /mosquitto/config/mosquitto.conf -d
sleep 1

# Start Dialog Manager with optional args from $DIALOG_PARAMS\
python dialog_manager.py ${DIALOG_PARAMS} > /dev/null 2>&1 &
#python -u dialog_manager.py ${DIALOG_PARAMS} & 

# Start T2S2T with optional args from $TTS_PARAMS
exec python -u text2speech2text.py ${TTS_PARAMS} 2>/dev/null

wait -n