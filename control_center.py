import paho.mqtt.client as mqtt
import time
import json
import uuid
import os
from datetime import datetime, timezone

#BROKER = "mqtt01.carma"
BROKER = os.getenv('MQTT_BROKER', 'localhost')
PORT = int(os.getenv('MQTT_PORT', 1883))
USERNAME = os.getenv('USERNAME', 'inesc')
PASSWORD = os.getenv('PASSWORD', 'inesc')


class Mqtt_client:
    def __init__(self):
        self.cc_client = mqtt.Client()
        self.cc_client.will_set("victim/controlcenter/lwt", "offline")
        self.cc_client.on_connect = self.on_connect
        self.cc_client.on_message = self.on_message
        self.cc_client.username_pw_set(USERNAME,PASSWORD)
        self.cc_client.connect(BROKER, PORT)

    def on_connect(self,client, userdata, flags, rc):
        if rc == 0:
            print("✅ Connected to broker")
            client.subscribe("victim/dialogmanager/report")
            client.subscribe("victim/dialogmanager/lwt")
            print("Subscribed to victim/dialogmanager/report")
            client.publish("victim/controlcenter/lwt", "online")
        else:
            print("❌ Bad connection. Returned code=", rc)

    def show_status(self,status):
        print("Victim Status Report:\n")
        for key in status:
            print(f" - {key}: {status[key]}")
                
    def on_message(self,client, userdata, msg):
        if msg.payload.decode() != "":
            msg_topic = msg.topic
            if msg_topic == "victim/dialogmanager/lwt":
                print(f"Dialog Manager status update: {msg.payload.decode()}")
            else:    
                print(f"📩 Message received on {msg.topic}")
                try:
                    payload = msg.payload.decode()
                    json_object = json.loads(payload)
                    print(json_object["data"])
                    if not json_object["data"]["victim_id"]:
                        victim_id = str(uuid.uuid4())
                        new_msg = {
                            "header": {
                                "sender": "Crimson",
                                "msg_id": str(uuid.uuid4()),
                                "utc_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                "msg_type": "creation",
                                "msg_content": "victim/controlcenter/victim_id"
                            },
                            "data": {
                                "victim_id": victim_id,
                            }
                        }
                        self.cc_client.publish("victim/controlcenter/victim_id", json.dumps(new_msg), retain=True)
                    else:
                        status_report = json_object["data"]
                        self.show_status(status_report)
                        self.cc_client.publish("victim/dialogmanager/report", payload="", qos=1, retain=True)
                except Exception as e:
                    print("Error parsing message:", e, msg.payload)

def send_context(cc_client):
    # 🔹 Dialog Manager is asking for empathy level
    context = situationType[0]
    cc_client.waiting_for_message = True

    new_msg = {
        "header": {
            "sender": "Crimson",
            "msg_id": str(uuid.uuid4()),
            "utc_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "msg_type": "creation",
            "msg_content": "victim/dialogmanager/request"
        },
        "data": {
            "uuid": "Chatbot",
            "ugv_id": str(uuid.uuid4()),
            "context": context,
        }
    }

    json_msg = json.dumps(new_msg)
    cc_client.cc_client.publish("victim/dialogmanager/request", json_msg, retain=True)
    print("Context sent:", context)
    cc_client.cc_client.loop_start()

    while True:
        time.sleep(1)

if __name__ == "__main__":

    cc_client = Mqtt_client()

    situationType = ["ImminentCollapse","FireClosingBy","NoImmediateDanger"]

    send_context(cc_client)