"""
Conversation Manager Module
Handles the conversation flow and coordinates between agents and audio
"""
import json
import time
import uuid
from typing import Dict, Optional
from helpers.audio_manager import AudioManager
from agents.assessment_agent import AssessmentAgent
from agents.dialog_agent import DialogueAgent
from agents.action_agent import ActionAgent

import paho.mqtt.client as mqtt
import time
import random
import asyncio
from queue import Queue
from datetime import datetime, timezone


#BROKER = "mqtt01.carma"
BROKER = "localhost"
PORT = 1883
USERNAME = "inesc"
PASSWORD = "inesc"


class ConversationManager:
    """Manages the conversation flow between the robot and victim"""
    
    def __init__(self, 
                 assessment_agent: AssessmentAgent, 
                 dialogue_agent: DialogueAgent, 
                 action_agent: ActionAgent, 
                 audio_manager: Optional[AudioManager], 
                 local: bool, 
                 report_queue, 
                 loop, 
                 event):
        """
        Initialize conversation manager
        
        Args:
            assessment_agent: Agent for assessing victim condition
            dialogue_agent: Agent for managing dialogue
            action_agent: Agent for deciding robot actions
            audio_manager: Manager for audio processing
        """
        self.assessment_agent = assessment_agent
        self.dialogue_agent = dialogue_agent
        self.action_agent = action_agent
        self.audio_manager = audio_manager
        self.local = local
        self.report_queue = report_queue
        self.loop = loop
        self.event = event
        
        # Load Action Agent base prompt from file
        self.action_prompt = ""
        try:
            with open('prompts/action_prompt.txt', 'r',encoding='utf-8') as f:
                self.action_prompt = f.read()
        except FileNotFoundError:
            # Minimal fallback to avoid hardcoding the full prompt here
            self.action_prompt = "You are the decision-making assistant for a rescue robot.\n\nYour output MUST always be a valid JSON object with exactly two fields: send_message_to_cc and action. Do not include any explanation or text outside the JSON.\n\nHere is the context and conversation history:"
        
        if not self.local:
            self.stt_queue = Queue()
            self.dialog_client = mqtt.Client()
            self.dialog_client.will_set("victim/dialogmanager2/lwt", "offline")
            self.dialog_client.on_connect = self.on_connect
            self.dialog_client.on_message = self.on_stt_message
            self.dialog_client.username_pw_set(USERNAME,PASSWORD)
            self.dialog_client.connect(BROKER, PORT)
            self.dialog_client.loop_start()
            self.first_message = True

        self.conversation_history = []
        self.turn_count = 0
        self.victim_id = "001"


    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("✅ Connected to broker")
            self.dialog_client.subscribe("victim/text2speech2text/stt")
            self.dialog_client.subscribe("victim/text2speech2text/lwt")            
            self.dialog_client.publish("victim/dialogmanager2/lwt", "online")
        else:
            print("❌ Bad connection. Returned code=", rc)    


    def on_stt_message(self, client, userdata, msg):
        if msg.payload.decode() != "":
            msg_topic = msg.topic
            if msg_topic == "victim/text2speech2text/lwt":
                print(f"Text2speech2Text status update: {msg.payload.decode()}")        
            else:    
                response = json.loads(msg.payload.decode())
                data = response["data"]
                message = data["message"]
                print(f"VICTIM: {message}")

                self.stt_queue.put(data)

                if self.first_message:
                    self.first_message = False
                    self.dialog_client.publish("victim/text2speech2text/stt", payload="", qos=1, retain=True)

    def change_to_backup_system(self,victim_response):
        if self.loop is not None:
            self.loop.call_soon_threadsafe(
                asyncio.create_task, self.report_queue.put({"info": "fail", "data": victim_response})
        ) 
        self.event.set()

    
    def get_victim_response_with_retry(self, max_retries: int = 3) -> str:
        """
        Get victim response with retry mechanism using offline recognition
        
        Args:
            max_retries: Maximum number of retry attempts
            
        Returns:
            Victim's response text
        """
        for attempt in range(max_retries):
            print(f"\n--- Listening Attempt {attempt + 1}/{max_retries} ---")
            if self.local:
                response = self.audio_manager.speech_to_text(max_duration=12)
            else:
                try:
                    data = self.stt_queue.get(timeout=20)
                    response = data["message"]
                except:
                    response = False
            if response:
                return response
            else:
                if attempt < max_retries - 1:
                    retry_message = self.dialogue_agent.get_no_response_message()
                    if self.local:
                        self.audio_manager.text_to_speech(retry_message)
                    else:
                        json_msg = {
                            "header":{
                                    "sender": "dialogManager",
                                    "msg_id": str(uuid.uuid4()),
                                    "utc_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                    "msg_type": "UGV's message",
                                    "msg_content": "victim/text2speech2text/tts"},
                            "data":{
                                "message": retry_message,
                                "victim_id": self.victim_id,
                                "last_message": False,
                            }
                        }
                        json_msg = json.dumps(json_msg)

                        self.dialog_client.publish("victim/text2speech2text/tts",str(json_msg))
                    time.sleep(1)
        
        return ""
    
    def process_victim_response(self, victim_response: str) -> Dict:
        """
        Process victim's response and update assessment
        
        Args:
            victim_response: The victim's spoken response
            
        Returns:
            Dictionary with processing results
        """
        # Add to conversation history
        self.dialogue_agent.add_to_history("victim", victim_response)
        
        # Analyze and update assessment
        robot_question = self.dialogue_agent.get_last_robot_question()
        updates = self.assessment_agent.analyze_victim_response(robot_question, victim_response)

        if updates == False:
            self.change_to_backup_system(victim_response)
            return False
        
        print(f"Assessment updates: {updates}")
        self.assessment_agent.update_assessment(updates)
        
        # Get current assessment status using the new priority-based system
        assessment_status = self.assessment_agent.get_assessment_status()
        assessment = self.assessment_agent.get_assessment()


        if self.loop is not None:
            self.loop.call_soon_threadsafe(
                asyncio.create_task, self.report_queue.put(assessment)
            )
        
        print(f"Current assessment: {json.dumps(assessment, indent=2)}")
        print(f"Next priority field: {assessment_status['next_priority_field']}")
        print(f"Assessment progress: {assessment_status['completed_fields']}/{assessment_status['total_fields']} ({assessment_status['progress_percentage']:.1f}%)")
        print(f"Assessment complete: {assessment_status['assessment_complete']}")
        print(f"Priority order: {self.assessment_agent.assessment_priority}")
        print(f"Assessed categories: {self.assessment_agent.assessed_categories}")
        
        return {
            "assessment": assessment,
            "assessment_complete": assessment_status['assessment_complete'],
            "next_field": assessment_status['next_priority_field'],
            "updates": updates,
            "assessment_status": assessment_status
        }
    
    def generate_robot_response(self, assessment_info: Dict, victim_response: str = "") -> Dict:
        """
        Generate the next robot response based on assessment and action decision
        
        Args:
            assessment_info: Dictionary containing assessment information
            victim_response: The victim's response that led to this assessment
            
        Returns:
            Dictionary with action decision and robot response
        """
        # First, decide on the robot's action based on assessment and victim response
        action_decision = self.decide_robot_action(assessment_info, victim_response)
        if action_decision == None:
            return None
        print(action_decision)
        
        # Then generate speech based on the decided action
        robot_response = self.dialogue_agent.get_next_response_with_action(
            assessment_info["assessment"],
            assessment_info["assessment_complete"],
            assessment_info["next_field"],
            action_decision
        )

        if not robot_response:
            self.change_to_backup_system(victim_response)
            return None
        
        return {
            "action_decision": action_decision,
            "robot_response": robot_response
        }
    
    def decide_robot_action(self, assessment_info: Dict, victim_response: str) -> Dict:
        """
        Use Action Agent to decide the robot's next action
        
        Args:
            assessment_info: Dictionary containing assessment information
            victim_response: The victim's response
            
        Returns:
            Dictionary with action decision
        """
        # Build prompt for action agent
        action_prompt = self._build_action_prompt(assessment_info, victim_response)
        
        # Get action decision from Action Agent
        action_decision = self.action_agent.decide_next_action(action_prompt)
        if not action_decision:
            self.change_to_backup_system(victim_response)
            return None
        
        print(f"Action Agent Decision: {action_decision}")
        return action_decision
    
    def _build_action_prompt(self, assessment_info: Dict, victim_response: str) -> str:
        """
        Build prompt for the Action Agent
        
        Args:
            assessment_info: Dictionary containing assessment information
            victim_response: The victim's response
            
        Returns:
            Complete prompt for the Action Agent
        """
        assessment = assessment_info["assessment"]
        conversation_history = self.dialogue_agent.get_conversation_history()
        
        # Start from the external prompt file content
        prompt = self.action_prompt + "\n\n"
        
        prompt += "Current Assessment:\n"
        prompt += f"{json.dumps(assessment, indent=2)}\n\n"
        
        prompt += "Conversation History:\n"
        
        for entry in conversation_history:
            if entry["role"] == "victim":
                prompt += f"Victim: {entry['content']}\n"
            else:
                prompt += f"Robot: {entry['content']}\n"
        
        if victim_response:
            prompt += f"\nLatest Victim Response: {victim_response}"
        
        return prompt
    
    def execute_conversation_turn(self) -> bool:
        """
        Execute one turn of the conversation
        
        Returns:
            True if conversation should continue, False if it should end
        """
        self.turn_count += 1
        print(f"\n--- Turn {self.turn_count} ---")
        
        # Get victim response
        victim_response = self.get_victim_response_with_retry()
        # victim_response = input("Victim (type response): ").strip()
        
        if not victim_response:
            print("No response received after multiple attempts")
            final_message = "I'm having trouble hearing you. Help is on the way. Please stay where you are."
            if self.local:
                self.audio_manager.text_to_speech(final_message)
            else:
                json_msg = {
                    "header":{
                            "sender": "dialogManager",
                            "msg_id": str(uuid.uuid4()),
                            "utc_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "msg_type": "UGV's message",
                            "msg_content": "victim/text2speech2text/tts"},
                    "data":{
                        "message": final_message,
                        "victim_id": self.victim_id,
                        "last_message": False,
                    }
                }
                json_msg = json.dumps(json_msg)

                self.dialog_client.publish("victim/text2speech2text/tts",str(json_msg))
            
            return False
        
        # Process the response
        assessment_info = self.process_victim_response(victim_response)
        if not assessment_info:
            return "LLM FAIL"
        
        # Generate and speak robot response with action decision
        response_data = self.generate_robot_response(assessment_info, victim_response)
        if response_data == None:
            return "LLM FAIL"
        next_response = response_data["robot_response"]
        action_decision = response_data["action_decision"]
        
        # Handle control center messaging if needed
        if action_decision.get("send_message_to_cc", False):
            print(f"⚠️  Sending message to control center due to action: {action_decision['action']}")
            # Here you would implement the actual control center messaging logic
        if self.local:
            self.audio_manager.text_to_speech(next_response)
        else:
            json_msg = {
                "header":{
                        "sender": "dialogManager",
                        "msg_id": str(uuid.uuid4()),
                        "utc_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "msg_type": "UGV's message",
                        "msg_content": "victim/text2speech2text/tts"},
                "data":{
                    "message": next_response,
                    "victim_id": self.victim_id,
                }
            }
            if assessment_info["assessment_complete"]:
                json_msg["data"]["last_message"] = True
                json_msg = json.dumps(json_msg)

                self.dialog_client.publish("victim/text2speech2text/tts",str(json_msg))

                print("\n--- FINAL ASSESSMENT ---")
                print(json.dumps(self.assessment_agent.get_assessment(), indent=2))
                print("-------------------------\n")
                return False
            
            elif self.turn_count >= 10 or not assessment_info["next_field"]:
                json_msg["data"]["last_message"] = True
                json_msg = json.dumps(json_msg)

                self.dialog_client.publish("victim/text2speech2text/tts",str(json_msg))
                
                print(f"\n--- CONVERSATION ENDING ---")
                print(f"Reason: {'Max turns reached' if self.turn_count >= 10 else 'No more fields to assess'}")
                print(json.dumps(self.assessment_agent.get_assessment(), indent=2))
                print("-------------------------\n")
                return False 
            
            else:
                json_msg["data"]["last_message"] = False
                json_msg = json.dumps(json_msg)

                self.dialog_client.publish("victim/text2speech2text/tts",str(json_msg))
        
        
        
        return True
    
    def wait_for_victim(self):
        print("Waiting for victim...")
        data = self.stt_queue.get()
        print("Victim Found -> ", data["victim_id"])
        return data["victim_id"]
        
    
    def start_conversation(self):
        """Start the conversation with initial robot response"""
        print("LIVE AUDIO MODE - Robot will speak and listen")

        # Initial robot response
        initial_response = self.dialogue_agent.get_initial_response()

        if self.local:
            self.audio_manager.text_to_speech(initial_response)
        else:
            json_msg = {
                "header":{
                        "sender": "dialogManager",
                        "msg_id": str(uuid.uuid4()),
                        "utc_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "msg_type": "UGV's message",
                        "msg_content": "victim/text2speech2text/tts"},
                "data":{
                    "message": initial_response,
                    "victim_id": self.victim_id,
                    "last_message": False,
                }
            }
            json_msg = json.dumps(json_msg)

            self.dialog_client.publish("victim/text2speech2text/tts",str(json_msg))


    def run_full_conversation(self, max_turns: int = 10):
        """
        Run a complete conversation with the victim
        
        Args:
            max_turns: Maximum number of conversation turns
            
        Returns:
            Final assessment results
        """
        if not self.local: 
            self.victim_id = self.wait_for_victim()
        self.start_conversation()
        
        for turn in range(max_turns):
            should_continue = self.execute_conversation_turn()
            if should_continue == "LLM FAIL":
                return None, None
            if not should_continue:
                break
        
        print("Conversation completed")

        final_assessment = self.assessment_agent.get_assessment()
        if not self.assessment_agent.can_victim_walk():
            if self.assessment_agent.is_victim_stuck():
                final_assessment["mobility"] = "can't walk - victim is stuck"
                final_assessment["robot_action"] = "wait for responder"
            else:
                final_assessment["mobility"] = "can't walk"
                final_assessment["robot_action"] = "wait for responder"

        else:
            final_assessment["mobility"] = "can walk"
            final_assessment["robot_action"] = "guide victim to safety"

        final_assessment.pop("can_walk")
        final_assessment.pop("stuck_trapped")

        return final_assessment,self.victim_id
    
    def get_conversation_summary(self) -> Dict:
        """
        Get a summary of the conversation
        
        Returns:
            Dictionary with conversation summary
        """
        return {
            "total_turns": self.turn_count,
            "final_assessment": self.assessment_agent.get_assessment(),
            "assessment_complete": self.assessment_agent.is_assessment_complete(),
            "conversation_history": self.dialogue_agent.get_conversation_history()
        }