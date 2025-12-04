"""
ComfortAssessmentAgent - Specialized agent for extracting medical needs and special conditions
during the comfort phase of rescue operations.

This agent analyzes victim responses during Phase 2 (comfort) to extract:
- Emergency medications needed
- Regular medications
- Allergies
- Medical conditions (diabetes, etc.)
- Age/elderly status
- Pregnancy status
- Mobility impairments
- Mental health conditions
"""

import requests
import json
import re


class ComfortAssessmentAgent:
    """
    Agent specialized in extracting and tracking special medical needs
    and conditions during the comfort phase.
    """
    
    def __init__(self, model_name: str, assessment_prompt_path: str, ollama_base_url: str = "http://localhost:11434"):
        """
        Initialize the ComfortAssessmentAgent
        
        Args:
            model_name: Name of the LLM model to use
            assessment_prompt_path: Path to the assessment prompt file
            ollama_base_url: Base URL for Ollama API
        """
        self.model_name = model_name
        self.ollama_base_url = ollama_base_url
        
        # Load assessment prompt
        with open(assessment_prompt_path, 'r') as f:
            self.assessment_prompt = f.read()
        
        # Initialize special needs tracking
        self.special_needs = {
            "emergency_medication": "unknown",
            "regular_medication": "unknown",
            "allergies": "unknown",
            "medical_conditions": "unknown",
            "age": "unknown",
            "elderly": "unknown",
            "pregnant": "unknown",
            "mobility_impairment": "unknown",
            "mental_health_conditions": "unknown"
        }
        
        # Priority order for gathering information
        self.priority_fields = [
            "emergency_medication",      # Highest priority
            "medical_conditions",
            "allergies",
            "regular_medication",
            "age",
            "elderly",
            "mobility_impairment",
            "pregnant",
            "mental_health_conditions"
        ]
        
        # Track what's been assessed
        self.assessed_fields = set()
    
    def analyze_victim_response(self, robot_question: str, victim_response: str) -> dict:
        """
        Analyze a victim's response to extract special needs and medical information
        
        Args:
            robot_question: The question asked by the robot
            victim_response: The victim's response
            
        Returns:
            Dictionary of extracted information
        """
        prompt = f"""{self.assessment_prompt}

CONTEXT:
Robot asked: "{robot_question}"
Victim responded: "{victim_response}"

TASK:
Analyze the victim's response and extract any special medical needs or conditions mentioned.
Look for:
1. Emergency medications (insulin, EpiPen, inhaler, etc.)
2. Regular medications they take
3. Allergies (especially drug allergies like penicillin)
4. Medical conditions (diabetes, heart condition, asthma, etc.)
5. Age or elderly status
6. Pregnancy status
7. Mobility impairments (wheelchair, cane, walker, etc.)
8. Mental health conditions

CURRENT ASSESSMENT STATE:
{json.dumps(self.special_needs, indent=2)}

OUTPUT FORMAT:
Return ONLY a valid JSON object with the fields that have NEW or UPDATED information.
Only include fields where you found specific information in the victim's response.
Use "yes" or "no" for boolean fields, and detailed descriptions for others.

Example:
{{
    "emergency_medication": "insulin for diabetes",
    "medical_conditions": "diabetes",
    "age": "67 years old",
    "elderly": "yes",
    "allergies": "penicillin"
}}

If NO new information is found, return an empty JSON object: {{}}

JSON OUTPUT:"""

        try:
            response = requests.post(
                f"{self.ollama_base_url}/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.1
                },
                timeout=180
            )
            
            if response.status_code == 200:
                result = response.json()
                response_text = result.get("response", "").strip()
                
                # Extract JSON from response
                updates = self._extract_json(response_text)
                
                # Mark fields as assessed
                for field in updates.keys():
                    if field in self.special_needs:
                        self.assessed_fields.add(field)
                
                return updates
            else:
                print(f"Error from LLM: {response.status_code}")
                return {}
                
        except Exception as e:
            print(f"Error analyzing response: {e}")
            return {}
    
    def _extract_json(self, text: str) -> dict:
        """
        Extract JSON object from LLM response text
        
        Args:
            text: Raw text from LLM
            
        Returns:
            Extracted dictionary or empty dict if parsing fails
        """
        # Try to find JSON in the text
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(json_pattern, text, re.DOTALL)
        
        for match in matches:
            try:
                data = json.loads(match)
                # Filter to only include valid fields
                filtered = {k: v for k, v in data.items() if k in self.special_needs}
                return filtered
            except json.JSONDecodeError:
                continue
        
        return {}
    
    def update_special_needs(self, updates: dict):
        """
        Update the special needs assessment with new information
        
        Args:
            updates: Dictionary of field updates
        """
        for key, value in updates.items():
            if key in self.special_needs and value and value != "unknown":
                # If field already has data, append new info
                current = self.special_needs[key]
                if current != "unknown" and current != value:
                    # Combine information
                    self.special_needs[key] = f"{current}; {value}"
                else:
                    self.special_needs[key] = value
    
    def get_special_needs(self) -> dict:
        """
        Get the current special needs assessment
        
        Returns:
            Dictionary of special needs
        """
        return self.special_needs.copy()
    
    def get_next_priority_field(self) -> str:
        """
        Get the next priority field that hasn't been assessed yet
        
        Returns:
            Field name or None if all assessed
        """
        for field in self.priority_fields:
            if field not in self.assessed_fields and self.special_needs[field] == "unknown":
                return field
        return None
    
    def is_assessment_complete(self) -> bool:
        """
        Check if the special needs assessment is complete
        
        Returns:
            True if all priority fields have been assessed
        """
        # Consider complete if top 5 priority fields are assessed
        top_priority = self.priority_fields[:5]
        assessed_count = sum(1 for field in top_priority if field in self.assessed_fields)
        return assessed_count >= 4  # At least 4 of top 5
    
    def get_assessment_status(self) -> dict:
        """
        Get the current status of the assessment
        
        Returns:
            Dictionary with assessment progress information
        """
        completed_fields = len(self.assessed_fields)
        total_fields = len(self.priority_fields)
        
        return {
            "completed_fields": completed_fields,
            "total_fields": total_fields,
            "progress_percentage": (completed_fields / total_fields) * 100,
            "assessment_complete": self.is_assessment_complete(),
            "next_priority_field": self.get_next_priority_field()
        }
    
    def needs_emergency_medication(self) -> bool:
        """
        Check if victim needs emergency medication
        
        Returns:
            True if emergency medication is needed
        """
        em = self.special_needs.get("emergency_medication", "unknown")
        return em != "unknown" and em.lower() not in ["no", "none", "n/a"]
    
    def has_critical_allergies(self) -> bool:
        """
        Check if victim has critical allergies
        
        Returns:
            True if allergies are present
        """
        allergies = self.special_needs.get("allergies", "unknown")
        return allergies != "unknown" and allergies.lower() not in ["no", "none", "n/a"]
    
    def has_mobility_limitations(self) -> bool:
        """
        Check if victim has mobility limitations
        
        Returns:
            True if mobility impairments are present
        """
        mobility = self.special_needs.get("mobility_impairment", "unknown")
        return mobility != "unknown" and mobility.lower() not in ["no", "none", "n/a"]
    
    def is_elderly(self) -> bool:
        """
        Check if victim is elderly
        
        Returns:
            True if victim is elderly (65+)
        """
        elderly = self.special_needs.get("elderly", "unknown")
        age = self.special_needs.get("age", "unknown")
        
        # Check explicit elderly field
        if elderly != "unknown" and elderly.lower() in ["yes", "true"]:
            return True
        
        # Check age field
        if age != "unknown":
            # Extract number from age string
            age_match = re.search(r'\d+', str(age))
            if age_match:
                age_num = int(age_match.group())
                return age_num >= 65
        
        return False
    
    def get_critical_needs_summary(self) -> dict:
        """
        Get a summary of critical needs that require immediate attention
        
        Returns:
            Dictionary with critical needs flags and details
        """
        return {
            "emergency_medication_needed": self.needs_emergency_medication(),
            "emergency_medication_details": self.special_needs.get("emergency_medication", "unknown"),
            "critical_allergies": self.has_critical_allergies(),
            "allergy_details": self.special_needs.get("allergies", "unknown"),
            "medical_conditions": self.special_needs.get("medical_conditions", "unknown"),
            "mobility_limited": self.has_mobility_limitations(),
            "is_elderly": self.is_elderly(),
            "is_pregnant": self.special_needs.get("pregnant", "unknown").lower() in ["yes", "true"]
        }
    
    def get_assessment(self) -> dict:
        """Get the current comfort assessment (alias for get_special_needs)"""
        return self.get_special_needs()
    
    def update_assessment(self, updates: dict):
        """Update the comfort assessment (alias for update_special_needs)"""
        return self.update_special_needs(updates)
