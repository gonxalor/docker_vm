#!/bin/bash

# Start Mosquitto in the background using your config file
# We run it with -d to daemonize it
echo "Starting Mosquitto Broker with custom config..."
mosquitto -c /mosquitto/config/mosquitto.conf -d

# Give Mosquitto a second to bind to the port
sleep 1

# Start Dialog Manager in the background
python dialog_manager.py & 

exec python -u text2speech2text.py 2>/dev/null
#python text2speech2text.py 
# Start User Interface in the foreground