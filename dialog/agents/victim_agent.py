import json
import requests

class VictimAgent:
    """
    LLM-powered agent responsible for simulating victim responses in a disaster scenario.
    """

    def __init__(self, model_name: str, victim_prompt_path: str, victim_info_path: str, ollama_base_url: str = "http://localhost:11434"):
        """
        Initialize the Victim Agent with Ollama model.
        
        Args:
            model_name: Name of the model in Ollama
            victim_prompt_path: Path to the victim system prompt file
            victim_info_path: Path to the victim info JSON file
            ollama_base_url: Base URL for Ollama API
        """
        self.model_name = model_name
        self.ollama_url = f"{ollama_base_url}/api/generate"
        
        with open(victim_prompt_path, 'r') as f:
            self.victim_prompt = f.read().strip()

        with open(victim_info_path, 'r') as f:
            self.victim_info = json.load(f)

        self.base_prompt = (
            f"{self.victim_prompt}\n\n"
            "Victim Information:\n"
            f"{json.dumps(self.victim_info, indent=2)}\n\n"
        )

        self.conversation_history = ""

    def generate_response(self, question: str) -> str:
        """
        Generate victim response using LLM based on the current question and conversation history.
        """
        prompt = self._build_victim_prompt(question)
        try:
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "temperature": 0.7,
                "max_tokens": 150
            }
            
            response = requests.post(self.ollama_url, json=payload, timeout=180)
            if response.status_code == 200:
                response_data = response.json()
                victim_response = response_data.get("response", "").strip()

                self.conversation_history += f"Robot: {question}\nVictim: {victim_response}\n"
                
                return victim_response
            else:
                print(f"Error from Ollama API: {response.text}")
                return ""
        except Exception as e:
            print(f"Exception during Ollama API call: {e}")
            return ""
    
    def _build_victim_prompt(self, question: str) -> str:
        """
        Build the complete prompt for the victim LLM including base prompt and conversation history.
        """
        return (
            self.base_prompt +
            self.conversation_history +
            f"Robot: {question}\nVictim:"
        )
