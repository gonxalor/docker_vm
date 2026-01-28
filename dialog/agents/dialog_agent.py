from typing import Dict, List, Optional
import requests
import time


class DialogueAgent:
    """
    Agent responsible for generating context-aware rescue dialogue during Phase 1 assessment.
    
    This agent focuses exclusively on generating appropriate questions and responses
    based on the current assessment state and next priority field. It adapts its
    communication style based on the configured empathy level (low/medium/high).
    
    Key Responsibilities:
    - Generate initial greeting and assessment questions
    - Build contextual prompts including conversation history
    - Adapt empathy level based on configuration
    - Maintain conversation history for context
    - Generate appropriate final messages when assessment completes
    
    Architecture:
    - Uses Ollama LLM (gemma3:12b) for natural language generation
    - Temperature: 0.4 for consistent, focused responses
    - Timeout: 60s for all API requests
    - Empathy levels: low (direct), medium (balanced), high (compassionate)
    """
    
    def __init__(
        self,
        model_name: str,
        dialogue_prompt_path: str,
        empathy_level: str = "medium",
        ollama_base_url: str = "http://localhost:11434",
        language: str = 'en'
    ):
        """
        Initialize the Dialogue Agent with Ollama Gemma model.
        
        Args:
            model_name: Name of the Gemma model in Ollama (e.g., "gemma3:12b")
            dialogue_prompt_path: Path to the base dialogue prompt file
            empathy_level: Communication style - "low", "medium", or "high"
            ollama_base_url: Base URL for Ollama API (default: localhost:11434)
        """

        self.model_name = model_name
        self.ollama_url = f"{ollama_base_url}/api/generate"
        self.empathy_level = empathy_level
        self.language = language
        self.all_final_messages = self._define_messages()
        
        # Load base dialogue prompt
        try:
            with open(dialogue_prompt_path, 'r', encoding='utf-8') as f:
                base_prompt = f.read()
        except FileNotFoundError:
            print(f"[ERROR] DialogueAgent: Prompt file not found at {dialogue_prompt_path}")
            base_prompt = "You are a rescue robot assisting victims."
        
        # Append empathy-specific instructions
        empathy_instructions = self._load_empathy_instructions(empathy_level)
        self.dialogue_prompt = base_prompt + "\n\n" + empathy_instructions


        # Conversation state
        self.conversation_history = []
        self.last_robot_question = ""
        self.asked_questions = set()  # Track questions to avoid repetition
        self.situation_context = ""  # Optional context about the situation
    
    # ===== Configuration Methods =====
    
    def set_situation_context(self, context: str):
        """
        Set additional situation context to include in prompts
        
        Args:
            context: Descriptive text about the situation/environment
        """
        self.situation_context = context
    
    def _load_empathy_instructions(self, level: str) -> str:
        """
        Load empathy-specific instructions from file
        
        Args:
            level: Empathy level (low/medium/high)
            
        Returns:
            Empathy instruction text
        """
        empathy_files = {
            "low": "data/low_empathy_instructions.txt",
            "medium": "data/medium_empathy_instructions.txt",
            "high": "data/high_empathy_instructions.txt"
        }
        
        filepath = empathy_files.get(level, empathy_files["medium"])
        
        try:
            with open(filepath, 'r') as f:
                return f.read()
        except FileNotFoundError:
            print(f"[ERROR] DialogueAgent: Empathy file not found at {filepath}, using defaults")
            return self._get_default_empathy_instructions(level)
    
    def _get_default_empathy_instructions(self, level: str) -> str:
        """
        Get default empathy instructions if files are not available
        
        Args:
            level: Empathy level
            
        Returns:
            Default instruction text
        """
        if level == "low":
            return "Keep responses short and direct. Focus on facts only."
        elif level == "high":
            return "Be compassionate and reassuring. Show empathy and concern."
        else:  # medium
            return "Be professional but caring. Balance efficiency with empathy."
    
    # ===== Conversation Starters =====
    
    def get_initial_response(self) -> str:
        """
        Generate the initial greeting to start the conversation
        
        Returns:
            Opening message adapted to empathy level
        """

        print("xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
        print(f"THIS IS THE MODEL NAME: {self.model_name}")
        print("xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
        if self.language == 'en':
            greetings = {
                "low": "Hello. Are you injured?",
                "medium": "Hello. I am a rescue robot here to help you. Are you injured?",
                "high": "Hello, I'm a rescue robot and I'm here to help you. Are you injured or in pain? Please tell me what happened."
            }
        elif self.language == "es":
            greetings = {
                "low": "Hola. Está herido?",
                "medium": "Hola. Soy un robot de rescate y estoy aquí para ayudarle. Está herido?",
                "high": "Hola, soy un robot de rescate y estoy aquí para ayudarle. Está herido o siente dolor? Por favor, dígame qué pasó."
            }
        elif self.language == 'fr':
            greetings = {
                "low": "Bonjour. Êtes-vous blessé?",
                "medium": "Bonjour. Je suis un robot de sauvetage et je suis là pour vous aider. Êtes-vous blessé ?",
                "high": "Bonjour, je suis un robot de sauvetage et je suis là pour vous aider. Êtes-vous blessé ou souffrez-vous? Veuillez me dire ce qui s'est passé."
            }            
        initial_response = greetings.get(self.empathy_level, greetings["medium"])
        
        self.add_to_history("robot", initial_response)
        self.last_robot_question = initial_response
        return initial_response
    
    # ===== Prompt Building =====
    
    # ===== Prompt Building =====
    
    def build_prompt(self, assessment: Dict[str, str], next_field: str = "") -> str:
        """
        Build a comprehensive prompt for the LLM including all relevant context
        
        Args:
            assessment: Current assessment dictionary from AssessmentAgent
            next_field: The next priority field that needs to be assessed
            
        Returns:
            Complete prompt string for LLM generation
        """
        prompt_parts = []
        
        # 1. Base dialogue instructions
        prompt_parts.append(self.dialogue_prompt)
        
        # 2. Situation context (if provided)
        if self.situation_context:
            prompt_parts.append(f"\nSITUATION CONTEXT:\n{self.situation_context}")
        
        # 3. Current assessment state
        prompt_parts.append("\nCURRENT ASSESSMENT:")
        if assessment:
            for key, value in assessment.items():
                if value and value != "unknown":
                    prompt_parts.append(f"- {key}: {value}")
        else:
            prompt_parts.append("- No information collected yet")
        
        # 4. Conversation history
        prompt_parts.append("\nCONVERSATION HISTORY:")
        if self.conversation_history:
            for entry in self.conversation_history:
                role_label = "Victim" if entry["role"] == "victim" else "Robot"
                prompt_parts.append(f"{role_label}: {entry['content']}")
        else:
            prompt_parts.append("(This is the start of the conversation)")
        
        # 5. Instructions for next response
        prompt_parts.append("\nINSTRUCTIONS FOR NEXT RESPONSE:")
        if next_field:
            prompt_parts.append(f"The next priority field to assess is: {next_field}")
            prompt_parts.append(f"Ask a clear, direct question about {next_field}.")
            prompt_parts.append("Follow the RESPONSE STRUCTURE defined above.")
        else:
            prompt_parts.append("All assessment fields have been completed.")
            prompt_parts.append("Provide an appropriate final message or summary.")
        
        return "\n".join(prompt_parts)
    
    def build_action_prompt(self, assessment: Dict[str, str], next_field: str, action: str) -> str:
        """
        Build prompt that includes action decision context (for integration with ActionAgent)
        
        Args:
            assessment: Current assessment dictionary
            next_field: Next priority field to assess
            action: The decided action from ActionAgent
            
        Returns:
            Complete prompt including action context
        """
        prompt_parts = []
        
        # 1. Base dialogue instructions
        prompt_parts.append(self.dialogue_prompt)
        
        # 2. Situation context (if provided)
        if self.situation_context:
            prompt_parts.append(f"\nSITUATION CONTEXT:\n{self.situation_context}")
        
        # 3. Robot's action decision
        prompt_parts.append(f"\nROBOT'S DECIDED ACTION: {action}")
        
        # 4. Current assessment
        prompt_parts.append("\nCURRENT ASSESSMENT:")
        for key, value in assessment.items():
            if value and value != "unknown":
                prompt_parts.append(f"- {key}: {value}")
        
        # 5. Conversation history
        prompt_parts.append("\nCONVERSATION HISTORY:")
        for entry in self.conversation_history:
            role_label = "Victim" if entry["role"] == "victim" else "Robot"
            prompt_parts.append(f"{role_label}: {entry['content']}")
        
        # 6. Instructions
        prompt_parts.append("\nINSTRUCTIONS:")
        if next_field:
            prompt_parts.append(f"Next priority field: {next_field}")
            prompt_parts.append(f"Ask a question about {next_field}.")
            prompt_parts.append(f"Keep in mind the robot's action: {action}")
        else:
            prompt_parts.append("Assessment complete. Provide final message.")
            prompt_parts.append(f"Consider the robot's action: {action}")
        
        return "\n".join(prompt_parts)
    
    # ===== LLM Response Generation =====
    
    # ===== LLM Response Generation =====
    
    def get_llm_response(self, prompt: str) -> str:
        """
        Generate a response from the Ollama LLM with proper error handling
        
        Args:
            prompt: Complete prompt to send to the LLM
            
        Returns:
            Generated response text, or fallback message if error occurs
        """
        try:
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.4,  # Lower temperature for more consistent responses
                    "top_p": 0.9,
                    "num_predict": 256
                },
                "stop": ["Victim:", "\n\n", "Robot:"]  # Stop tokens to prevent overgeneration
            }
            
            start_time = time.time()
            response = requests.post(self.ollama_url, json=payload, timeout=180)  # Added timeout
            
            if response.status_code == 200:
                response_data = response.json()
                response_text = response_data.get("response", "").strip()
                elapsed = time.time() - start_time
                print(f"[LLM] DialogueAgent latency: {elapsed:.2f}s")
                
                # Clean response
                response_text = self._clean_response(response_text)
                
                # Apply empathy-based length constraints
                response_text = self._apply_length_constraints(response_text)
                
                # Fallback if response is empty after cleaning
                if not response_text:
                    return False
                
                return response_text
                
            else:
                print(f"[ERROR] DialogueAgent: Ollama API returned {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
        except requests.exceptions.Timeout:
            print(f"[ERROR] DialogueAgent: Request timed out after 60s")
            return False
        except requests.exceptions.ConnectionError:
            print(f"[ERROR] DialogueAgent: Could not connect to Ollama at {self.ollama_url}")
            return False
        except Exception as e:
            print(f"[ERROR] DialogueAgent: Unexpected error - {type(e).__name__}: {e}")
            return False
    
    def _clean_response(self, text: str) -> str:
        """
        Clean LLM response by removing unwanted prefixes and formatting
        
        Args:
            text: Raw LLM response
            
        Returns:
            Cleaned response text
        """
        # Remove "Robot:" prefix variations
        prefixes = ["Robot:", "Robot ", "ROBOT:", "robot:"]
        for prefix in prefixes:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        
        return text
    
    def _apply_length_constraints(self, text: str) -> str:
        """
        Apply empathy-level specific length constraints
        
        Args:
            text: Response text to constrain
            
        Returns:
            Constrained text
        """
        max_sentences = {
            "low": 2,
            "medium": 2,
            "high": 4
        }
        
        limit = max_sentences.get(self.empathy_level, 2)
        
        sentences = text.split('. ')
        if len(sentences) > limit:
            text = '. '.join(sentences[:limit])
            if not text.endswith('.'):
                text += '.'
        
        return text
    
    def _get_fallback_question(self) -> str:
        """
        Get a safe fallback question based on empathy level
        
        Returns:
            Appropriate fallback question
        """
        fallbacks = {
            "low": "Are you injured?",
            "medium": "Can you tell me if you're injured?",
            "high": "I'm here to help you. Can you tell me if you're injured or in pain?"
        }
        
        return fallbacks.get(self.empathy_level, fallbacks["medium"])
    
    # ===== Main Response Methods =====
    
    # ===== Main Response Methods =====
    
    def get_next_response(
        self,
        assessment: Dict[str, str],
        is_assessment_complete: bool,
        next_field: str = ""
    ) -> str:
        """
        Generate the next response based on current assessment state
        
        The LLM will naturally acknowledge any urgent concerns (insulin, missing kids, 
        trapped people, etc.) mentioned in the victim's previous response, as guided by
        the dialogue prompt.
        
        Args:
            assessment: Current assessment dictionary
            is_assessment_complete: Whether all assessment fields are complete
            next_field: The next priority field to assess (if not complete)
            
        Returns:
            Next question or final message
        """
        if is_assessment_complete:
            # Generate final message based on assessment
            can_walk = "yes" in assessment.get("can_walk", "").lower()
            is_stuck = self._check_if_stuck(assessment)
            return self.get_final_message(can_walk, is_stuck)
        else:
            # Generate next assessment question
            # The LLM will naturally acknowledge urgent concerns based on conversation history
            prompt = self.build_prompt(assessment, next_field)
            response = self.get_llm_response(prompt)
            
            if not response:
                return False
                
            
            self.add_to_history("robot", response)
            self.last_robot_question = response
            return response
    
    def get_next_response_with_action(
        self,
        assessment: Dict[str, str],
        is_assessment_complete: bool,
        next_field: str = "",
        action_decision: Optional[Dict] = None
    ) -> str:
        """
        Generate response considering action decision from ActionAgent
        
        Args:
            assessment: Current assessment dictionary
            is_assessment_complete: Whether assessment is complete
            next_field: Next field to assess
            action_decision: Dictionary with action decision (if available)
            
        Returns:
            Response incorporating action context
        """
        if action_decision:
            action = action_decision.get("action", "Maintain safety and observe")
            return self.get_action_based_response(
                assessment, action, is_assessment_complete, next_field
            )
        else:
            # Fallback to standard response
            return self.get_next_response(assessment, is_assessment_complete, next_field)
    
    def get_action_based_response(
        self,
        assessment: Dict[str, str],
        action: str,
        is_assessment_complete: bool,
        next_field: str = ""
    ) -> str:
        """
        Generate response based on action decision
        
        The LLM will naturally acknowledge any urgent concerns mentioned by the victim,
        as guided by the dialogue prompt.
        
        Args:
            assessment: Current assessment dictionary
            action: Decided action string from ActionAgent
            is_assessment_complete: Whether assessment is complete
            next_field: Next field to assess
            
        Returns:
            Action-aware response
        """
        if is_assessment_complete:
            return self.get_action_based_final_message(action, assessment)
        
        # Generate question with action context
        # The LLM will naturally acknowledge urgent concerns based on conversation history
        prompt = self.build_action_prompt(assessment, next_field, action)
        response = self.get_llm_response(prompt)
        
        self.add_to_history("robot", response)
        self.last_robot_question = response
        return response
    
    # ===== Final Message Generation =====
    
    def get_final_message(self, can_walk: bool, is_stuck: bool = False) -> str:
        """
        Generate appropriate final message when assessment is complete
        
        Args:
            can_walk: Whether victim can walk
            is_stuck: Whether victim is stuck/trapped
            
        Returns:
            Final message adapted to empathy level and situation
        """
        if can_walk and not is_stuck:
            # Victim can evacuate
            messages_en = {
                "low": "Assessment complete. Follow me to safety.",
                "medium": "Assessment complete. You can walk, so please follow me to safety.",
                "high": "You've been very brave. I've completed my assessment and you can walk safely. Please follow me to the evacuation point. I'll help you the entire way."
            }
            
            # --- Translations for Evacuation Messages ---
            messages_es = {
                "low": "Evaluación completa. Sígame a un lugar seguro.",
                "medium": "Evaluación completa. Puede caminar, por favor, sígame a un lugar seguro.",
                "high": "Ha sido muy valiente. He completado mi evaluación y puede caminar sin peligro. Por favor, sígame hasta el punto de evacuación. Le ayudaré durante todo el camino."
            }
            messages_fr = {
                "low": "Évaluation terminée. Suivez-moi vers la sécurité.",
                "medium": "Évaluation terminée. Vous pouvez marcher, veuillez donc me suivre vers la sécurité.",
                "high": "Vous avez été très courageux(se). J'ai terminé mon évaluation et vous pouvez marcher en toute sécurité. Veuillez me suivre jusqu'au point d'évacuation. Je vais vous aider tout le long du chemin."
            }
        else:
            # Victim needs specialized help
            messages_en = {
                "low": "Assessment complete. Emergency services dispatched. Stay where you are.",
                "medium": "Assessment complete. Emergency services are on the way. Please remain in place.",
                "high": "You've been very brave. My assessment is complete, and I've called for specialized help. Please stay where you are. A rescue team is on the way to your location."
            }
            
            # --- Translations for Specialized Help Messages ---
            messages_es = {
                "low": "Evaluación completa. Servicios de emergencia enviados. Quédese donde está.",
                "medium": "Evaluación completa. Los servicios de emergencia están en camino. Por favor, permanezca en su sitio.",
                "high": "Ha sido muy valiente. Mi evaluación ha finalizado, y he llamado a ayuda especializada. Por favor, quédese donde está. Un equipo de rescate ya está en camino hacia su ubicación."
            }
            messages_fr = {
                "low": "Évaluation terminée. Services d'urgence dépêchés. Restez où vous êtes.",
                "medium": "Évaluation terminée. Les services d'urgence sont en route. Veuillez rester sur place.",
                "high": "Vous avez été très courageux(se). Mon évaluation est terminée et j'ai appelé de l'aide spécialisée. Veuillez rester où vous êtes. Une équipe de sauvetage est en route vers votre emplacement."
            }

        # --- 2. Select the final message dictionary based on language ---
        if self.language == 'es':
            messages = messages_es
        elif self.language == 'fr':
            messages = messages_fr
        elif self.language == 'en':
            messages = messages_en
        
        return messages.get(self.empathy_level, messages["medium"])
    
    def _define_messages(self):
        """Defines all message templates separated by language and action."""
        
        # 1. Action: Guide to Safety (Victim can walk)
        guide_action = "Guide the victim to walk to the safe zone"
        guide_messages = {
            'en': {
                "low": "Assessment complete. Follow me to safety.",
                "medium": "Assessment complete. You can walk, so please follow me to safety.",
                "high": "You've been very brave. I've completed my assessment and you can walk safely. Please follow me to the evacuation point. I'll help you the entire way."
            },
            'es': {
                "low": "Evaluación completa. Sígame a un lugar seguro.",
                "medium": "Evaluación completa. Puede caminar, por favor, sígame a un lugar seguro.",
                "high": "Ha sido muy valiente. He completado mi evaluación y puede caminar sin peligro. Por favor, sígame hasta el punto de evacuación. Le ayudaré durante todo el camino."
            },
            'fr': {
                "low": "Évaluation terminée. Suivez-moi vers la sécurité.",
                "medium": "Évaluation terminée. Vous pouvez marcher, veuillez donc me suivre vers la sécurité.",
                "high": "Vous avez été très courageux(se). J'ai terminé mon évaluation et vous pouvez marcher en toute sécurité. Veuillez me suivre jusqu'au point d'évacuation. Je vais vous aider tout le long du chemin."
            }
        }
        
        # 2. Action: Maintain Safety (Immediate Danger)
        abandon_action = "Abandon immediate evacuation and maintain safety"
        abandon_messages = {
            'en': {
                "low": "Immediate danger detected. Stay where you are. Emergency services coming.",
                "medium": "There's immediate danger. Please stay in place. Help is coming.",
                "high": "I need to prioritize our safety right now. Please stay exactly where you are. Emergency responders are on their way to help us both."
            },
            'es': {
                "low": "Peligro inmediato detectado. Quédese donde está. Servicios de emergencia en camino.",
                "medium": "Hay peligro inmediato. Por favor, permanezca en su sitio. La ayuda viene en camino.",
                "high": "Debo priorizar nuestra seguridad en este momento. Por favor, quédese exactamente donde está. Los equipos de emergencia están en camino para ayudarnos a ambos."
            },
            'fr': {
                "low": "Danger immédiat détecté. Restez où vous êtes. Les services d'urgence arrivent.",
                "medium": "Il y a un danger immédiat. Veuillez rester sur place. L'aide arrive.",
                "high": "Je dois donner la priorité à notre sécurité pour le moment. Veuillez rester exactement où vous êtes. Les équipes d'urgence sont en route pour nous aider tous les deux."
            }
        }

        # 3. Action: Talk to Calm Down (Anxious Victim)
        calm_action = "Talk to the victim to calm them down"
        calm_messages = {
            'en': {
                "low": "Stay calm. Help is on the way.",
                "medium": "Please try to stay calm. Help is on the way and you're safe.",
                "high": "I know this is frightening, but you're doing great. Help is coming and you're safe with me. Just stay calm and breathe slowly."
            },
            'es': {
                "low": "Mantenga la calma. La ayuda está en camino.",
                "medium": "Por favor, intente mantener la calma. La ayuda está en camino y está seguro(a).",
                "high": "Sé que esto da miedo, pero lo está haciendo muy bien. La ayuda viene en camino y está seguro(a) conmigo. Simplemente mantenga la calma y respire lentamente."
            },
            'fr': {
                "low": "Restez calme. L'aide est en route.",
                "medium": "Veuillez essayer de rester calme. L'aide est en route et vous êtes en sécurité.",
                "high": "Je sais que c'est effrayant, mais vous vous en sortez très bien. L'aide arrive et vous êtes en sécurité avec moi. Restez juste calme et respirez lentement."
            }
        }

        # 4. Default Fallback / Specialized Help (Victim cannot walk)
        default_messages = {
            'en': {
                "low": "Assessment complete. Emergency services dispatched. Stay where you are.",
                "medium": "Assessment complete. Emergency services are on the way. Please remain in place.",
                "high": "You've been very brave. My assessment is complete, and I've called for specialized help. Please stay where you are. A rescue team is on the way to your location."
            },
            'es': {
                "low": "Evaluación completa. Servicios de emergencia enviados. Quédese donde está.",
                "medium": "Evaluación completa. Los servicios de emergencia están en camino. Por favor, permanezca en su sitio.",
                "high": "Ha sido muy valiente. Mi evaluación ha finalizado, y he llamado a ayuda especializada. Por favor, quédese donde está. Un equipo de rescate ya está en camino hacia su ubicación."
            },
            'fr': {
                "low": "Évaluation terminée. Services d'urgence dépêchés. Restez où vous êtes.",
                "medium": "Évaluation terminée. Les services d'urgence sont en route. Veuillez rester sur place.",
                "high": "Vous avez été très courageux(se). Mon évaluation est terminée et j'ai appelé de l'aide spécialisée. Veuillez rester où vous êtes. Une équipe de sauvetage est en route vers votre emplacement."
            }
        }
        
        # 5. No Response Message (Victim silence)
        no_response_messages = {
            'en': {
                "low": "Please respond to my question.",
                "medium": "I didn't catch that. Could you please speak again?",
                "high": "I didn't catch what you said. Please don't worry, I'm here to help. Could you speak again?"
            },
            'es': {
                "low": "Por favor, responda a mi pregunta.",
                "medium": "No le he entendido. ¿Podría hablar de nuevo, por favor?",
                "high": "No he captado lo que ha dicho. Por favor, no se preocupe, estoy aquí para ayudar. ¿Podría hablar de nuevo?"
            },
            'fr': {
                "low": "Veuillez répondre à ma question.",
                "medium": "Je n'ai pas compris cela. Pourriez-vous répéter s'il vous plaît?",
                "high": "Je n'ai pas entendu ce que vous avez dit. Ne vous inquiétez pas, je suis là pour vous aider. Pourriez-vous parler à nouveau ?"
            }
        }
        return {
            guide_action: guide_messages,
            abandon_action: abandon_messages,
            calm_action: calm_messages,
            "default": default_messages,
            "no_response": no_response_messages
        }


    
    def get_action_based_final_message(self, action: str, assessment: Dict[str, str]) -> str:
        """
        Generate final message based on action decision and current language/empathy level.
        """
        
        # Select the current language (defaults to 'en')
        language = self.language if self.language in ['es', 'fr', 'en'] else 'en'
        
        # 1. Find matching action template
        templates = None
        for key, messages_by_lang in self.all_final_messages.items():
            if key != "default" and key in action:
                templates = messages_by_lang.get(language, self.all_final_messages["default"][language])
                break
                
        # 2. Use default fallback if no action match was found
        if templates is None:
            templates = self.all_final_messages["default"].get(language)
        
        # 3. Return the message corresponding to the empathy level
        return templates.get(self.empathy_level, templates["medium"])


    def get_no_response_message(self) -> str:
        """
        Generate message when victim doesn't respond in the correct language.
        """
        
        # Select the current language (defaults to 'en')
        language = self.language if self.language in ['es', 'fr', 'en'] else 'en'
        
        # Get the no response templates for the selected language
        templates = self.all_final_messages["no_response"].get(language)

        # Return the message corresponding to the empathy level
        return templates.get(self.empathy_level, templates["medium"])
    
    # ===== Conversation History Management =====
    
    # ===== Conversation History Management =====
    
    def add_to_history(self, role: str, content: str):
        """
        Add entry to conversation history and track asked questions
        
        Args:
            role: Either "robot" or "victim"
            content: The message content
        """
        self.conversation_history.append({"role": role, "content": content})
        
        # Track questions to avoid repetition
        if role == "robot" and '?' in content:
            question_parts = content.split('?')
            if len(question_parts) > 1:
                # Extract the main question (last sentence before ?)
                main_question = question_parts[0].split('.')[-1].strip().lower()
                if len(main_question) > 5:  # Minimum meaningful question length
                    self.asked_questions.add(main_question)
    
    def get_conversation_history(self) -> List[Dict[str, str]]:
        """
        Get the complete conversation history
        
        Returns:
            List of conversation entries with role and content
        """
        return self.conversation_history
    
    def get_last_robot_question(self) -> str:
        """
        Get the last question asked by the robot
        
        Returns:
            Last robot question text
        """
        return self.last_robot_question
    
    # ===== Helper Methods =====
    
    def _check_if_stuck(self, assessment: Dict[str, str]) -> bool:
        """
        Check if victim is stuck/trapped based on assessment
        
        Args:
            assessment: Current assessment dictionary
            
        Returns:
            True if victim is stuck/trapped
        """
        stuck_field = assessment.get("stuck_trapped", "").lower()
        return ("yes" in stuck_field or "stuck" in stuck_field or "trapped" in stuck_field)