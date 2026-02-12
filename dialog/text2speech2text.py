import argparse
import paho.mqtt.client as mqtt
import time
import json
import queue
import uuid
import whisper
import os
from helpers.audio_manager import AudioManager
from datetime import datetime, timezone


# ---------------- MQTT CONFIG ---------------- #
#BROKER = "mqtt01.carma"  # replace with broker IP
BROKER = os.getenv('MQTT_BROKER', 'mosquitto')
#BROKER = os.getenv('MQTT_BROKER', 'localhost')
PORT = int(os.getenv('MQTT_PORT', 1883))
USERNAME = os.getenv('USERNAME', 'inesc')
PASSWORD = os.getenv('PASSWORD', 'inesc')


def transcribe_wav_file(file_path):
    # 2. Define the path to your WAV file
    wav_file_path = file_path

    try:
        # 3. Transcribe the audio
        result = model.transcribe(wav_file_path, fp16=False) # fp16=False is for CPU usage
        time.sleep(2)
        return result['text'].strip()

    except FileNotFoundError:
        print(f"Error: File not found at {wav_file_path}. Please check the path.")
    except Exception as e:
        print(f"An error occurred during transcription: {e}")

# ------------------ Argument Parser ------------------ #
def parse_args():
    parser = argparse.ArgumentParser(description="Speech module with MQTT and Whisper models.")
    parser.add_argument(
        "-m", "--model",
        choices=["tiny", "base", "small", "medium", "large"],
        default="base",
        help="Whisper model to use (default: base)"
    )
    parser.add_argument(
        "-l", "--language",
        choices=["en", "es", "fr"],
        default="en",
        help="Language used for the text-to-speech and speech-to-text (default: english)"
    )
    parser.add_argument(
        "-rn", "--robotname",
        default="TEC800",
        help="Language used for the text-to-speech and speech-to-text (default: english)"
    )
    return parser.parse_args()

# ------------------ Queues ------------------ #
tts_queue = queue.Queue()
victim_id_queue = queue.Queue()

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ Connected to broker")
        # Subscribe to TTS topic
        speech_client.subscribe(f"victim/text2speech2text/tts-{userdata}")
        speech_client.subscribe(f"dialogmanager/victim_id/{userdata}")
        speech_client.subscribe("victim/dialogmanager2/lwt")
        speech_client.publish("victim/text2speech2text/lwt", "online")    
    else:
        print("❌ Bad connection. Returned code=", rc)

# ------------------ MQTT CALLBACK ------------------ #
def on_tts_message(client, userdata, msg):
    """Receive TTS message from Dialog Manager and add to queue"""
    msg_topic = msg.topic
    if msg_topic == "victim/dialogmanager2/lwt":
        print(f"Dialog Manager status update: {msg.payload.decode()}")
    elif msg_topic == f"dialogmanager/victim_id/{userdata}":
        loaded_msg = json.loads(msg.payload.decode())
        data = loaded_msg["data"]
        victim_id = data["victim_id"]
        victim_id_queue.put(victim_id)
        print("victim_id: ", victim_id)
    else:
        try:
            loaded_msg = json.loads(msg.payload.decode())
            data = loaded_msg["data"]
            message = data["message"]
            print(f"\nUGV: {message}\n")
            tts_queue.put(data)
        except Exception as e:
            print(f"Error in MQTT callback: {e}")

def wait_for_help(audio_manager,speech_client,robotname):
    while True:
        # After speaking, record speech from user
        if language == "en":
            keyword = "help"
        elif language == "es":
            keyword = "ayuda"
        elif language == "fr":
            keyword = "bonjour"    
                
        new_msg = audio_manager.speech_to_text(max_duration=8)
        if keyword in new_msg.lower():
            # Prepare JSON message and publish STT result
            victim_id = str(uuid.uuid4())
            json_msg = {
                "header": {
                    "sender": "speechModule",
                    "msg_id": str(uuid.uuid4()),
                    "utc_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "msg_type": "Victim's message",
                    "msg_content": f"victim/text2speech2text/stt-{robotname}"
                },
                "data": {
                    "victim_id": victim_id,
                    "message": new_msg,
                }
            }
            speech_client.publish(f"victim/text2speech2text/stt-{robotname}", json.dumps(json_msg), retain=True)
            print(f"\nVICTIM: {new_msg}")
            break

def wait_for_c2():
    print("waiting for victim_id from the C2")
    victim_id = victim_id_queue.get()
    json_msg = {
                "header": {
                    "sender": "speechModule",
                    "msg_id": str(uuid.uuid4()),
                    "utc_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "msg_type": "Victim's message",
                    "msg_content": f"victim/text2speech2text/stt-{robotname}"
                },
                "data": {
                    "victim_id": victim_id,
                    "message": "Help",
                }
    }
    speech_client.publish(f"victim/text2speech2text/stt-{robotname}", json.dumps(json_msg), retain=True)
    return victim_id

# ------------------ MAIN SCRIPT ------------------ #
if __name__ == "__main__":
    args = parse_args()
    whisper_model = args.model
    language = args.language
    robotname = args.robotname
    print(f"[Speech Module] Using Whisper model: {whisper_model}")

    # Initialize AudioManager (loads Whisper model, configures TTS & recording)
    audio_manager = AudioManager(whisper_model=whisper_model,language=language,local=False)

    # Initialize MQTT client
    speech_client = mqtt.Client(userdata=robotname)
    speech_client.will_set("victim/text2speech2text/lwt", "offline")
    speech_client.on_connect = on_connect
    speech_client.on_message = on_tts_message
    speech_client.username_pw_set(USERNAME,PASSWORD)
    speech_client.connect(BROKER, PORT)
    speech_client.loop_start()

    
    #wait_for_help(audio_manager,speech_client,robotname)
    print("-----------------------:", robotname)
    victim_id = wait_for_c2()
    print("Its not waiting")
    n = 0
    while True:
        try:
            # Check if there is a new TTS message
            data = tts_queue.get_nowait()
            tts_text = data["message"]
            last_message = data["last_message"]
            
            # Speak the message (blocking is OK in main thread)
            audio_manager.text_to_speech(tts_text, blocking=True)

            print("THIS IS THE ROBOTNAME: ", robotname)
            if not last_message:
                # After speaking, record speech from user

                new_msg = audio_manager.speech_to_text(max_duration=8)
                # Prepare JSON message and publish STT result
                json_msg = {
                    "header": {
                        "sender": "speechModule",
                        "msg_id": str(uuid.uuid4()),
                        "utc_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "msg_type": "Victim's message",
                        "msg_content": f"victim/text2speech2text/stt-{robotname}"
                    },
                    "data": {
                        "victim_id": victim_id,
                        "message": new_msg
                        

                    }
                }
                speech_client.publish(f"victim/text2speech2text/stt-{robotname}", json.dumps(json_msg))
                print(f"\nVICTIM: {new_msg}")
            else:
                break    

        except queue.Empty:
            # No TTS messages pending, just sleep briefly
            time.sleep(0.1)
        except Exception as e:
            print(f"Error in main loop: {e}")
