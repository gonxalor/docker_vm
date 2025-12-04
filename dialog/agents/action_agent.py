import requests
import time
import json
from typing import Dict, List, Optional

class ActionAgent:
    """
    LLM-powered agent responsible for deciding the robot's next action.
    
    This agent operates continuously throughout the rescue interaction, making
    real-time decisions after every conversational turn about whether to:
    - Continue gathering information
    - Evacuate the victim immediately
    - Transition between phases
    - Abort and alert command center
    - Escalate priority levels
    """

    def __init__(self, model_name: str, ollama_base_url: str = "http://localhost:11434", verbose: bool = True):
        """
        Initialize the Action Agent with Ollama model.
        
        Args:
            model_name: Name of the model in Ollama
            ollama_base_url: Base URL for Ollama API
            verbose: Whether to print detailed logging
        """
        self.model_name = model_name
        self.ollama_url = f"{ollama_base_url}/api/generate"
        self.verbose = verbose

    def decide_next_action(self, prompt: str) -> dict:
        """
        Use LLM to determine the robot's next action based on context and conversation history.

        Args:
            prompt: String containing context and conversation history

        Returns:
            Dictionary with keys:
                - primary_action: Main action to take
                - alert_command_center: True/False
                - urgency_level: routine/priority/critical/emergency
                - reasoning: Brief justification
                - next_phase: Optional phase transition
                - specialized_equipment_needed: List of required equipment
                
                (For backwards compatibility, also includes):
                - send_message_to_cc: Same as alert_command_center
                - action: Human-readable action description
        """
        
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "temperature": 0.1,
            "max_tokens": 200,  # Increased for more detailed output
            "timeout": 180
        }

        try:
            start_time = time.time()
            response = requests.post(self.ollama_url, json=payload, timeout=180)
            response.raise_for_status()
            response_data = response.json()
            llm_output = response_data.get("response", "").strip()
            elapsed = time.time() - start_time
            
            if self.verbose:
                print(f"[LLM] ActionAgent latency: {elapsed:.2f}s")

            # Try to parse JSON from LLM output (robust to markdown fences and extra text)
            parsed = self._parse_action_json(llm_output)
            if parsed is not None:
                # Ensure all required fields are present with defaults
                return self._normalize_action_decision(parsed)
            
            if self.verbose:
                print(f"Warning: Failed to parse JSON from LLM output: {llm_output[:200]}")
            return self._get_default_decision()

        except requests.exceptions.Timeout:
            if self.verbose:
                print(f"Error: ActionAgent request timed out after 180s")
            return False
        except Exception as e:
            ### Send message to backup dialog manager
            if self.verbose:    
                print(f"Error in deciding next action: {e}")
            return False
            #return {"send_message_to_cc": False, "action": "Maintain safety and observe"}

    def _strip_markdown_fences(self, text: str) -> str:
        """
        Remove markdown code fences like ```json ... ``` from the text if present.
        """
        if text.startswith("```"):
            # Remove opening fence with optional language
            first_newline = text.find('\n')
            if first_newline != -1:
                text = text[first_newline+1:]
        if text.endswith("```"):
            text = text[:-3].strip()
        # Also handle cases where model echoes ```json on the same line
        text = text.replace("```json", "").replace("```JSON", "").strip()
        return text

    def _parse_action_json(self, llm_output: str):
        """
        Extract and parse the JSON object from the LLM output.
        Handles plain JSON, fenced code blocks, and surrounding text.
        Returns dict on success, or None on failure.
        """
        if not llm_output:
            return None
        cleaned = self._strip_markdown_fences(llm_output)
        # If still not plain JSON, extract between first '{' and last '}'
        start = cleaned.find('{')
        end = cleaned.rfind('}')
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start:end+1]
        try:
            data = json.loads(cleaned)
        except Exception:
            return None
        # Validate presence of required keys (flexible for both old and new format)
        if isinstance(data, dict) and ("primary_action" in data or "action" in data):
            return data
        return None
    
    def _normalize_action_decision(self, raw_decision: Dict) -> Dict:
        """
        Normalize action decision to ensure all required fields are present.
        Handles both old format (send_message_to_cc, action) and new format.
        """
        normalized = {
            "primary_action": raw_decision.get("primary_action", "continue_conversation"),
            "alert_command_center": raw_decision.get("alert_command_center", False),
            "urgency_level": raw_decision.get("urgency_level", "routine"),
            "reasoning": raw_decision.get("reasoning", ""),
            "next_phase": raw_decision.get("next_phase", None),
            "specialized_equipment_needed": raw_decision.get("specialized_equipment_needed", [])
        }
        
        # Backwards compatibility: also include old format fields
        normalized["send_message_to_cc"] = normalized["alert_command_center"]
        
        # Generate human-readable action description
        action_map = {
            "continue_conversation": "Continue gathering information",
            "transition_to_phase_2": "Transition to Phase 2 (Comfort & Special Needs)",
            "evacuate_immediately": "Guide victim to evacuation immediately",
            "abort_and_alert": "Abort and alert command center for specialized rescue",
            "complete": "Assessment complete - await further instructions",
            "maintain_and_monitor": "Maintain position and monitor victim"
        }
        normalized["action"] = action_map.get(normalized["primary_action"], normalized["primary_action"])
        
        return normalized
    
    def _get_default_decision(self) -> Dict:
        """
        Get safe default decision when LLM fails or times out.
        Defaults to continuing conversation with routine alert.
        """
        return {
            "primary_action": "continue_conversation",
            "alert_command_center": False,
            "urgency_level": "routine",
            "reasoning": "Default action due to decision system error - continuing safely",
            "next_phase": None,
            "specialized_equipment_needed": [],
            "send_message_to_cc": False,  # Backwards compatibility
            "action": "Continue gathering information"  # Backwards compatibility
        }
