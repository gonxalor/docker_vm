import requests
import time
import json
from typing import Dict, List, Optional

class ComfortAgent:
    """
    LLM-powered agent responsible for calming victims through empathetic small talk
    and gathering additional context-sensitive information (medical needs, special conditions, etc.)
    """
    
    def __init__(self, model_name: str, comfort_prompt_path: str, ollama_base_url: str = "http://localhost:11434",language: str = 'en'):
        """
        Initialize the Comfort Agent with Ollama model.
        
        Args:
            model_name: Name of the model in Ollama
            comfort_prompt_path: Path to the comfort prompt file
            ollama_base_url: Base URL for Ollama API
        """
        self.model_name = model_name
        self.ollama_url = f"{ollama_base_url}/api/generate"
        self.language = language
        
        with open(comfort_prompt_path, 'r') as f:
            self.comfort_prompt = f.read()
        
        # Track special/medical needs discovered
        self.special_needs = {
            "elderly": "unknown",
            "pregnant": "unknown",
            "mobility_impairment": "unknown",
            "allergies": "unknown",
            "mental_health_conditions": "unknown",
            "regular_medication": "unknown",
            "emergency_medication": "unknown",
            "other_conditions": "unknown"
        }
        
        # Track which needs have been explicitly assessed
        self.assessed_needs = set()
        
        # Priority order for gathering special needs information
        self.needs_priority = [
            "emergency_medication",     # 1. Most critical
            "pregnant",                 # 2. High priority
            "elderly",                  # 3. Important for rescue planning
            "mobility_impairment",      # 4. Important for evacuation
            "regular_medication",       # 5. Important
            "allergies",                # 6. Important for medical treatment
            "mental_health_conditions", # 7. Important for ongoing interaction
            "other_conditions"          # 8. Catch-all
        ]
        
        # Conversation history for context
        self.conversation_history = []
        
        # Track distress level to adapt responses
        self.distress_indicators = {
            "high_distress": False,
            "anxiety": False,
            "panic": False,
            "calm": True
        }
    
    def generate_comfort_response(self, victim_response: str, assessment: Dict[str, str]) -> str:
        """
        Generate a comforting response that calms the victim while gathering additional information
        
        Args:
            victim_response: The victim's last response
            assessment: Current assessment data from AssessmentAgent
            
        Returns:
            Comforting response with follow-up question about special needs
        """
        # Analyze distress level
        self._analyze_distress(victim_response)
        
        # Build prompt
        prompt = self._build_comfort_prompt(victim_response, assessment)
        
        try:
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,  # Higher temperature for more natural, empathetic responses
                    "top_p": 0.9,
                    "num_predict": 256
                },
                "stop": ["Victim:", "\n\n"]
            }
            
            start_time = time.time()
            response = requests.post(self.ollama_url, json=payload, timeout=180)
            
            if response.status_code == 200:
                response_data = response.json()
                response_text = response_data.get("response", "").strip()
                elapsed = time.time() - start_time
                print(f"[LLM] ComfortAgent latency: {elapsed:.2f}s")
                
                # Clean up response
                if response_text.startswith("Robot:"):
                    response_text = response_text[6:].strip()
                
                # Add to conversation history
                self.conversation_history.append({
                    "role": "victim",
                    "content": victim_response
                })
                self.conversation_history.append({
                    "role": "robot",
                    "content": response_text
                })
                
                return response_text
            else:
                print(f"Error from Ollama API: {response.status_code} - {response.text}")
                return self._get_fallback_comfort_message()
                
        except requests.exceptions.Timeout:
            print(f"[ERROR] ComfortAgent request timed out")
            return self._get_fallback_comfort_message()
        except Exception as e:
            print(f"[ERROR] ComfortAgent failed: {e}")
            return self._get_fallback_comfort_message()
    
    def analyze_special_needs(self, victim_response: str) -> Dict[str, str]:
        """
        Analyze victim response to extract special/medical needs information
        
        Args:
            victim_response: The victim's response text
            
        Returns:
            Dictionary of updates to special needs
        """
        prompt = self._build_needs_analysis_prompt(victim_response)
        
        try:
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,  # Lower temperature for consistent extraction
                    "top_p": 0.9,
                    "num_predict": 256
                }
            }
            
            start_time = time.time()
            response = requests.post(self.ollama_url, json=payload, timeout=180)
            
            if response.status_code == 200:
                response_data = response.json()
                response_text = response_data.get("response", "").strip()
                elapsed = time.time() - start_time
                print(f"[LLM] ComfortAgent needs analysis latency: {elapsed:.2f}s")
                
                # Extract and validate JSON
                updates = self._extract_json(response_text)
                validated_updates = self._validate_needs_updates(updates)
                
                return validated_updates
            else:
                print(f"Error from Ollama API: {response.status_code} - {response.text}")
                return {}
                
        except requests.exceptions.Timeout:
            print(f"[ERROR] ComfortAgent needs analysis timed out")
            return {}
        except Exception as e:
            print(f"[ERROR] ComfortAgent needs analysis failed: {e}")
            return {}
    
    def _analyze_distress(self, victim_response: str):
        """
        Analyze victim's response for distress indicators
        
        Args:
            victim_response: The victim's response text
        """
        response_lower = victim_response.lower()
        
        # Check for panic indicators
        panic_words = ["help", "please", "scared", "terrified", "panic", "can't breathe", "dying"]
        self.distress_indicators["panic"] = any(word in response_lower for word in panic_words)
        
        # Check for anxiety indicators
        anxiety_words = ["worried", "anxious", "nervous", "afraid", "concerned", "don't know"]
        self.distress_indicators["anxiety"] = any(word in response_lower for word in anxiety_words)
        
        # High distress combines both
        self.distress_indicators["high_distress"] = (
            self.distress_indicators["panic"] or self.distress_indicators["anxiety"]
        )
        
        # Calm if no distress indicators
        self.distress_indicators["calm"] = not self.distress_indicators["high_distress"]
    
    def _build_comfort_prompt(self, victim_response: str, assessment: Dict[str, str]) -> str:
        """
        Build the prompt for generating comforting responses
        
        Args:
            victim_response: The victim's last response
            assessment: Current assessment data
            
        Returns:
            Complete prompt for comfort response generation
        """
        prompt = f"""{self.comfort_prompt}

CURRENT VICTIM DISTRESS LEVEL:
- High Distress: {self.distress_indicators['high_distress']}
- Panic: {self.distress_indicators['panic']}
- Anxiety: {self.distress_indicators['anxiety']}

CURRENT ASSESSMENT (medical status already gathered):
"""
        for key, value in assessment.items():
            if value and value != "unknown":
                prompt += f"- {key}: {value}\n"
        
        prompt += "\nSPECIAL NEEDS ALREADY ASSESSED:\n"
        for need in self.assessed_needs:
            if self.special_needs[need] != "unknown":
                prompt += f"- {need}: {self.special_needs[need]}\n"
        
        prompt += "\nNEXT PRIORITY NEED TO ASSESS:\n"
        next_need = self.get_next_priority_need()
        if next_need:
            prompt += f"- {next_need}\n"
        else:
            prompt += "- All needs assessed\n"
        
        prompt += "\nRECENT CONVERSATION HISTORY:\n"
        # Include last 4 exchanges for context
        recent_history = self.conversation_history[-8:] if len(self.conversation_history) > 8 else self.conversation_history
        for entry in recent_history:
            role = "Victim" if entry["role"] == "victim" else "Robot"
            prompt += f"{role}: {entry['content']}\n"
        
        prompt += f"\nVictim's Latest Response: \"{victim_response}\"\n\n"
        prompt += "Generate a comforting response that:\n"
        prompt += "1. Acknowledges their emotional state if distressed\n"
        prompt += "2. Provides reassurance that help is coming and their status has been reported\n"
        prompt += "3. Naturally transitions to asking about the next priority special need (if not all assessed)\n"
        prompt += "4. Uses empathetic, calming language\n"
        prompt += "5. Keeps the response concise (2-3 sentences maximum)\n\n"
        prompt += "Your response:"
        
        return prompt
    
    def _build_needs_analysis_prompt(self, victim_response: str) -> str:
        """
        Build prompt for analyzing special needs from victim response
        
        Args:
            victim_response: The victim's response text
            
        Returns:
            Complete prompt for needs analysis
        """
        prompt = """You are analyzing a disaster victim's response to extract special medical needs and conditions.

SPECIAL NEEDS CATEGORIES:
- elderly: Is the person elderly/senior (yes/no)
- pregnant: Is the person pregnant (yes/no, if yes include how far along)
- mobility_impairment: Any mobility issues beyond current injuries (yes/no, with details)
- allergies: Any allergies mentioned (yes/no, with specific allergens)
- mental_health_conditions: Any mental health conditions (yes/no, with details if shared)
- regular_medication: Regular medications needed (yes/no, with medication names)
- emergency_medication: Emergency medications like EpiPen, insulin (yes/no, with details)
- other_conditions: Any other medical conditions (yes/no, with details)

Extract information from the victim's response and return ONLY a JSON object.
CRITICAL: Only include fields where you found explicit information.
If no information is found, return an empty object: {}

"""
        prompt += f'Victim Response: "{victim_response}"\n\n'
        prompt += "Return JSON with extracted information:"
        
        return prompt
    
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
        
        print("[WARNING] No valid JSON found in response")
        return {}
    
    def _validate_needs_updates(self, updates: dict) -> dict:
        """
        Validate and clean the updates dictionary for special needs
        
        Args:
            updates: Raw updates from LLM
            
        Returns:
            Validated and cleaned updates dictionary
        """
        valid_updates = {}
        
        for field, value in updates.items():
            # Skip if field is not in our special needs template
            if field not in self.special_needs:
                print(f"[WARNING] Ignoring unknown need field: {field}")
                continue
            
            # Skip if value is invalid
            if not value or value == "" or value.strip() == "" or value.lower() == "unknown":
                continue
            
            # Skip if trying to update with the same value
            current_value = self.special_needs[field]
            if current_value == value:
                continue
            
            # Valid update
            valid_updates[field] = value.strip()
        
        return valid_updates
    
    def update_special_needs(self, updates: Dict[str, str]):
        """
        Update special needs information
        
        Args:
            updates: Dictionary of validated updates to special needs
        """
        for key, value in updates.items():
            if key not in self.special_needs:
                continue
            
            current_value = self.special_needs[key]
            
            # Update from "unknown" to known value
            if current_value == "unknown":
                self.special_needs[key] = value
                self.assessed_needs.add(key)
                print(f"[COMFORT AGENT UPDATE] {key}: unknown → {value}")
            
            # Update existing value (append if it's additional info)
            elif value != current_value:
                self.special_needs[key] = value
                self.assessed_needs.add(key)
                print(f"[COMFORT AGENT UPDATE] {key}: {current_value} → {value}")
    
    def get_next_priority_need(self) -> str:
        """
        Get the next priority special need to assess
        
        Returns:
            Name of the next need to assess, or empty string if all assessed
        """
        for need in self.needs_priority:
            if need not in self.assessed_needs:
                return need
        return ""
    
    def is_comfort_phase_complete(self) -> bool:
        """
        Check if all priority special needs have been assessed
        
        Returns:
            True if all needs assessed, False otherwise
        """
        for need in self.needs_priority:
            if need not in self.assessed_needs:
                return False
        return True
    
    def get_special_needs(self) -> Dict[str, str]:
        """Get the current special needs information"""
        return self.special_needs.copy()
    
    def get_distress_level(self) -> Dict[str, bool]:
        """Get the current distress indicators"""
        return self.distress_indicators.copy()
    
    def _get_fallback_comfort_message(self) -> str:
        """
        Get a fallback comfort message if LLM fails
        
        Returns:
            Basic comfort message
        """

        if self.language == "es":
            if self.distress_indicators["high_distress"]:
                return "Entiendo que estás pasando por un momento difícil. La ayuda está en camino. ¿Tienes alguna condición médica o necesidad que deba saber?"
            else:
                return "Gracias por mantener la calma. Su información ha sido enviada al equipo de rescate. ¿Tiene alguna necesidad médica especial, como medicamentos o afecciones que deba tener en cuenta?"
        
        elif self.language == "fr":
            if self.distress_indicators["high_distress"]:
                return "Je comprends que vous traversez une période difficile. De l'aide arrive. Avez-vous des problèmes de santé ou des besoins particuliers dont je devrais être informé(e) ?"
            else:
                return "Merci de garder votre calme. Vos informations ont été transmises à l'équipe de secours. Avez-vous des besoins médicaux particuliers, comme des médicaments ou des problèmes de santé dont je devrais être informé(e) ?"
    
        else:
            if self.distress_indicators["high_distress"]:
                return "I understand you're going through a difficult time. Help is on the way. Do you have any medical conditions or needs I should know about?"
            else:
                return "Thank you for staying calm. Your information has been sent to the rescue team. Do you have any special medical needs, such as medications or conditions I should be aware of?"
    
    
    def reset(self):
        """Reset the comfort agent for a new conversation"""
        self.special_needs = {key: "unknown" for key in self.special_needs}
        self.assessed_needs = set()
        self.conversation_history = []
        self.distress_indicators = {
            "high_distress": False,
            "anxiety": False,
            "panic": False,
            "calm": True
        }
    
    def get_initial_message(self) -> str:
        """Generate initial comfort message for Phase 2"""
        # Simple calming opening message
        if self.language == 'fr':
            return "Je suis là avec vous. Comment vous sentez-vous ? Y a-t-il quelque chose que je devrais savoir pour que vous soyez plus à l'aise ?"
        elif self.language == 'es':
            return "Estoy aquí contigo ahora. Cómo te sientes? Hay algo que deba saber para que estés cómoda?"
        else:
            return "I'm here with you now. How are you feeling? Is there anything I should know to help keep you comfortable?"
    
    def add_to_history(self, role: str, message: str):
        """Add message to conversation history"""
        if not hasattr(self, 'conversation_history'):
            self.conversation_history = []
        self.conversation_history.append({"role": role, "content": message})
    
    def get_next_response(self, assessment: dict, is_complete: bool, next_field: str) -> str:
        """
        Generate next comfort response based on assessment state.
        
        Args:
            assessment: Current comfort assessment
            is_complete: Whether assessment is complete
            next_field: Next field to assess
        
        Returns:
            Robot comfort message
        """
        if is_complete:
            return ""
        
        # Generate question based on what we need to know
        if next_field:
            return self._generate_targeted_comfort_question(next_field, assessment)
        
        if self.language == "es":
            default = "¿Hay algo más que debería saber para ayudarle a sentirse cómodo?"
        elif self.language == "fr":
            default = "Y a-t-il autre chose que je devrais savoir pour contribuer à votre confort ?"
        else:
            default = "Is there anything else I should know to help keep you comfortable?"        
        
        return default
    
    def _generate_targeted_comfort_question(self, field: str, assessment: dict) -> str:
        """Generate a targeted question for a specific assessment field"""
        questions_en = {
            "emergency_medication": "Do you need any medications right now? Like insulin, an inhaler, or anything else?",
            "pregnant": "I need to know - are you pregnant? This helps me know how best to help you.",
            "elderly": "Can you tell me your age? This helps us plan the best way to get you out.",
            "mobility_impairment": "Are you able to walk on your own, or do you have any mobility issues?",
            "regular_medication": "Are you on any regular medications I should know about?",
            "allergies": "Do you have any allergies I should be aware of?",
            "mental_health_conditions": "Is there anything about your health or any conditions that might affect how you're feeling right now?",
            "other_conditions": "Is there anything else about your health or situation I should know?"
        }

        questions_fr = {
            "emergency_medication": "Avez-vous besoin de médicaments tout de suite ? Comme de l'insuline, un inhalateur, ou autre chose ?",
            "pregnant": "J'ai besoin de savoir : êtes-vous enceinte ? Cela m'aide à savoir comment vous aider au mieux.",
            "elderly": "Pouvez-vous me dire votre âge ? Cela nous aide à planifier la meilleure façon de vous faire sortir.",
            "mobility_impairment": "Êtes-vous capable de marcher seule, ou avez-vous des problèmes de mobilité ?",
            "regular_medication": "Prenez-vous des médicaments réguliers dont je devrais être au courant ?",
            "allergies": "Avez-vous des allergies dont je devrais être informé(e) ?",
            "mental_health_conditions": "Y a-t-il quelque chose concernant votre santé ou toute condition qui pourrait affecter votre état actuel ?",
            "other_conditions": "Y a-t-il autre chose concernant votre santé ou votre situation que je devrais savoir ?"
        }

        questions_es = {
            "emergency_medication": "¿Necesita algún medicamento ahora mismo? ¿Como insulina, un inhalador o algo más?",
            "pregnant": "Necesito saber: ¿está embarazada? Esto me ayuda a saber cómo asistirla mejor.",
            "elderly": "¿Puede decirme su edad? Esto nos ayuda a planificar la mejor manera de sacarla.",
            "mobility_impairment": "¿Puede caminar por sí misma o tiene algún problema de movilidad?",
            "regular_medication": "¿Toma algún medicamento regular que deba saber?",
            "allergies": "¿Tiene alguna alergia que deba tener en cuenta?",
            "mental_health_conditions": "¿Hay algo sobre su salud o alguna condición que pueda afectar cómo se siente en este momento?",
            "other_conditions": "¿Hay algo más sobre su salud o situación que deba saber?"
        }

        if self.language == "fr":
            questions = questions_fr
            default = "Y a-t-il autre chose que je devrais savoir ?"
        elif self.language == "es":
            questions = questions_es
            default = "¿Hay algo más que debería saber?" 
        else:
            questions = questions_en
            default = "Is there anything else I should know?"   
        
        return questions.get(field, default)
    
    def set_situation_context(self, context: str):
        """Set the disaster situation context"""
        self.situation_context = context
