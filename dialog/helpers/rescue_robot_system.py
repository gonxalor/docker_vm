"""
Rescue Robot System - Main System Class
Coordinates all components of the rescue robot system
"""
from typing import Dict, Optional
from helpers.audio_manager import AudioManager
from helpers.conversation_manager import ConversationManager
from helpers.config_manager import ConfigManager
from agents.assessment_agent import AssessmentAgent
from agents.dialog_agent import DialogueAgent
from agents.triage_agent import TriageAgent
from agents.action_agent import ActionAgent
from agents.comfort_agent import ComfortAgent
from agents.comfort_assessment_agent import ComfortAssessmentAgent


class RescueRobotSystem:
    """Main system coordinating between assessment and dialogue agents with offline TTS and STT"""
    
    def __init__(self, config: ConfigManager, local=True,report_queue=None,loop=None,event=None,use_phase_controller=False):
        """
        Initialize the Rescue Robot Communication System.
        
        Args:
            config: ConfigManager instance with system configuration
            local: Whether to use local audio (True) or MQTT (False)
            use_phase_controller: Whether to use new PhaseController architecture (True) or legacy ConversationManager (False)
        """
        self.config = config
        self.local = local
        self.event = event
        self.use_phase_controller = use_phase_controller
        
        # Initialize agents
        model_config = config.get_model_config_dict()
        self.assessment_agent = AssessmentAgent(
            model_config['model_name'],
            model_config['assessment_prompt_path'],
            model_config['ollama_base_url']
        )
        self.dialogue_agent = DialogueAgent(
            model_config['model_name'],
            model_config['dialogue_prompt_path'],
            config.audio_config.empathy_level,
            model_config['ollama_base_url'],
            model_config['language']
        )
        self.triage_agent = TriageAgent(
            model_config['model_name'],
            model_config['triage_prompt_path'],
            model_config['ollama_base_url']
        )
        self.action_agent = ActionAgent(
            model_config['model_name'],
            model_config['ollama_base_url']
        )
        # Initialize comfort agents if using phase controller
        if use_phase_controller:
            self.comfort_agent = ComfortAgent(
                model_config['model_name'],
                model_config.get('comfort_prompt_path', 'prompts/comfort_prompt.txt'),
                model_config['ollama_base_url'],
                model_config['language']
            )
            
            self.comfort_assessment_agent = ComfortAssessmentAgent(
                model_config['model_name'],
                model_config.get('comfort_assessment_prompt_path', 'prompts/comfort_assessment_prompt.txt'),
                model_config['ollama_base_url']
            )
        if local:
            # Initialize audio manager
            audio_config = config.get_audio_config_dict()
            self.audio_manager = AudioManager(**audio_config)
        else:
            self.audio_manager = None

        print(f"Using PhaseController: {self.use_phase_controller}\n")
        
        if use_phase_controller:
            from helpers.phase_controller import PhaseController
            self.phase_controller = PhaseController(
                dialog_agent=self.dialogue_agent,
                assessment_agent=self.assessment_agent,
                comfort_agent=self.comfort_agent,
                comfort_assessment_agent=self.comfort_assessment_agent,
                action_agent=self.action_agent,
                triage_agent=self.triage_agent,
                report_queue=report_queue,
                loop=loop,
                event=event,
                verbose=True, # Enable verbose output for debugging
                local=self.local, 
            )
            self.conversation_manager = None
        else:
            self.conversation_manager = ConversationManager(
                self.assessment_agent,
                self.dialogue_agent,
                self.action_agent,
                self.audio_manager,
                self.local,
                report_queue,
                loop,
                event
            )
            self.phase_controller = None
        
        # Set default location
        #self.update_gps_location(
        #    config.location_config.latitude,
        #    config.location_config.longitude,
        #    config.location_config.description
        #)
    
    def update_gps_location(self, latitude: float, longitude: float, description: str = ""):
        """
        Update the location from the robot's GPS system
        
        Args:
            latitude: GPS latitude coordinate
            longitude: GPS longitude coordinate  
            description: Human-readable location description
        """
        self.assessment_agent.update_gps_location(latitude, longitude, description)
        print(f"Location updated: {description} ({latitude}, {longitude})")
    
    def perform_triage_assessment(self) -> str:
        """
        Perform triage assessment using the current assessment data
        
        Returns:
            Triage priority (Red, Yellow, Green, or Black)
        """
        priority = self.triage_agent.assign_triage_priority(self.assessment_agent.assessment)
        
        # Update the assessment with the triage priority
        self.assessment_agent.assessment["priority"] = priority
        
        print(f"\n=== TRIAGE ASSESSMENT COMPLETE ===")
        print(f"Priority: {priority}")
        print(f"Full Assessment: {self.assessment_agent.assessment}")
        
        return priority
    
    def get_triage_priority(self) -> str:
        """
        Get the current triage priority from the assessment
        
        Returns:
            Current triage priority or empty string if not set
        """
        return self.assessment_agent.assessment.get("priority", "")
    
    def set_situation_context(self, context: str):
        """
        Set the situation context for the dialogue agent
        
        Args:
            context: Description of the disaster situation

        """
        print(f"This is the context that we are going to set: {context}")
        self.dialogue_agent.set_situation_context(context)
        print(f"Situation context set: {context}")
    
    def test_audio_systems(self):
        """Test the audio systems (TTS and STT)"""
        if self.audio_manager:
            self.audio_manager.test_audio_systems()
    
    def run_conversation(self, max_turns: Optional[int] = None, situation_context: str = ""):
        """
        Run a conversation with the victim using offline audio processing
        
        Args:
            max_turns: Maximum number of conversation turns (uses config default if None)
            situation_context: Description of the disaster situation
            
        Returns:
            Final assessment results
        """
        if max_turns is None:
            max_turns = self.config.conversation_config.max_turns
        
        print(f"\n=== STARTING RESCUE DIALOGUE ===")
        print(f"Empathy level: {self.config.audio_config.empathy_level}")
        print(f"Architecture: {'PhaseController (Continuous Decisions)' if self.use_phase_controller else 'ConversationManager (Legacy)'}")
        print(f"Mode: {'Fully offline (Whisper + pyttsx3)' if self.local else 'MQTT'}")
        
        try:
            if self.use_phase_controller:
                # New PhaseController approach with continuous action decisions
                if situation_context:
                    self.phase_controller.set_situation_context(situation_context)
                
                # Run full workflow (Phase 1 → Phase 2 → Triage)
                result,victim_id = self.phase_controller.execute_full_workflow(
                    max_phase_1_turns=max_turns,
                    max_phase_2_turns=max_turns
                )

                # After finishing, check again
                if self.event.is_set():
                    print("🛑 Conversation aborted due to cancel signal.")
                    return None, None
                
                print(f"\nPhase Controller Results:")
                print(f"   • Entry Phase: {result['entry_phase']}")
                print(f"   • Phase 1 Turns: {result.get('phase_1_turns', 0)}")
                print(f"   • Phase 2 Turns: {result.get('phase_2_turns', 0)}")
                print(f"   • Total Turns: {result['total_turns']}")
                print(f"   • Triage Priority: {result.get('triage_priority', 'N/A')}")
                
                # Extract final assessment
                final_assessment = result.get('phase_1_assessment', {})
                if 'phase_2_assessment' in result:
                    final_assessment['comfort_needs'] = result['phase_2_assessment']
                
                # Add triage info
                if 'triage_priority' in result:
                    final_assessment['triage_priority'] = result['triage_priority']
                
                
                return final_assessment, victim_id
            else:
                # Run conversation
                final_assessment, victim_id = self.conversation_manager.run_full_conversation(
                    max_turns
                )

                # After finishing, check again
                if self.event.is_set():
                    print("🛑 Conversation aborted due to cancel signal.")
                    return None, None
                
                self.conversation_manager.dialog_client.disconnect()
                
                # Get conversation summary
                summary = self.conversation_manager.get_conversation_summary()
                
                print(f"\nConversation completed:")
                print(f"   • Total turns: {summary['total_turns']}")
                print(f"   • Assessment complete: {summary['assessment_complete']}")
                
                return final_assessment,victim_id
            
        except Exception as e:
            print(f"ERROR: Conversation error: {e}")
            raise
        finally:
            # Cleanup resources
            self.cleanup()
    
    def get_system_status(self) -> Dict:
        """
        Get current system status
        
        Returns:
            Dictionary with system status information
        """
        status = {
            "audio_config": {
                "empathy_level": self.config.audio_config.empathy_level,
                "whisper_model": self.config.audio_config.whisper_model,
                "tts_configured": hasattr(self.audio_manager, 'tts_engine') if self.audio_manager else False
            },
            "model_config": {
                "model_name": self.config.model_config.model_name,
                "ollama_url": self.config.model_config.ollama_base_url
            }
        }
        
        if self.use_phase_controller and self.phase_controller:
            status["conversation_status"] = {
                "architecture": "PhaseController",
                "current_phase": self.phase_controller.current_phase,
                "total_turns": self.phase_controller.turn_count,
                "phase_1_turns": self.phase_controller.phase_1_turns,
                "phase_2_turns": self.phase_controller.phase_2_turns,
                "assessment_complete": self.assessment_agent.is_assessment_complete()
            }
        elif self.conversation_manager:
            status["conversation_status"] = {
                "architecture": "ConversationManager (Legacy)",
                "turns_completed": self.conversation_manager.turn_count,
                "assessment_complete": self.assessment_agent.is_assessment_complete()
            }
        else:
            status["conversation_status"] = {
                "architecture": "Not initialized",
                "assessment_complete": self.assessment_agent.is_assessment_complete()
            }
        
        return status
    
    def get_current_assessment(self) -> Dict:
        """
        Get current victim assessment
        
        Returns:
            Current assessment data
        """
        return self.assessment_agent.get_assessment()
    
    def cleanup(self):
        """Clean up system resources"""
        try:
            if self.audio_manager:
                self.audio_manager.cleanup()
            print("System cleanup completed")
        except Exception as e:
            print(f"Cleanup warning: {e}")

    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup"""
        self.cleanup()