#!/usr/bin/env python3
"""
Rescue Robot System - Main Entry Point
Offline rescue communication system with Whisper STT and pyttsx3 TTS
"""
import sys
import traceback
import asyncio
import time
from typing import Tuple
import paho.mqtt.client as mqtt
from queue import Queue
import json
import uuid
import os
from datetime import datetime, timezone

from helpers.config_manager import ConfigManager, setup_argument_parser, get_situation_context_from_user
from helpers.rescue_robot_system import RescueRobotSystem
from helpers.backup_dialog import BackupInteraction

#BROKER = "mqtt01.carma"  # replace with broker IP
BROKER = os.getenv('MQTT_BROKER', 'mosquitto')
#BROKER = os.getenv('MQTT_BROKER', 'localhost')
PORT = int(os.getenv('MQTT_PORT', 1883))
USERNAME = os.getenv('USERNAME', 'inesc')
PASSWORD = os.getenv('PASSWORD', 'inesc')

class MqttClient():        

    def __init__(self):
        self.cc_queue = Queue()
        print("Why no print?")
        self.dm_client = mqtt.Client()
        self.dm_client.will_set("victim/dialogmanager/lwt", "offline")
        self.dm_client.on_connect = self.on_connect
        self.dm_client.on_message = self.on_cc_message
        self.dm_client.username_pw_set(USERNAME,PASSWORD)
        self.dm_client.connect(BROKER, PORT)
        self.dm_client.loop_start()

        self.victim_id = None

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("✅ Connected to broker")
            # Listen for text to speak
            self.dm_client.subscribe("victim/dialogmanager/request")
            self.dm_client.subscribe("victim/controlcenter/lwt")
            self.dm_client.publish("victim/dialogmanager/lwt", "online")    
        else:
            print("❌ Bad connection. Returned code=", rc)    


    def on_cc_message(self,client, userdata, msg):
        if msg.payload.decode() != "":
            msg_topic = msg.topic
            if msg_topic == "victim/controlcenter/lwt":
                print(f"Control Center status update: {msg.payload.decode()}")    
            else:
                configs = json.loads(msg.payload.decode())   
                self.cc_queue.put(configs)
                self.dm_client.publish("victim/dialogmanager/request", payload="", qos=1, retain=True)


def print_system_requirements():
    """Print system requirements and dependencies"""
    print("\nSYSTEM REQUIREMENTS:")
    print("  • Python 3.8+")
    print("  • Ollama running locally (port 11434)")
    print("  • Microphone and speakers/headphones")
    print("  • Required packages: whisper, pyttsx3, pyaudio, speech_recognition")
    print("\nDEPENDENCIES CHECK:")
    
    # Check critical dependencies
    dependencies = {
        "whisper": "OpenAI Whisper for speech recognition",
        "pyttsx3": "Text-to-speech engine", 
        "pyaudio": "Audio recording interface",
        "speech_recognition": "Backup speech recognition",
        "requests": "HTTP client for Ollama API",
        "numpy": "Audio data processing"
    }
    
    missing_deps = []
    for dep, description in dependencies.items():
        try:
            __import__(dep)
            print(f"{dep:<20} - {description}")
        except ImportError:
            print(f"ERROR: {dep:<20} - {description} (MISSING)")
            missing_deps.append(dep)
    
    if missing_deps:
        print(f"\nMissing dependencies: {', '.join(missing_deps)}")
        print("Install with: pip install " + " ".join(missing_deps))
        return False
    
    return True


def check_ollama_connection(base_url: str) -> bool:
    """
    Check if Ollama is running and accessible
    
    Args:
        base_url: Ollama base URL
        
    Returns:
        True if Ollama is accessible
    """
    try:
        import requests
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        if response.status_code == 200:
            print(f"Ollama connection - {base_url}")
            return True
        else:
            print(f"ERROR: Ollama connection failed - Status {response.status_code}")
            return False
    except Exception as e:
        print(f"ERROR: Ollama connection failed - {e}")
        print(f"Make sure Ollama is running: ollama serve")
        return False


def validate_system_readiness(config: ConfigManager) -> bool:
    """
    Validate that the system is ready to run
    
    Args:
        config: System configuration
        
    Returns:
        True if system is ready
    """
    ready = True
    
    # Check dependencies
    if not print_system_requirements():
        ready = False
    
    # Check Ollama connection
    if not check_ollama_connection(config.model_config.ollama_base_url):
        ready = False
    
    # Validate configuration
    if not config.validate_configuration():
        ready = False
    
    if ready:
        print("\nSystem validation passed - Ready to start!")
    else:
        print("\nERROR: System validation failed - Please fix issues above")

    return ready


def run_interactive_setup(config: ConfigManager) -> Tuple[bool, str]:
    """
    Run interactive setup process
    
    Args:
        config: System configuration
        
    Returns:
        Tuple of (success: bool, situation_context: str)
    """
    print("\nINTERACTIVE SETUP:")
    
    # Ask if user wants to test audio systems
    if not config.conversation_config.test_audio_on_start:
        test_audio = input("Would you like to test audio systems before starting? (y/n): ").lower().startswith('y')
        config.conversation_config.test_audio_on_start = test_audio
    
    # Get situation context from user
    situation_context = get_situation_context_from_user()
    
    return True, situation_context


def handle_system_error(error: Exception, context: str = ""):
    """
    Handle system errors gracefully
    
    Args:
        error: The exception that occurred
        context: Additional context about when the error occurred
    """
    print(f"\nSYSTEM ERROR {context}:")
    print(f"   {type(error).__name__}: {error}")
    
    # Print detailed traceback in debug mode
    if "--debug" in sys.argv:
        print("\nDEBUG TRACEBACK:")
        traceback.print_exc()
    else:
        print("\nRun with --debug flag for detailed error information")

    print("\nTROUBLESHOOTING TIPS:")
    print("  • Check that Ollama is running: ollama serve")
    print("  • Verify microphone and speaker connections")
    print("  • Ensure all Python dependencies are installed")
    print("  • Check firewall settings for Ollama port 11434")

def send_status_report(mqtt_client,msg,robotname):
    topic = f"dialogmanager/ugv/{robotname}"
    data = msg
    data["victim_id"] = mqtt_client.victim_id
    status_report_msg = {
        "header": {
            "sender": "dialogManager",
            "msg_id": str(uuid.uuid4()),
            "utc_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "msg_type": "Creation",
            "msg_content": topic},
        "data": data
        }

    json_msg = json.dumps(status_report_msg)

    result = mqtt_client.dm_client.publish(topic, json_msg, retain=True)
    result.wait_for_publish()   # ✅ wait until actually sent
   
async def run_backup_interaction(mqtt_client,report_queue,language,robotname):
    print("--------------------------entering backup interaction-----------------------------")
    try:
        robot_system = BackupInteraction(robotname,language=language)
        mqtt_client.victim_id = await robot_system.interaction_tree(queue=report_queue)
        send_status_report(mqtt_client, robot_system.victim_situation,robotname)
        await asyncio.sleep(0.5)
        robot_system.dialog_client.disconnect()
    except Exception as e:
        handle_system_error(e, "during backup interaction")


async def run_rescue_robot(mqtt_client, args, context,report_queue,loop,cancel_event):
    print("-----------------------entering normal interaction---------------------------------")

    config = ConfigManager.from_args(args)
    if not validate_system_readiness(config):
        print("\nERROR: Cannot start system due to validation failures")
        await report_queue.put({"info": "fail_at_start"})
        cancel_event.set()
        return 1

    print(f"\nINITIALIZING RESCUE ROBOT SYSTEM...")
    robot_system = RescueRobotSystem(config, local=False,report_queue=report_queue,loop=loop,event=cancel_event,use_phase_controller=True)
    print("DEBUGGING set cpntext")
    robot_system.set_situation_context(context)

    if config.conversation_config.test_audio_on_start:
        robot_system.test_audio_systems()

    print(f"\nSTARTING RESCUE OPERATION...")
    print(f"Location: {config.location_config.description}")
    print(f"Empathy Level: {config.audio_config.empathy_level}")
    print(f"Max Turns: {config.conversation_config.max_turns}")
    print("\n" + "="*50)

    try:
        # Runs blocking conversation in background thread
        final_assessment, mqtt_client.victim_id = await asyncio.to_thread(
            robot_system.run_conversation,
            max_turns=config.conversation_config.max_turns
        )

        if cancel_event.is_set():
            print("🛑 Rescue robot cancellation detected.")
            return

        print("✅ Rescue robot shutting down gracefully.")

    except asyncio.CancelledError:
        print("Rescue robot coroutine cancelled externally.")
        raise

    print("\n" + "="*50)
    print("PERFORMING TRIAGE ASSESSMENT...")
    print("="*50)

    triage_priority = await asyncio.to_thread(robot_system.perform_triage_assessment)

    print("\n" + "="*50)
    print("RESCUE OPERATION COMPLETED")
    print("="*50)
    print("\nFINAL ASSESSMENT SUMMARY:")
    send_status_report(mqtt_client, final_assessment,config.conversation_config.robot_name)
    await asyncio.sleep(0.5) 
    print(f"\nTRIAGE PRIORITY: {triage_priority}")
    print("\nSystem shutdown successful")


async def main():
    parser = setup_argument_parser()
    args = parser.parse_args()
    
    mqtt_client = MqttClient()

    context_situation = {
        "ImminentCollapse": "You are inside a building that is in danger of immediate collapse.",
        "FireClosingBy": "There is a fire close by.",
        "NoImmediateDanger": "There is no immediate danger",
    }


    try:
        print("⚙️ Starting Backup and Rescue systems simultaneously...")

        
        #json_object = mqtt_client.cc_queue.get()
        #situation_context = json_object["data"]["context"]
        context = context_situation["ImminentCollapse"]


        print(f"[Dialog Manager] Context received: {context}")
        report_queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        cancel_event = asyncio.Event()

        # Run both tasks *at the same time*
        await asyncio.gather(
            run_rescue_robot(mqtt_client, args, context,report_queue,loop,cancel_event),
            run_backup_interaction(mqtt_client,report_queue,args.language,args.robotname),
        )

        print("\n✅ Both systems completed execution successfully.")

    except KeyboardInterrupt:
        print("\n\nSYSTEM INTERRUPTED BY USER")
        mqtt_client.dm_client.loop_stop()
        mqtt_client.dm_client.disconnect()
        return 130

    except Exception as e:
        handle_system_error(e, "during execution")
        mqtt_client.dm_client.loop_stop()
        mqtt_client.dm_client.disconnect()
        return 1
    

exit_code = asyncio.run(main())
sys.exit(exit_code)

 