import requests
import time
from typing import Dict, Optional


class TriageAgent:
    """
    LLM-powered agent for assigning triage priority to victims during rescue operations.
    
    This agent analyzes the complete assessment from Phase 1 (AssessmentAgent) and
    Phase 2 (ComfortAssessmentAgent if available) to determine the appropriate triage
    category following standard START (Simple Triage And Rapid Treatment) principles.
    
    Triage Categories:
    - Red (Immediate): Life-threatening injuries requiring immediate intervention
    - Yellow (Delayed): Serious injuries but stable, can wait for treatment
    - Green (Minor): Minor injuries, can walk and wait
    - Black (Deceased/Expectant): Deceased or injuries incompatible with life
    
    Key Features:
    - LLM-based priority assignment using structured prompt
    - Validation of triage output against valid categories
    - Comprehensive error handling with fallback to "Yellow" (safe default)
    - Timeout protection for API calls
    - Assessment completeness checking
    
    Architecture:
    - Uses Ollama LLM (gemma3:12b) with low temperature (0.1) for consistency
    - Timeout: 60s for all API requests
    - Validates output against START triage categories
    """
    
    def __init__(
        self,
        model_name: str,
        triage_prompt_path: str,
        ollama_base_url: str = "http://localhost:11434"
    ):
        """
        Initialize the Triage Agent with Ollama model.
        
        Args:
            model_name: Name of the model in Ollama (e.g., "gemma3:12b")
            triage_prompt_path: Path to the triage prompt file
            ollama_base_url: Base URL for Ollama API (default: localhost:11434)
        """
        self.model_name = model_name
        self.ollama_url = f"{ollama_base_url}/api/generate"
        
        # Load triage prompt
        try:
            with open(triage_prompt_path, 'r') as f:
                self.triage_prompt = f.read()
        except FileNotFoundError:
            print(f"[ERROR] TriageAgent: Prompt file not found at {triage_prompt_path}")
            self.triage_prompt = "Assign triage priority based on assessment."
        
        # Valid triage categories (START protocol)
        self.valid_priorities = ['Red', 'Yellow', 'Green', 'Black']
        self.default_priority = 'Yellow'  # Safe default when errors occur
    
    def assign_triage_priority(
        self,
        assessment: Dict[str, str],
        comfort_assessment: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Assign triage priority based on victim assessment(s)
        
        Args:
            assessment: Complete assessment dictionary from AssessmentAgent
            comfort_assessment: Optional comfort assessment from ComfortAssessmentAgent
            
        Returns:
            Triage priority: "Red", "Yellow", "Green", or "Black"
        """
        # Validate assessment completeness
        if not assessment or not self._is_assessment_sufficient(assessment):
            print("[WARNING] TriageAgent: Insufficient assessment data, using default priority")
            return self.default_priority
        
        # Build prompt with both assessments
        prompt = self._build_triage_prompt(assessment, comfort_assessment)
        
        # Get LLM decision
        priority = self._get_llm_triage_decision(prompt)
        
        # Validate and return
        if priority in self.valid_priorities:
            return priority
        else:
            print(f"[WARNING] TriageAgent: Invalid priority '{priority}', using default")
            return self.default_priority
    
    def _get_llm_triage_decision(self, prompt: str) -> str:
        """
        Get triage decision from LLM with proper error handling
        
        Args:
            prompt: Complete triage prompt
            
        Returns:
            Triage priority string
        """
        try:
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,  # Low temperature for consistent classification
                    "top_p": 0.9,
                    "num_predict": 64  # Short output, just the priority
                }
            }
            
            start_time = time.time()
            response = requests.post(self.ollama_url, json=payload, timeout=180)  # Added timeout
            
            if response.status_code == 200:
                response_data = response.json()
                priority = response_data.get("response", "").strip()
                elapsed = time.time() - start_time
                print(f"[LLM] TriageAgent latency: {elapsed:.2f}s")
                
                # Display triage output for debugging
                print(f"\n[TRIAGE AGENT] LLM Output:")
                print("-" * 50)
                print(priority)
                print("-" * 50)
                
                # Clean response
                priority = self._clean_priority_response(priority)
                
                return priority
            else:
                print(f"[ERROR] TriageAgent: Ollama API returned {response.status_code}")
                print(f"Response: {response.text}")
                return self.default_priority
                
        except requests.exceptions.Timeout:
            print(f"[ERROR] TriageAgent: Request timed out after 60s")
            return self.default_priority
        except requests.exceptions.ConnectionError:
            print(f"[ERROR] TriageAgent: Could not connect to Ollama at {self.ollama_url}")
            return self.default_priority
        except Exception as e:
            print(f"[ERROR] TriageAgent: Unexpected error - {type(e).__name__}: {e}")
            return self.default_priority
    
    def _clean_priority_response(self, response: str) -> str:
        """
        Clean LLM response to extract priority
        
        Args:
            response: Raw LLM response
            
        Returns:
            Cleaned priority string
        """
        # Remove newlines and extra whitespace
        response = response.replace('\n', '').replace('\r', '').strip()
        
        # Extract priority if response contains explanation
        for priority in self.valid_priorities:
            if priority.lower() in response.lower():
                return priority
        
        # If exact match exists, return it
        if response in self.valid_priorities:
            return response
        
        return response  # Return as-is if no match (will be caught by validation)
    
    def _build_triage_prompt(
        self,
        assessment: Dict[str, str],
        comfort_assessment: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Build comprehensive prompt for triage decision
        
        Args:
            assessment: Phase 1 assessment from AssessmentAgent
            comfort_assessment: Optional Phase 2 assessment from ComfortAssessmentAgent
            
        Returns:
            Complete triage prompt
        """
        prompt_parts = []
        
        # Base triage instructions
        prompt_parts.append(self.triage_prompt)
        
        # Phase 1 Assessment (Safety and Injuries)
        prompt_parts.append("\nPHASE 1 ASSESSMENT (Safety & Injuries):")
        for key, value in assessment.items():
            if value and value != "unknown":
                prompt_parts.append(f"- {key}: {value}")
        
        # Phase 2 Assessment (Medical & Special Needs) if available
        if comfort_assessment:
            prompt_parts.append("\nPHASE 2 ASSESSMENT (Medical & Special Needs):")
            for key, value in comfort_assessment.items():
                if value and value != "unknown":
                    prompt_parts.append(f"- {key}: {value}")
        
        return "\n".join(prompt_parts)
    
    def _is_assessment_sufficient(self, assessment: Dict[str, str]) -> bool:
        """
        Check if assessment has minimum required information for triage
        
        Args:
            assessment: Assessment dictionary
            
        Returns:
            True if assessment is sufficient for triage decision
        """
        # Check for at least one critical field
        critical_fields = ["injuries", "breathing", "consciousness", "immediate_danger"]
        
        for field in critical_fields:
            value = assessment.get(field, "").strip()
            if value and value.lower() != "unknown":
                return True
        
        return False
    
    # ===== Helper Methods =====
    
    def get_priority_description(self, priority: str) -> str:
        """
        Get human-readable description of triage priority
        
        Args:
            priority: Triage priority (Red/Yellow/Green/Black)
            
        Returns:
            Description of what the priority means
        """
        descriptions = {
            "Red": "IMMEDIATE - Life-threatening injuries requiring immediate intervention",
            "Yellow": "DELAYED - Serious injuries but stable, can wait for treatment",
            "Green": "MINOR - Minor injuries, can walk and wait",
            "Black": "DECEASED/EXPECTANT - Deceased or injuries incompatible with life"
        }
        
        return descriptions.get(priority, "Unknown priority level")
    
    def is_high_priority(self, priority: str) -> bool:
        """
        Check if priority is high (Red)
        
        Args:
            priority: Triage priority
            
        Returns:
            True if priority is Red (immediate)
        """
        return priority == "Red"
    
    def is_ambulatory(self, priority: str) -> bool:
        """
        Check if victim can walk (Green priority)
        
        Args:
            priority: Triage priority
            
        Returns:
            True if priority is Green (walking wounded)
        """
        return priority == "Green"
