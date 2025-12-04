import json
from typing import Dict, List, Any
import requests
import time

class AssessmentAgent:
    """
    LLM-powered agent responsible for analyzing victim responses during Phase 1 (initial assessment).
    
    Extracts critical information about:
    - Injuries and physical condition
    - Breathing status
    - Mobility (can walk, stuck/trapped)
    - Immediate danger
    - Consciousness level
    - People in surroundings
    """
    
    def __init__(self, model_name: str, assessment_prompt_path: str, ollama_base_url: str = "http://localhost:11434"):
        """
        Initialize the Assessment Agent with Ollama model.
        
        Args:
            model_name: Name of the model in Ollama (e.g., "gemma3:12b")
            assessment_prompt_path: Path to the assessment prompt file
            ollama_base_url: Base URL for Ollama API (default: http://localhost:11434)
        """
        self.model_name = model_name
        self.ollama_url = f"{ollama_base_url}/api/generate"
        
        with open(assessment_prompt_path, 'r') as f:
            self.assessment_prompt = f.read()
            
        # Initialize with "unknown" instead of empty strings
        self.assessment = {
            "injuries": "unknown",
            "people_in_surroundings": "unknown",
            "can_walk": "unknown",
            "stuck_trapped": "unknown",
            "breathing": "unknown",
            "consciousness": "Conscious",  # Default assumption
            "immediate_danger": "unknown",
        }
        
        # Track which categories have been explicitly assessed
        self.assessed_categories = set()
        
        self.assessment_priority = [
            "injuries",               # 1. Most critical
            "breathing",              # 2. Critical
            "immediate_danger",       # 3. Critical
            "stuck_trapped",          # 4. Important
            "can_walk",               # 5. Important
            "people_in_surroundings", # 6. Important
        ]
    
    def update_gps_location(self, latitude: float, longitude: float, description: str = ""):
        """Update the location from the robot's GPS system"""
        self.assessment["Location"] = f"Latitude {latitude}, Longitude {longitude} ({description})"
    
    def analyze_victim_response(self, robot_question: str, victim_response: str) -> Dict[str, str]:
        """
        Use LLM to analyze victim response and extract assessment updates
        
        Args:
            robot_question: The robot's question that preceded the victim's response
            victim_response: The victim's response text
            
        Returns:
            Dictionary of updates to the assessment form (validated and cleaned)
        """
        prompt = self._build_assessment_prompt(robot_question, victim_response)
        
        try:
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,  # Lower temperature for consistency
                    "top_p": 0.9,
                    "num_predict": 512
                }
            }
            
            start_time = time.time()
            response = requests.post(self.ollama_url, json=payload, timeout=180)  # Added timeout
            
            if response.status_code == 200:
                response_data = response.json()
                response_text = response_data.get("response", "").strip()
                elapsed = time.time() - start_time
                print(f"[LLM] AssessmentAgent latency: {elapsed:.2f}s")
                
                # Extract and validate JSON
                updates = self._extract_json(response_text)
                validated_updates = self._validate_updates(updates)

                print("This is the validated updates: ",validated_updates)
                
                return validated_updates
            else:
                print(f"[ERROR] AssessmentAgent: Ollama API returned {response.status_code}")
                print(f"Response: {response.text}")
                return {}
                
        except requests.exceptions.Timeout:
            print(f"[ERROR] AssessmentAgent: Request timed out after 60s")
            return False
        except requests.exceptions.ConnectionError:
            print(f"[ERROR] AssessmentAgent: Could not connect to Ollama at {self.ollama_url}")
            return False
        except Exception as e:
            print(f"[ERROR] AssessmentAgent: Unexpected error - {type(e).__name__}: {e}")
            return False
    
    def _extract_json(self, text: str) -> dict:
        """
        Extract JSON from text that might contain markdown or other formatting
        
        Args:
            text: Raw text response from LLM
            
        Returns:
            Parsed JSON dictionary or empty dict if parsing fails
        """
        # Remove markdown code blocks if present
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            parts = text.split("```")
            if len(parts) >= 2:
                text = parts[1]
        
        text = text.strip()
        
        # Try direct parsing
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Try to find JSON object in the text
        json_start = text.find('{')
        json_end = text.rfind('}') + 1
        
        if json_start >= 0 and json_end > json_start:
            json_str = text[json_start:json_end]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                print(f"[WARNING] Failed to parse JSON: {e}")
                print(f"Attempted to parse: {json_str[:200] if len(json_str) > 200 else json_str}")
        
        print("[WARNING] No valid JSON found in response")
        return {}
    
    def _validate_updates(self, updates: dict) -> dict:
        """
        Validate and clean the updates dictionary.
        Remove invalid entries like empty strings, "unknown", or fields not in template.
        
        Args:
            updates: Raw updates from LLM
            
        Returns:
            Validated and cleaned updates dictionary
        """
        valid_updates = {}
        
        for field, value in updates.items():
            # Skip if field is not in our assessment template
            if field not in self.assessment:
                print(f"[WARNING] Ignoring unknown field: {field}")
                continue
            
            # Skip if value is invalid
            if not value or value == "" or value.strip() == "" or value.lower() == "unknown":
                print(f"[WARNING] Skipping invalid value for '{field}': '{value}'")
                continue
            
            # Skip if trying to update with the same value
            current_value = self.assessment[field]
            if current_value == value:
                print(f"[INFO] Field '{field}' already has value '{value}', skipping")
                continue
            
            # Valid update
            valid_updates[field] = value.strip()
        
        return valid_updates
    
    def _build_assessment_prompt(self, robot_question: str, victim_response: str) -> str:
        """
        Build prompt for the assessment LLM
        
        Args:
            robot_question: The robot's question that preceded the victim's response
            victim_response: The victim's response
            
        Returns:
            Complete assessment prompt
        """
        prompt = f"""{self.assessment_prompt}

Robot Question: "{robot_question}"
Victim Response: "{victim_response}"

Extract assessment information from the victim's response above.
Return ONLY a JSON object with the fields you can extract.
CRITICAL: Do NOT include any field if the value is empty string ("") or "unknown".
If no information can be extracted, return: {{}}
"""
        return prompt
    
    def update_assessment(self, updates: Dict[str, str]):
        """
        Update the assessment form with new information
        
        Args:
            updates: Dictionary of validated updates to the assessment form
        """
        for key, value in updates.items():
            if key not in self.assessment:
                continue
            
            # Get current value
            current_value = self.assessment[key]
            
            # Update from "unknown" to known value
            if current_value == "unknown":
                self.assessment[key] = value
                self.assessed_categories.add(key)
                print(f"[ASSESSMENT UPDATE] {key}: unknown → {value}")
            
            # Update existing value (append if it's additional info)
            elif value != current_value:
                # For injuries, we might want to append new injuries
                if key == "injuries" and current_value.startswith("yes"):
                    # Check if this is genuinely new information
                    if not self._is_duplicate_info(current_value, value):
                        self.assessment[key] = f"{current_value}; {value.replace('yes - ', '')}"
                        print(f"[ASSESSMENT UPDATE] {key}: Added new injury info")
                else:
                    # For other fields, replace if we have better/new information
                    self.assessment[key] = value
                    self.assessed_categories.add(key)
                    print(f"[ASSESSMENT UPDATE] {key}: {current_value} → {value}")
            
            # Mark as assessed
            self.assessed_categories.add(key)
        
        # Automatic "can_walk" inference if victim is stuck/trapped
        if "stuck_trapped" in updates:
            stuck_status = updates["stuck_trapped"].lower()
            if "yes" in stuck_status and self.assessment["can_walk"] == "unknown":
                self.assessment["can_walk"] = "No - victim is stuck/trapped"
                self.assessed_categories.add("can_walk")
                print(f"[ASSESSMENT UPDATE] can_walk: Automatically set to 'No' (victim is trapped)")
    
    def _is_duplicate_info(self, existing: str, new: str) -> bool:
        """
        Check if new information is a duplicate of existing information
        
        Args:
            existing: Existing assessment value
            new: New value to check
            
        Returns:
            True if the information is duplicate, False otherwise
        """
        existing_lower = existing.lower()
        new_lower = new.lower()
        
        # Remove common prefixes
        new_lower = new_lower.replace("yes - ", "").replace("no - ", "")
        
        # Check if new info is already in existing
        return new_lower in existing_lower or existing_lower in new_lower

    def get_assessment(self) -> Dict[str, str]:
        """Get the current assessment"""
        return self.assessment.copy()
    
    def get_incomplete_categories(self) -> List[str]:
        """Get a list of categories that still need assessment"""
        return [cat for cat in self.assessment_priority if cat not in self.assessed_categories]
    
    def is_assessment_complete(self) -> bool:
        """Check if assessment is complete (all priority fields assessed)"""
        for field in self.assessment_priority:
            if field not in self.assessed_categories:
                return False
        return True
        
    def get_next_priority_field(self) -> str:
        """
        Get the next field that should be assessed based on priority order
        
        Returns:
            Name of the next field to assess, or empty string if all are complete
        """
        for field in self.assessment_priority:
            if field not in self.assessed_categories:
                return field
        return ""
    
    def get_assessment_status(self) -> Dict[str, Any]:
        """
        Get comprehensive assessment status including next priority field
        
        Returns:
            Dictionary with assessment status information
        """
        next_field = self.get_next_priority_field()
        completed_fields = len(self.assessed_categories)
        total_fields = len(self.assessment_priority)
        
        return {
            "next_priority_field": next_field,
            "completed_fields": completed_fields,
            "total_fields": total_fields,
            "assessment_complete": self.is_assessment_complete(),
            "incomplete_categories": self.get_incomplete_categories(),
            "progress_percentage": (completed_fields / total_fields) * 100 if total_fields > 0 else 0
        }
        
    def can_victim_walk(self) -> bool:
        """Check if the victim can walk based on mobility assessment"""
        if "can_walk" not in self.assessed_categories:
            return False
        
        can_walk_value = self.assessment["can_walk"].lower()
        return "yes" in can_walk_value or "can walk" in can_walk_value
    
    def is_victim_stuck(self) -> bool:
        """Check if the victim is stuck or trapped"""
        if "stuck_trapped" not in self.assessed_categories:
            return False
        
        stuck_value = self.assessment["stuck_trapped"].lower()
        return "yes" in stuck_value or "stuck" in stuck_value or "trapped" in stuck_value
    
    # ===== Enhanced Helper Methods for Critical Status Checks =====
    
    def has_critical_injuries(self) -> bool:
        """
        Check if victim has critical injuries requiring immediate attention
        
        Returns:
            True if any serious injuries are reported
        """
        if "injuries" not in self.assessed_categories:
            return False
        
        injuries = self.assessment.get("injuries", "unknown").lower()
        
        if injuries in ["unknown", "no injuries", "none", ""]:
            return False
        
        critical_keywords = [
            "bleeding", "blood", "fracture", "broken", "head injury", 
            "chest pain", "severe", "unconscious", "trapped", "crushed",
            "hemorrhage", "laceration", "compound"
        ]
        
        return any(keyword in injuries for keyword in critical_keywords)
    
    def has_breathing_issues(self) -> bool:
        """
        Check if victim is having difficulty breathing
        
        Returns:
            True if breathing problems are indicated
        """
        if "breathing" not in self.assessed_categories:
            return False
        
        breathing = self.assessment.get("breathing", "unknown").lower()
        
        problem_indicators = [
            "difficult", "labored", "struggling", "gasping", 
            "shallow", "rapid", "not breathing", "trouble",
            "wheezing", "choking", "coughing blood"
        ]
        
        return any(indicator in breathing for indicator in problem_indicators)
    
    def is_in_immediate_danger(self) -> bool:
        """
        Check if victim is in immediate environmental danger
        
        Returns:
            True if dangerous situation is reported
        """
        if "danger" not in self.assessed_categories:
            return False
        
        danger = self.assessment.get("danger", "unknown").lower()
        
        if danger in ["unknown", "no", "safe", "none", ""]:
            return False
        
        danger_keywords = [
            "fire", "smoke", "gas", "unstable", "collapse", "flood", 
            "electrical", "chemical", "debris falling", "structural"
        ]
        
        return "yes" in danger or any(keyword in danger for keyword in danger_keywords)
    
    def is_consciousness_concerning(self) -> bool:
        """
        Check if victim's level of consciousness is concerning
        
        Returns:
            True if consciousness level indicates potential problems
        """
        if "consciousness" not in self.assessed_categories:
            return False
        
        consciousness = self.assessment.get("consciousness", "unknown").lower()
        
        concerning_states = [
            "unconscious", "unresponsive", "confused", "disoriented",
            "drowsy", "fading", "losing consciousness", "semi-conscious",
            "dazed", "altered", "incoherent"
        ]
        
        return any(state in consciousness for state in concerning_states)
    
    def needs_immediate_evacuation(self) -> bool:
        """
        Determine if victim needs urgent evacuation based on all assessment factors
        
        Returns:
            True if urgent evacuation is recommended
        """
        # Critical injuries OR breathing issues OR immediate danger OR unconscious = urgent evacuation
        return (
            self.has_critical_injuries() or 
            self.has_breathing_issues() or 
            self.is_in_immediate_danger() or
            self.is_consciousness_concerning()
        )
    
    def get_assessment_summary(self) -> str:
        """
        Generate a human-readable summary of the current assessment
        
        Returns:
            Multi-line string summarizing key assessment findings
        """
        summary_lines = []
        summary_lines.append("=== Assessment Summary ===")
        
        # Injuries
        if "injuries" in self.assessed_categories:
            injuries = self.assessment.get("injuries", "unknown")
            injury_status = "⚠️ CRITICAL" if self.has_critical_injuries() else "✓ Noted"
            summary_lines.append(f"Injuries: {injury_status} - {injuries}")
        else:
            summary_lines.append("Injuries: Not yet assessed")
        
        # Breathing
        if "breathing" in self.assessed_categories:
            breathing = self.assessment.get("breathing", "unknown")
            breathing_status = "⚠️ CONCERNING" if self.has_breathing_issues() else "✓ Normal"
            summary_lines.append(f"Breathing: {breathing_status} - {breathing}")
        else:
            summary_lines.append("Breathing: Not yet assessed")
        
        # Danger
        if "danger" in self.assessed_categories:
            danger = self.assessment.get("danger", "unknown")
            danger_status = "⚠️ IMMEDIATE DANGER" if self.is_in_immediate_danger() else "✓ Safe"
            summary_lines.append(f"Environment: {danger_status} - {danger}")
        else:
            summary_lines.append("Environment: Not yet assessed")
        
        # Mobility
        if "can_walk" in self.assessed_categories:
            can_walk = self.assessment.get("can_walk", "unknown")
            mobility_status = "✓ Mobile" if self.can_victim_walk() else "⚠️ Cannot walk"
            summary_lines.append(f"Mobility: {mobility_status} - {can_walk}")
        else:
            summary_lines.append("Mobility: Not yet assessed")
        
        # Stuck/Trapped
        if "stuck_trapped" in self.assessed_categories:
            stuck = self.assessment.get("stuck_trapped", "unknown")
            stuck_status = "⚠️ TRAPPED" if self.is_victim_stuck() else "✓ Free"
            summary_lines.append(f"Physical Status: {stuck_status} - {stuck}")
        else:
            summary_lines.append("Physical Status: Not yet assessed")
        
        # Consciousness
        if "consciousness" in self.assessed_categories:
            consciousness = self.assessment.get("consciousness", "unknown")
            consciousness_status = "⚠️ ALTERED" if self.is_consciousness_concerning() else "✓ Alert"
            summary_lines.append(f"Consciousness: {consciousness_status} - {consciousness}")
        else:
            summary_lines.append("Consciousness: Not yet assessed")
        
        # Overall recommendation
        summary_lines.append("")
        if self.needs_immediate_evacuation():
            summary_lines.append("🚨 RECOMMENDATION: IMMEDIATE EVACUATION REQUIRED")
        elif self.is_assessment_complete():
            summary_lines.append("✓ RECOMMENDATION: Assessment complete, proceed to triage")
        else:
            summary_lines.append("→ RECOMMENDATION: Continue assessment")
        
        # Progress
        status = self.get_assessment_status()
        summary_lines.append(f"Progress: {status['completed_fields']}/{status['total_fields']} fields ({status['progress_percentage']:.0f}%)")
        
        return "\n".join(summary_lines)