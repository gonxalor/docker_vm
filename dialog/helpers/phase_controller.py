"""
Phase Controller - Central Coordinator for Multi-Phase Rescue Operations

This controller implements the continuous action decision-making architecture where
the Action Agent evaluates the situation after EVERY conversational turn and makes
real-time decisions about evacuation, phase transitions, and emergency escalation.

Architecture:
- Phase 1: Initial Assessment (injuries, breathing, mobility, danger)
- Phase 2: Comfort & Special Needs (medications, allergies, chronic conditions)
- Continuous: Action Agent operates throughout both phases

Decision Points:
- After each victim response → Assessment update → Action evaluation → Decision
- Can evacuate mid-phase, abort early, escalate priority, or transition phases
"""

from typing import Dict, Optional, List, TYPE_CHECKING
import time
import json
import uuid
import os
from datetime import datetime, timezone
from dataclasses import dataclass

if TYPE_CHECKING:
    from helpers.mqtt_manager import MQTTManager

from typing import Dict, Optional, List, Tuple
import time
import paho.mqtt.client as mqtt
import asyncio
from queue import Queue
from agents.assessment_agent import AssessmentAgent
from agents.dialog_agent import DialogueAgent
from agents.comfort_agent import ComfortAgent
from agents.comfort_assessment_agent import ComfortAssessmentAgent
from agents.triage_agent import TriageAgent
from agents.action_agent import ActionAgent
from agents.victim_agent import VictimAgent

#BROKER = "mqtt01.carma"
BROKER = os.getenv('MQTT_BROKER', 'mosquitto')
PORT = int(os.getenv('MQTT_PORT', 1883))
USERNAME = os.getenv('USERNAME', 'inesc')
PASSWORD = os.getenv('PASSWORD', 'inesc')

class ActionDecision:
    """
    Structured representation of an Action Agent decision
    """
    def __init__(self, raw_decision: Dict):
        self.raw = raw_decision
        self.primary_action = raw_decision.get("primary_action", "continue_conversation")
        self.alert_command_center = raw_decision.get("alert_command_center", False)
        self.urgency_level = raw_decision.get("urgency_level", "routine")
        self.reasoning = raw_decision.get("reasoning", "")
        self.next_phase = raw_decision.get("next_phase", None)
        self.specialized_equipment = raw_decision.get("specialized_equipment_needed", [])
        
    def should_continue_phase(self) -> bool:
        """Check if should continue current phase"""
        return self.primary_action == "continue_conversation"
    
    def should_transition_phase_2(self) -> bool:
        """Check if should transition to Phase 2"""
        return self.primary_action == "transition_to_phase_2"
    
    def should_evacuate(self) -> bool:
        """Check if should evacuate immediately"""
        return self.primary_action == "evacuate_immediately"
    
    def should_abort(self) -> bool:
        """Check if should abort and alert command center"""
        return self.primary_action == "abort_and_alert"
    
    def should_complete(self) -> bool:
        """Check if interaction should complete"""
        return self.primary_action == "complete"
    
    def is_emergency(self) -> bool:
        """Check if this is an emergency situation"""
        return self.urgency_level in ["critical", "emergency"]


class PhaseController:
    """
    Central coordinator for multi-phase rescue operations with continuous action decision-making.
    
    This controller orchestrates the interaction between all agents and implements the
    turn-by-turn action evaluation architecture specified in the system design.
    """
    
    def __init__(
        self,
        assessment_agent: AssessmentAgent,
        dialog_agent: DialogueAgent,
        comfort_agent: ComfortAgent,
        comfort_assessment_agent: ComfortAssessmentAgent,
        triage_agent: TriageAgent,
        action_agent: ActionAgent,
        report_queue,
        loop,
        event,
        victim_agent: Optional[VictimAgent] = None,
        mqtt_manager: Optional['MQTTManager'] = None,
        verbose: bool = True,
        local: bool = True,
    ):
        """
        Initialize Phase Controller with all required agents.
        
        Args:
            assessment_agent: Phase 1 assessment extraction agent
            dialog_agent: Phase 1 dialogue generation agent
            comfort_agent: Phase 2 comfort dialogue agent
            comfort_assessment_agent: Phase 2 special needs extraction agent
            triage_agent: Medical priority assignment agent
            action_agent: Continuous decision-making agent
            victim_agent: Optional victim simulation agent for testing
            mqtt_manager: Optional MQTT manager for command center communication
            verbose: Whether to print detailed progress information
        """
        self.assessment_agent = assessment_agent
        self.dialog_agent = dialog_agent
        self.comfort_agent = comfort_agent
        self.comfort_assessment_agent = comfort_assessment_agent
        self.triage_agent = triage_agent
        self.action_agent = action_agent
        self.victim_agent = victim_agent
        self.mqtt_manager = mqtt_manager
        self.verbose = verbose
        self.local = local
        self.report_queue = report_queue
        self.loop = loop
        self.event = event
        
        # State tracking
        self.current_phase = None  # 1, 2, or None
        self.conversation_history = []
        self.action_decisions = []  # Audit trail of all decisions
        self.turn_count = 0
        self.phase_1_turns = 0
        self.phase_2_turns = 0
        
        # Timing data for performance analysis
        self.timing_data = {
            'dialogue_agent': [],
            'assessment_agent': [],
            'comfort_agent': [],
            'comfort_assessment_agent': [],
            'action_agent': [],
            'victim_agent': []
        }

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
        self.victim_id = ""


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
                #message = data["message"]
                #print(f"VICTIM: {message}")

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

    def set_victim_agent(self, victim_agent):
        """Set or update the victim agent for testing scenarios"""
        self.victim_agent = victim_agent
        if self.verbose:
            print(f"✓ Victim agent configured for testing mode")
    
    def set_situation_context(self, context: str):
        """Set the disaster situation context for all agents"""
        if hasattr(self.dialog_agent, 'set_situation_context'):
            self.dialog_agent.set_situation_context(context)
        if hasattr(self.dialog_agent, 'situation_context'):
            self.dialog_agent.situation_context = context
        if hasattr(self.comfort_agent, 'set_situation_context'):
            self.comfort_agent.set_situation_context(context)
        if self.verbose:
            print(f"ℹ️  Situation context set: {context}")
        
    def determine_entry_point(self, prior_assessment: Optional[Dict] = None) -> int:
        """
        Determine which phase to start based on available prior assessment data.
        
        Args:
            prior_assessment: Optional prior Phase 1 assessment data
            
        Returns:
            1 for Phase 1 start, 2 for Phase 2 start
        """
        if prior_assessment and self._is_assessment_sufficient(prior_assessment):
            if self.verbose:
                print("\n🔄 Prior assessment detected - Starting at Phase 2 (Comfort)")
            return 2
        else:
            if self.verbose:
                print("\n🔄 No prior assessment - Starting at Phase 1 (Initial Assessment)")
            return 1
    
    def _is_assessment_sufficient(self, assessment: Dict) -> bool:
        """Check if prior assessment has sufficient information to skip Phase 1"""
        critical_fields = ["injuries", "breathing", "can_walk", "immediate_danger", "consciousness"]
        for field in critical_fields:
            if assessment.get(field, "unknown") == "unknown":
                return False
        return True
    
    def execute_full_workflow(
        self,
        max_phase_1_turns: int = 15,
        max_phase_2_turns: int = 15,
        prior_assessment: Optional[Dict] = None,
        situation_context: str = ""
    ) -> Dict:
        """
        Execute complete rescue workflow with continuous action decision-making.
        
        Args:
            max_phase_1_turns: Maximum turns for Phase 1
            max_phase_2_turns: Maximum turns for Phase 2
            prior_assessment: Optional prior assessment to resume from Phase 2
            situation_context: Description of disaster situation
            
        Returns:
            Dictionary with complete results including assessments, triage, and action log
        """
        if self.verbose:
            print("\n" + "="*80)
            print("🚁 RESCUE ROBOT WORKFLOW - CONTINUOUS ACTION DECISION ARCHITECTURE")
            print("="*80)
        
        # Set situation context
        if situation_context:
            self.dialog_agent.set_situation_context(situation_context)
        
        # Determine entry point
        entry_phase = self.determine_entry_point(prior_assessment)
        
        # If resuming from Phase 2, load prior assessment
        if entry_phase == 2 and prior_assessment:
            self.assessment_agent.assessment = prior_assessment.copy()
        
        results = {
            "entry_phase": entry_phase,
            "phase_1_executed": False,
            "phase_2_executed": False,
            "final_assessment": {},
            "comfort_assessment": {},
            "triage_priority": "",
            "action_decisions": [],
            "conversation_history": [],
            "timing_data": {},
            "exit_reason": ""
        }

        self.victim_id = self.wait_for_victim()
        
        try:
            # Execute Phase 1 if starting fresh
            if entry_phase == 1:
                phase_1_result = self.execute_phase_1(max_phase_1_turns)
                if phase_1_result == 'LLM FAIL':
                    return None,None
                
                results["phase_1_executed"] = True
                results["final_assessment"] = phase_1_result["assessment"]
                results["exit_reason"] = phase_1_result["exit_reason"]
                
                # Check if we should continue to Phase 2
                if phase_1_result["next_phase"] == 2:
                    phase_2_result = self.execute_phase_2(max_phase_2_turns)
                    results["phase_2_executed"] = True
                    results["comfort_assessment"] = phase_2_result["comfort_assessment"]
                    results["exit_reason"] = phase_2_result["exit_reason"]
            
            # Execute Phase 2 if resuming
            elif entry_phase == 2:
                phase_2_result = self.execute_phase_2(max_phase_2_turns)
                results["phase_2_executed"] = True
                results["comfort_assessment"] = phase_2_result["comfort_assessment"]
                results["exit_reason"] = phase_2_result["exit_reason"]
            
            # Perform final triage
            results["triage_priority"] = self._perform_final_triage()
            
            # Compile final results
            results["action_decisions"] = self.action_decisions
            results["conversation_history"] = self.conversation_history
            results["timing_data"] = self.timing_data
            # Legacy/expected keys for tests: provide both phase-specific and final assessment keys
            results["phase_1_assessment"] = self.assessment_agent.get_assessment() if self.phase_1_turns > 0 else {}
            results["phase_2_assessment"] = self.comfort_assessment_agent.get_assessment() if self.phase_2_turns > 0 else {}
            results["final_assessment"] = self.assessment_agent.get_assessment()
            results["phase_1_turns"] = self.phase_1_turns
            results["phase_2_turns"] = self.phase_2_turns
            results["total_turns"] = self.turn_count

            # Generate comprehensive report
            results["rescue_report"] = self.generate_rescue_report()
            
            if self.verbose:
                self._print_final_summary(results)
            
            return results,self.victim_id
            
        except Exception as e:
            print(f"\n❌ ERROR in workflow execution: {e}")
            import traceback
            traceback.print_exc()
            results["exit_reason"] = f"ERROR: {str(e)}"
            return results,self.victim_id
        
    def _robot_speak(self,question):
        #if self.local:
        #    self.audio_manager.text_to_speech(question)
        #else:

        
        json_msg = {
            "header":{
                    "sender": "dialogManager",
                    "msg_id": str(uuid.uuid4()),
                    "utc_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "msg_type": "UGV's message",
                    "msg_content": "victim/text2speech2text/tts"},
            "data":{
                "message": question,
                "victim_id": self.victim_id,
            }
        }  

        json_msg["data"]["last_message"] = False
        json_msg = json.dumps(json_msg)

        self.dialog_client.publish("victim/text2speech2text/tts",str(json_msg))   
    
    def execute_phase_1(self, max_turns: int = 15) -> Dict:
        """
        Execute Phase 1: Initial Assessment with continuous action decision-making.
        
        After each victim response:
        1. Update assessment
        2. Evaluate action decision
        3. Handle decision (continue, evacuate, abort, transition)
        
        Args:
            max_turns: Maximum conversation turns for Phase 1
            
        Returns:
            Dictionary with assessment, exit reason, and next phase recommendation
        """
        self.current_phase = 1
        
        if self.verbose:
            print("\n" + "="*80)
            print("📋 PHASE 1: INITIAL ASSESSMENT")
            print("="*80)
            print("Goal: Extract critical safety and injury information")
            print("Decision Point: After EVERY turn - Action Agent evaluates next move")
            print("="*80 + "\n")
        
        # Generate initial greeting
        start_time = time.time()
        robot_question = self.dialog_agent.get_initial_response()
        elapsed = time.time() - start_time
        self.timing_data['dialogue_agent'].append({
            'turn': 0,
            'duration': elapsed,
            'phase': 1
        })
        
        if self.verbose:
            print(f"🤖 Robot: {robot_question}")
            print(f"⏱️  Dialogue Agent: {elapsed:.2f}s\n")
        
        self._add_to_conversation_log(1, 0, "robot", robot_question, elapsed)
        
        # Main assessment loop with action decision points
        while self.phase_1_turns < max_turns:
            self.phase_1_turns += 1
            self.turn_count += 1

            self._robot_speak(robot_question)

            if self.verbose:
                print(f"\n{'─'*80}")
                print(f"🔄 PHASE 1 - TURN {self.phase_1_turns}")
                print(f"{'─'*80}")
            
            # Get victim response
            victim_response = self._get_victim_response(robot_question)
            if not victim_response:
                if self.verbose:
                    print("⚠️  No response from victim - ending Phase 1")
                return {
                    "assessment": self.assessment_agent.get_assessment(),
                    "exit_reason": "no_victim_response",
                    "next_phase": 2  # Default to Phase 2 if no response
                }
            
            # Update assessment
            assessment_updates = self._update_assessment(robot_question, victim_response)
            
            if assessment_updates == False:
                return "LLM FAIL"
            
            if self.loop is not None:
                self.loop.call_soon_threadsafe(
                    asyncio.create_task, self.report_queue.put(assessment_updates)
                )

            # CRITICAL: Action Agent Decision Point
            action_decision = self._evaluate_action_decision()

            if action_decision == None:
                self.change_to_backup_system(victim_response)
                return "LLM FAIL"
            
            # Send command center alert if requested
            if action_decision.alert_command_center:
                self._alert_command_center(action_decision.raw)
            
            # Handle action decision
            decision_handler_result = self._handle_phase_1_action_decision(action_decision)
            
            if decision_handler_result["should_exit"]:
                return {
                    "assessment": self.assessment_agent.get_assessment(),
                    "exit_reason": decision_handler_result["exit_reason"],
                    "next_phase": decision_handler_result.get("next_phase", None)
                }
            
            # Continue conversation - generate next question
            robot_question = self._generate_next_phase_1_question()

            if robot_question == None:
                self.change_to_backup_system(victim_response)
                return "LLM FAIL"
            
            
            if not robot_question:  # Assessment complete
                if self.verbose:
                    print("\n✅ Phase 1 Assessment Complete")
                
                # Final action decision for phase completion
                final_decision = self._evaluate_action_decision()
                final_handler_result = self._handle_phase_1_action_decision(final_decision)
                
                return {
                    "assessment": self.assessment_agent.get_assessment(),
                    "exit_reason": final_handler_result["exit_reason"],
                    "next_phase": final_handler_result.get("next_phase", 2)
                }
        
        # Max turns reached
        if self.verbose:
            print(f"\n⚠️  Phase 1 max turns ({max_turns}) reached")
        
        return {
            "assessment": self.assessment_agent.get_assessment(),
            "exit_reason": "max_turns_reached",
            "next_phase": 2  # Default to Phase 2
        }
    
    def execute_phase_2(self, max_turns: int = 15) -> Dict:
        """
        Execute Phase 2: Comfort & Special Needs with continuous action decision-making.
        
        After each victim response:
        1. Update comfort assessment
        2. Evaluate action decision (can escalate priority, detect deterioration, abort early)
        3. Handle decision
        
        Args:
            max_turns: Maximum conversation turns for Phase 2
            
        Returns:
            Dictionary with comfort assessment and exit reason
        """
        self.current_phase = 2
        
        if self.verbose:
            print("\n" + "="*80)
            print("💬 PHASE 2: COMFORT & SPECIAL NEEDS")
            print("="*80)
            print("Goal: Provide emotional support and gather detailed medical information")
            print("Decision Point: After EVERY turn - Action Agent monitors for critical needs")
            print("="*80 + "\n")
        
        # Generate initial comfort message
        start_time = time.time()
        robot_message = self.comfort_agent.get_initial_message()
        elapsed = time.time() - start_time
        self.timing_data['comfort_agent'].append({
            'turn': 0,
            'duration': elapsed,
            'phase': 2
        })
        
        if self.verbose:
            print(f"🤖 Robot: {robot_message}")
            print(f"⏱️  Comfort Agent: {elapsed:.2f}s\n")
        
        self._add_to_conversation_log(2, 0, "robot", robot_message, elapsed)
        
        # Main comfort loop with action decision points
        while self.phase_2_turns < max_turns:
            self.phase_2_turns += 1
            self.turn_count += 1

            self._robot_speak(robot_message)
            
            if self.verbose:
                print(f"\n{'─'*80}")
                print(f"🔄 PHASE 2 - TURN {self.phase_2_turns}")
                print(f"{'─'*80}")
            
            # Get victim response
            victim_response = self._get_victim_response(robot_message)
            if not victim_response:
                if self.verbose:
                    print("⚠️  No response from victim - ending Phase 2")
                return {
                    "comfort_assessment": self.comfort_assessment_agent.get_assessment(),
                    "exit_reason": "no_victim_response"
                }
            
            # Update comfort assessment
            comfort_updates = self._update_comfort_assessment(robot_message, victim_response)
            
            # CRITICAL: Action Agent Decision Point (with Phase 1 + Phase 2 data)
            action_decision = self._evaluate_action_decision()
            
            # Send command center alert if requested
            if action_decision.alert_command_center:
                self._alert_command_center(action_decision.raw)
            
            # Handle action decision
            decision_handler_result = self._handle_phase_2_action_decision(action_decision)
            
            if decision_handler_result["should_exit"]:
                return {
                    "comfort_assessment": self.comfort_assessment_agent.get_assessment(),
                    "exit_reason": decision_handler_result["exit_reason"]
                }
            
            # Continue conversation - generate next comfort message
            robot_message = self._generate_next_phase_2_message()
            
            if not robot_message:  # Comfort assessment complete
                if self.verbose:
                    print("\n✅ Phase 2 Comfort Assessment Complete")
                
                return {
                    "comfort_assessment": self.comfort_assessment_agent.get_assessment(),
                    "exit_reason": "phase_2_complete"
                }
        
        # Max turns reached
        if self.verbose:
            print(f"\n⚠️  Phase 2 max turns ({max_turns}) reached")
        
        return {
            "comfort_assessment": self.comfort_assessment_agent.get_assessment(),
            "exit_reason": "max_turns_reached"
        }
    
    # ===== Internal Helper Methods =====

    def wait_for_victim(self):
        print("Waiting for victim...")
        data = self.stt_queue.get()
        print("Victim Found -> ", data["victim_id"])
        return data["victim_id"]
    
    def _get_victim_response(self, robot_question: str) -> str:
        """Get victim response (from VictimAgent or real interaction)"""
        start_time = time.time()
        max_retries = 3
        if self.victim_agent:
            # Testing mode - use VictimAgent
            victim_response = self.victim_agent.generate_response(robot_question)
        else:
            for attempt in range(max_retries):
                print(f"\n--- Listening Attempt {attempt + 1}/{max_retries} ---")
                #if self.local:
                    #victim_response = self.audio_manager.speech_to_text(max_duration=12)
                #else:
                try:
                    data = self.stt_queue.get(timeout=20)
                    victim_response = data["message"]
                except:
                    victim_response = False
                if victim_response:
                    break
                else:
                    if attempt < max_retries - 1:
                        retry_message = self.dialog_agent.get_no_response_message()
                        #if self.local:
                            #self.audio_manager.text_to_speech(retry_message)
                        #else:
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
                            
            # Production mode - would get from audio/text input
            # For now, return empty to signal need for implementation
                
        
        elapsed = time.time() - start_time
        
        if self.victim_agent:
            self.timing_data['victim_agent'].append({
                'turn': self.turn_count,
                'duration': elapsed,
                'phase': self.current_phase
            })
        
        if self.verbose and victim_response:
            print(f"👤 Victim: {victim_response}")
            if self.victim_agent:
                print(f"⏱️  Victim Agent: {elapsed:.2f}s")
        
        if victim_response and self.current_phase is not None:
            self._add_to_conversation_log(
                self.current_phase,
                self.phase_1_turns if self.current_phase == 1 else self.phase_2_turns,
                "victim",
                victim_response,
                elapsed
            )
            
            # Add to dialog agent history
            if self.current_phase == 1:
                self.dialog_agent.add_to_history("victim", victim_response)
            else:
                self.comfort_agent.add_to_history("victim", victim_response)
        
        return victim_response
    
    def _update_assessment(self, robot_question: str, victim_response: str) -> Dict:
        """Update Phase 1 assessment based on victim response"""
        start_time = time.time()
        
        updates = self.assessment_agent.analyze_victim_response(robot_question, victim_response)
        
        if updates == False:
            self.change_to_backup_system(victim_response)
            return False
        
        elif updates:
            self.assessment_agent.update_assessment(updates)
            if self.verbose:
                print(f"✅ Assessment updated: {list(updates.keys())}")
        
        elapsed = time.time() - start_time
        self.timing_data['assessment_agent'].append({
            'turn': self.turn_count,
            'duration': elapsed,
            'phase': 1
        })
        
        if self.verbose:
            print(f"⏱️  Assessment Agent: {elapsed:.2f}s")
        
        return updates
    
    def _update_comfort_assessment(self, robot_message: str, victim_response: str) -> Dict:
        """Update Phase 2 comfort assessment based on victim response"""
        start_time = time.time()
        
        updates = self.comfort_assessment_agent.analyze_victim_response(robot_message, victim_response)
        if updates:
            self.comfort_assessment_agent.update_assessment(updates)
            if self.verbose:
                print(f"✅ Comfort assessment updated: {list(updates.keys())}")
        
        elapsed = time.time() - start_time
        self.timing_data['comfort_assessment_agent'].append({
            'turn': self.turn_count,
            'duration': elapsed,
            'phase': 2
        })
        
        if self.verbose:
            print(f"⏱️  Comfort Assessment Agent: {elapsed:.2f}s")
        
        return updates
    
    def _evaluate_action_decision(self) -> ActionDecision:
        """
        Evaluate what action should be taken based on current state.
        This is called after EVERY turn in both phases.
        """
        start_time = time.time()
        
        # Build comprehensive prompt with all context
        from helpers.action_decision_builder import build_action_decision_prompt
        
        # Safety check - should never be called with current_phase as None
        if self.current_phase is None:
            raise ValueError("_evaluate_action_decision called but current_phase is None")
        
        print("Taking action")
        
        prompt = build_action_decision_prompt(
            phase=self.current_phase,
            assessment=self.assessment_agent.get_assessment(),
            comfort_assessment=self.comfort_assessment_agent.get_assessment() if self.current_phase == 2 else None,
            conversation_history=self.conversation_history[-6:],  # Last 6 exchanges (3 turns)
            turn_number=self.turn_count,
            phase_turn_number=self.phase_1_turns if self.current_phase == 1 else self.phase_2_turns,
            situation_context=getattr(self.dialog_agent, 'situation_context', '')
        )
        
        # Get decision from Action Agent
        raw_decision = self.action_agent.decide_next_action(prompt)
        if raw_decision == False:
            return None
        
        decision = ActionDecision(raw_decision)
        
        elapsed = time.time() - start_time
        self.timing_data['action_agent'].append({
            'turn': self.turn_count,
            'duration': elapsed,
            'phase': self.current_phase
        })
        
        # Log decision for audit trail
        self.action_decisions.append({
            'turn': self.turn_count,
            'phase': self.current_phase,
            'decision': decision.raw,
            'timing': elapsed
        })
        
        if self.verbose:
            print(f"\n🎯 ACTION DECISION:")
            print(f"   • Action: {decision.primary_action}")
            print(f"   • Alert CC: {decision.alert_command_center}")
            print(f"   • Urgency: {decision.urgency_level}")
            print(f"   • Reasoning: {decision.reasoning}")
            if decision.specialized_equipment:
                print(f"   • Equipment Needed: {', '.join(decision.specialized_equipment)}")
            print(f"⏱️  Action Agent: {elapsed:.2f}s")
        
        return decision
    
    def _handle_phase_1_action_decision(self, decision: ActionDecision) -> Dict:
        """
        Handle action decision during Phase 1.
        
        Returns:
            Dict with should_exit (bool), exit_reason (str), and optional next_phase (int)
        """
        # Emergency abort - ONLY for active immediate danger when victim is immobile
        # Examples: fire spreading NOW, ceiling collapsing NOW, smoke filling room NOW
        # NOT for: unstable furniture, cracks in walls, settled debris
        if decision.should_abort():
            assessment = self.assessment_agent.get_assessment()
            immediate_danger = assessment.get('immediate_danger', 'unknown')
            
            # Check if this is truly ACTIVE immediate danger requiring robot to leave
            is_active_danger = any(keyword in str(immediate_danger).lower() for keyword in [
                'fire', 'burning', 'collapsing', 'collapse now', 'smoke filling',
                'gas leak', 'flooding', 'rising water', 'electrical', 'sparks'
            ])
            
            if not is_active_danger and 'unstable' in str(immediate_danger).lower():
                # Unstable structure but not actively collapsing - override abort to Phase 2
                if self.verbose:
                    print("\n⚠️  ABORT OVERRIDDEN: Potential danger detected but not active/immediate")
                    print(f"   Danger: {immediate_danger}")
                    print("   → Robot can safely remain to gather medical information")
                    print("   → Transitioning to Phase 2 instead of aborting")
                
                return {
                    "should_exit": True,
                    "exit_reason": "transition_to_phase_2",
                    "next_phase": 2
                }
            
            # True active danger - abort
            if self.verbose:
                print("\n🚨 ABORTING Phase 1: " + decision.reasoning)
                print("   Robot will leave area and alert command center for specialized rescue")
            return {
                "should_exit": True,
                "exit_reason": "abort_and_alert",
                "next_phase": None
            }
        
        # Immediate evacuation - ambulatory victim, safe to move
        if decision.should_evacuate():
            if self.verbose:
                print("\n🏃 EVACUATING IMMEDIATELY: " + decision.reasoning)
                print("   Skipping Phase 2 - guiding victim to safe zone")
            return {
                "should_exit": True,
                "exit_reason": "immediate_evacuation",
                "next_phase": None
            }
        
        # Transition to Phase 2 - SAFETY GUARD
        if decision.should_transition_phase_2():
            # Deterministic safety check: block early transitions unless we have critical info
            assessment = self.assessment_agent.get_assessment()
            
            # Allow transition only if:
            # 1. Immediate danger is detected (must abort or evacuate - should not reach here)
            # 2. Victim mobility is confirmed (can_walk OR stuck_trapped is known)
            # 3. We've gathered enough turns (minimum 3 turns to establish baseline)
            
            mobility_known = (
                assessment.get('can_walk', 'unknown') != 'unknown' or
                assessment.get('stuck_trapped', 'unknown') != 'unknown'
            )
            
            min_turns_met = self.phase_1_turns >= 3
            
            if not mobility_known or not min_turns_met:
                # Override transition - continue Phase 1 assessment
                if self.verbose:
                    print("\n⚠️  TRANSITION BLOCKED: Insufficient safety data")
                    print(f"   • Mobility known: {mobility_known}")
                    print(f"   • Min turns (3): {min_turns_met} (current: {self.phase_1_turns})")
                    print("   • Continuing Phase 1 assessment to gather critical safety information")
                
                return {
                    "should_exit": False,
                    "exit_reason": None
                }
            
            # Safety check passed - allow transition
            if self.verbose:
                print("\n➡️  TRANSITIONING TO PHASE 2: " + decision.reasoning)
                print("   ✓ Safety criteria met:")
                print(f"     • Mobility status: known")
                print(f"     • Assessment turns: {self.phase_1_turns}")
            return {
                "should_exit": True,
                "exit_reason": "transition_to_phase_2",
                "next_phase": 2
            }
        
        # Continue Phase 1 conversation
        if decision.should_continue_phase():
            return {
                "should_exit": False,
                "exit_reason": None
            }
        
        # Unknown action - default to continue
        if self.verbose:
            print(f"\n⚠️  Unknown action: {decision.primary_action} - defaulting to continue")
        return {
            "should_exit": False,
            "exit_reason": None
        }
    
    def _handle_phase_2_action_decision(self, decision: ActionDecision) -> Dict:
        """
        Handle action decision during Phase 2.
        
        Returns:
            Dict with should_exit (bool) and exit_reason (str)
        """
        # Emergency situation detected
        if decision.should_abort() or decision.is_emergency():
            if self.verbose:
                print("\n🚨 EMERGENCY DETECTED: " + decision.reasoning)
                print(f"   Urgency Level: {decision.urgency_level}")
            return {
                "should_exit": True,
                "exit_reason": "emergency_detected"
            }
        
        # Immediate evacuation (for ambulatory victims with sufficient info)
        if decision.should_evacuate():
            if self.verbose:
                print("\n🏃 EVACUATING NOW: " + decision.reasoning)
                print("   Sufficient medical information gathered - proceeding to safe zone")
            return {
                "should_exit": True,
                "exit_reason": "evacuation_ready"
            }
        
        # Phase 2 complete
        if decision.should_complete():
            if self.verbose:
                print("\n✅ PHASE 2 COMPLETE: " + decision.reasoning)
            return {
                "should_exit": True,
                "exit_reason": "phase_2_complete"
            }
        
        # Continue Phase 2 conversation
        if decision.should_continue_phase():
            # Check for priority escalation even if continuing
            if decision.alert_command_center and decision.urgency_level in ["priority", "critical"]:
                if self.verbose:
                    print(f"\n⚠️  PRIORITY ESCALATION: {decision.reasoning}")
                    print(f"   Continuing Phase 2 but alerting command center ({decision.urgency_level})")
            return {
                "should_exit": False,
                "exit_reason": None
            }
        
        # Unknown action - default to continue
        if self.verbose:
            print(f"\n⚠️  Unknown action: {decision.primary_action} - defaulting to continue")
        return {
            "should_exit": False,
            "exit_reason": None
        }
    
    def _generate_next_phase_1_question(self) -> str:
        """Generate next Phase 1 assessment question"""
        assessment = self.assessment_agent.get_assessment()
        is_complete = self.assessment_agent.is_assessment_complete()
        next_field = self.assessment_agent.get_next_priority_field()
        
        if not next_field or is_complete:
            return ""  # Assessment complete
        
        start_time = time.time()
        robot_question = self.dialog_agent.get_next_response(
            assessment,
            is_complete,
            next_field
        )
        elapsed = time.time() - start_time
        
        if robot_question == False:
            return None


        self.timing_data['dialogue_agent'].append({
            'turn': self.phase_1_turns,
            'duration': elapsed,
            'phase': 1
        })
        
        if self.verbose:
            print(f"\n🤖 Robot: {robot_question}")
            print(f"⏱️  Dialogue Agent: {elapsed:.2f}s")
        
        self._add_to_conversation_log(1, self.phase_1_turns, "robot", robot_question, elapsed)
        
        return robot_question
    
    def _generate_next_phase_2_message(self) -> str:
        """Generate next Phase 2 comfort message"""
        is_complete = self.comfort_assessment_agent.is_assessment_complete()
        next_field = self.comfort_assessment_agent.get_next_priority_field()
        
        if not next_field or is_complete:
            return ""  # Comfort assessment complete
        
        start_time = time.time()
        robot_message = self.comfort_agent.get_next_response(
            self.comfort_assessment_agent.get_assessment(),
            is_complete,
            next_field
        )
        elapsed = time.time() - start_time
        
        self.timing_data['comfort_agent'].append({
            'turn': self.phase_2_turns,
            'duration': elapsed,
            'phase': 2
        })
        
        if self.verbose:
            print(f"\n🤖 Robot: {robot_message}")
            print(f"⏱️  Comfort Agent: {elapsed:.2f}s")
        
        self._add_to_conversation_log(2, self.phase_2_turns, "robot", robot_message, elapsed)
        
        return robot_message
    
    def _perform_final_triage(self) -> str:
        """Perform final triage assessment"""
        if self.verbose:
            print("\n" + "="*80)
            print("🏥 FINAL TRIAGE ASSESSMENT")
            print("="*80)
        
        start_time = time.time()
        
        phase_1 = self.assessment_agent.get_assessment()
        phase_2 = self.comfort_assessment_agent.get_assessment()
        
        priority = self.triage_agent.assign_triage_priority(phase_1, phase_2)
        
        elapsed = time.time() - start_time
        
        if self.verbose:
            print(f"Priority: {priority}")
            print(f"⏱️  Triage Agent: {elapsed:.2f}s")
        
        return priority
    
    def _add_to_conversation_log(self, phase: int, turn: int, role: str, content: str, timing: float):
        """Add entry to conversation log"""
        self.conversation_history.append({
            'phase': phase,
            'turn': turn,
            'type': role,
            'content': content,
            'timing': timing
        })
    
    def _print_final_summary(self, results: Dict):
        """Print final summary of workflow execution"""
        print("\n" + "="*80)
        print("📊 WORKFLOW SUMMARY")
        print("="*80)
        print(f"Entry Phase: {results['entry_phase']}")
        print(f"Phase 1 Executed: {results['phase_1_executed']}")
        print(f"Phase 2 Executed: {results['phase_2_executed']}")
        print(f"Total Turns: {self.turn_count}")
        print(f"Phase 1 Turns: {self.phase_1_turns}")
        print(f"Phase 2 Turns: {self.phase_2_turns}")
        print(f"Action Decisions Made: {len(self.action_decisions)}")
        print(f"Triage Priority: {results['triage_priority']}")
        print(f"Exit Reason: {results['exit_reason']}")
        print("="*80 + "\n")
    
    def handle_action_decision(self, decision: Dict) -> str:
        """
        Process an action decision and return the next step.
        
        Args:
            decision: Action decision dictionary from ActionAgent
            
        Returns:
            String indicating next step: "CONTINUE_PHASE", "TRANSITION_PHASE_2", 
            "EVACUATE_NOW", "ABORT_AND_ALERT", "COMPLETE"
        """
        action = decision.get("primary_action", "continue_conversation")
        
        # Log the decision
        self.action_decisions.append({
            'turn': self.turn_count,
            'phase': self.current_phase,
            'decision': decision
        })
        
        # Map actions to next steps
        action_map = {
            "continue_conversation": "CONTINUE_PHASE",
            "transition_to_phase_2": "TRANSITION_PHASE_2",
            "evacuate_immediately": "EVACUATE_NOW",
            "abort_and_alert": "ABORT_AND_ALERT",
            "maintain_and_monitor": "MAINTAIN_MONITOR",
            "emergency_alert": "EMERGENCY_ALERT",
            "complete": "COMPLETE"
        }
        
        next_step = action_map.get(action, "CONTINUE_PHASE")
        
        # Handle command center alerts
        if decision.get("alert_command_center", False):
            self._alert_command_center(decision)
        
        return next_step
    
    def _alert_command_center(self, decision: Dict):
        """
        Send alert to command center via MQTT (if available) or console output.
        
        Args:
            decision: Action decision with alert details
        """
        import time
        
        urgency = decision.get("urgency_level", "routine")
        reasoning = decision.get("reasoning", "No reason provided")
        equipment = decision.get("specialized_equipment_needed", [])
        
        # Build alert message
        alert_data = {
            "timestamp": time.time(),
            "urgency_level": urgency,
            "reason": reasoning,
            "specialized_equipment_needed": equipment,
            "phase": self.current_phase,
            "turn": self.turn_count,
            "assessment": self.assessment_agent.get_assessment() if self.current_phase == 1 else {},
            "comfort_assessment": self.comfort_assessment_agent.get_assessment() if self.current_phase == 2 else {}
        }
        
        # Send via MQTT if available
        mqtt_sent = False
        if hasattr(self, 'mqtt_manager') and self.mqtt_manager is not None:
            try:
                mqtt_sent = self.mqtt_manager.publish(
                    topic="rescue/robot/command_center/alert",
                    data=alert_data,
                    qos=1  # At least once delivery
                )
            except Exception as e:
                if self.verbose:
                    print(f"⚠️  MQTT send failed: {e}")
        
        # Console output for debugging/development
        if self.verbose:
            urgency_colors = {
                "routine": "\033[94m",  # Blue
                "priority": "\033[93m",  # Yellow
                "critical": "\033[91m",  # Red
                "emergency": "\033[91m\033[1m"  # Bold Red
            }
            color = urgency_colors.get(urgency, "\033[94m")
            reset = "\033[0m"
            
            status_icon = "✅" if mqtt_sent else "📡"
            print(f"\n{color}{status_icon} COMMAND CENTER ALERT{reset}")
            print(f"{color}Urgency: {urgency.upper()}{reset}")
            print(f"Reason: {reasoning}")
            if equipment:
                print(f"Equipment Needed: {', '.join(equipment)}")
            if mqtt_sent:
                print(f"Status: Sent via MQTT")
            elif hasattr(self, 'mqtt_manager'):
                print(f"Status: Queued for MQTT (offline)")
    
    def generate_rescue_report(self) -> str:
        """
        Generate a comprehensive rescue report after workflow completion.
        
        Returns:
            Formatted markdown report string
        """
        report_lines = []
        report_lines.append("# RESCUE ROBOT MISSION REPORT")
        report_lines.append("")
        report_lines.append("=" * 80)
        report_lines.append("")
        
        # Mission Overview
        report_lines.append("## MISSION OVERVIEW")
        report_lines.append("")
        report_lines.append(f"- **Total Turns**: {self.turn_count}")
        report_lines.append(f"- **Phase 1 Turns**: {self.phase_1_turns}")
        report_lines.append(f"- **Phase 2 Turns**: {self.phase_2_turns}")
        report_lines.append(f"- **Action Decisions Made**: {len(self.action_decisions)}")
        report_lines.append("")
        
        # Victim Assessment
        report_lines.append("## VICTIM ASSESSMENT (Phase 1)")
        report_lines.append("")
        assessment = self.assessment_agent.get_assessment()
        for key, value in assessment.items():
            report_lines.append(f"- **{key.replace('_', ' ').title()}**: {value}")
        report_lines.append("")
        
        # Comfort Assessment (if Phase 2 executed)
        if self.phase_2_turns > 0:
            report_lines.append("## COMFORT & SPECIAL NEEDS (Phase 2)")
            report_lines.append("")
            comfort = self.comfort_assessment_agent.get_assessment()
            for key, value in comfort.items():
                report_lines.append(f"- **{key.replace('_', ' ').title()}**: {value}")
            report_lines.append("")
        
        # Triage Priority
        triage_priority = self.assessment_agent.assessment.get("priority", "Not assessed")
        report_lines.append("## TRIAGE PRIORITY")
        report_lines.append("")
        report_lines.append(f"**{triage_priority}**")
        report_lines.append("")
        
        # Action Decisions Summary
        report_lines.append("## ACTION DECISIONS LOG")
        report_lines.append("")
        for i, decision_entry in enumerate(self.action_decisions, 1):
            decision = decision_entry['decision']
            report_lines.append(f"### Decision {i} (Turn {decision_entry['turn']}, Phase {decision_entry['phase']})")
            report_lines.append(f"- **Action**: {decision['primary_action']}")
            report_lines.append(f"- **Alert Command Center**: {decision['alert_command_center']}")
            report_lines.append(f"- **Urgency Level**: {decision['urgency_level']}")
            report_lines.append(f"- **Reasoning**: {decision['reasoning']}")
            if decision.get('specialized_equipment_needed'):
                report_lines.append(f"- **Equipment Needed**: {', '.join(decision['specialized_equipment_needed'])}")
            report_lines.append("")
        
        # Timing Analysis
        report_lines.append("## PERFORMANCE METRICS")
        report_lines.append("")
        for agent, timings in self.timing_data.items():
            if timings:
                total_time = sum(t['duration'] for t in timings)
                avg_time = total_time / len(timings)
                report_lines.append(f"### {agent}")
                report_lines.append(f"- Total calls: {len(timings)}")
                report_lines.append(f"- Total time: {total_time:.2f}s")
                report_lines.append(f"- Average time: {avg_time:.2f}s")
                report_lines.append("")
        
        # Conversation Summary
        report_lines.append("## CONVERSATION TRANSCRIPT")
        report_lines.append("")
        for i, entry in enumerate(self.conversation_history, 1):
            role = "🤖 Robot" if entry['type'] == 'robot' else "👤 Victim"
            report_lines.append(f"**{i}. {role}** (Phase {entry['phase']}, Turn {entry['turn']}, {entry['timing']:.2f}s):")
            report_lines.append(f"> {entry['content']}")
            report_lines.append("")
        
        report_lines.append("=" * 80)
        report_lines.append("END OF REPORT")
        
        return "\n".join(report_lines)


