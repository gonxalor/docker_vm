"""
Configuration Manager Module
Handles system configuration and setup
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any
import os
import argparse

OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://localhost:11434')

@dataclass
class AudioConfig:
    """Configuration for audio processing"""
    empathy_level: str = "medium"
    whisper_model: str = "base"
    language: str = "en"
    sample_rate: int = 16000
    chunk_size: int = 1024
    max_recording_duration: int = 10
    silence_threshold: float = 0.01
    silence_duration: float = 2.0
    tts_volume: float = 0.9


@dataclass
class ModelConfig:
    """Configuration for AI models"""
    model_name: str = "gemma3:12b"
    ollama_base_url: str = OLLAMA_URL
    dialogue_prompt_path: str = "prompts/dialogue_prompt.txt"
    assessment_prompt_path: str = "prompts/assessment_prompt.txt"
    triage_prompt_path: str = "prompts/triage_prompt.txt"
    confort_prompt_path: str = "prompts/confort_prompt.txt"
    language: str = "en"


@dataclass
class LocationConfig:
    """Configuration for GPS location"""
    latitude: float = 38.7223
    longitude: float = -9.1393
    description: str = "Oeiras, Lisbon, Portugal"


@dataclass
class ConversationConfig:
    """Configuration for conversation parameters"""
    max_turns: int = 10
    max_retries: int = 3
    test_audio_on_start: bool = False


class ConfigManager:
    """Manages system configuration and setup"""
    
    def __init__(self):
        self.audio_config = AudioConfig()
        self.model_config = ModelConfig()
        self.location_config = LocationConfig()
        self.conversation_config = ConversationConfig()
    
    @classmethod
    def from_args(cls, args: Optional[argparse.Namespace] = None) -> 'ConfigManager':
        """
        Create configuration from command line arguments
        
        Args:
            args: Parsed command line arguments
            
        Returns:
            Configured ConfigManager instance
        """
        config = cls()
        
        if args:
            # Update audio config from args
            if hasattr(args, 'empathy'):
                config.audio_config.empathy_level = args.empathy
            if hasattr(args, 'whisper_model'):
                config.audio_config.whisper_model = args.whisper_model
            if hasattr(args, 'test_audio'):
                config.conversation_config.test_audio_on_start = args.test_audio
             
            # Update model config from args
            if hasattr(args, 'model'):
                config.model_config.model_name = args.model
            if hasattr(args, 'ollama_url'):
                config.model_config.ollama_base_url = args.ollama_url
            if hasattr(args, 'language'):
                config.model_config.language = args.language
                config.audio_config.language = args.language
            # Update conversation config from args
            if hasattr(args, 'max_turns'):
                config.conversation_config.max_turns = args.max_turns
        
        return config
    
    def get_audio_config_dict(self) -> Dict[str, Any]:
        """Get audio configuration as dictionary"""
        return {
            'empathy_level': self.audio_config.empathy_level,
            'whisper_model': self.audio_config.whisper_model,
            'language': self.audio_config.language
        }
    
    def get_model_config_dict(self) -> Dict[str, Any]:
        """Get model configuration as dictionary"""

        if self.model_config.language != "en":
            self.model_config.dialogue_prompt_path = f"prompts/{self.model_config.language}/dialogue_prompt.txt"
            self.model_config.confort_prompt_path = f"prompts/{self.model_config.language}/confort_prompt.txt"
        return {
            'model_name': self.model_config.model_name,
            'ollama_base_url': self.model_config.ollama_base_url,
            'dialogue_prompt_path': self.model_config.dialogue_prompt_path,
            'assessment_prompt_path': self.model_config.assessment_prompt_path,
            'triage_prompt_path': self.model_config.triage_prompt_path,
            'confort_prompt_path': self.model_config.confort_prompt_path,
            'language': self.model_config.language
        }
        
    def validate_configuration(self) -> bool:
        """
        Validate the configuration
        
        Returns:
            True if configuration is valid
        """
        # Validate empathy level
        if self.audio_config.empathy_level not in ['low', 'medium', 'high']:
            print(f"ERROR: Invalid empathy level: {self.audio_config.empathy_level}")
            return False
        
        # Validate whisper model
        valid_whisper_models = ['tiny', 'base', 'small', 'medium', 'large']
        if self.audio_config.whisper_model not in valid_whisper_models:
            print(f"ERROR: Invalid whisper model: {self.audio_config.whisper_model}")
            return False
        
        # Validate paths exist (basic check)
        import os
        if not os.path.exists(self.model_config.dialogue_prompt_path):
            print(f"WARNING: Dialogue prompt file not found: {self.model_config.dialogue_prompt_path}")

        if not os.path.exists(self.model_config.assessment_prompt_path):
            print(f"WARNING: Assessment prompt file not found: {self.model_config.assessment_prompt_path}")

        if not os.path.exists(self.model_config.triage_prompt_path):
            print(f"WARNING: Triage prompt file not found: {self.model_config.triage_prompt_path}")

        return True


def setup_argument_parser() -> argparse.ArgumentParser:
    """
    Set up command line argument parser
    
    Returns:
        Configured ArgumentParser
    """
    parser = argparse.ArgumentParser(
        description='Offline Rescue Robot System with Whisper STT',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --empathy high --whisper-model base --test-audio
  python main.py -e low -w tiny --max-turns 15
        """
    )
    
    # Audio configuration
    parser.add_argument(
        '--empathy', '-e', 
        type=str, 
        choices=['low', 'medium', 'high'], 
        default='medium',
        help='Empathy level affecting robot speech speed (default: medium)'
    )

    # Audio configuration
    parser.add_argument(
        '--language', '-l', 
        type=str, 
        choices=['en', 'fr', 'es'], 
        default='en',
        help='Language used in the interaction (default: english)'
    )
    
    parser.add_argument(
        '--whisper-model', '-w',
        type=str,
        choices=['tiny', 'base', 'small', 'medium', 'large'],
        default='base',
        help='Whisper model size - larger = more accurate but slower (default: base)'
    )
    
    parser.add_argument(
        '--test-audio', '-t',
        action='store_true',
        help='Test audio systems before starting conversation'
    )
    
    # Model configuration
    parser.add_argument(
        '--model', '-m',
        type=str,
        choices=['backup','gemma3:4b','gemma:7b','gemma3:12b', 'gpt-oss:7b', 'gpt-oss:13b', 'gpt-oss:20b'],
        default='gemma3:12b',
        help='Ollama model name (default: gemma3:12b)'
    )
    
    parser.add_argument(
        '--ollama-url',
        type=str,
        default=OLLAMA_URL,
        help='Ollama base URL (default: http://localhost:11434)'
    )
    
    # Conversation configuration
    parser.add_argument(
        '--max-turns',
        type=int,
        default=10,
        help='Maximum conversation turns (default: 10)'
    )
    
    parser.add_argument(
        '--dialogue-prompt',
        type=str,
        default='prompts/dialogue_prompt.txt',
        help='Path to dialogue prompt file'
    )
    
    parser.add_argument(
        '--assessment-prompt',
        type=str,
        default='prompts/assessment_prompt.txt',
        help='Path to assessment prompt file'
    )
    
    return parser


def get_situation_context_from_user() -> str:
    """
    Get situation context from user input
    
    Returns:
        Situation context string
    """
    print("\n=== SITUATION CONTEXT SETUP ===")
    print("Please provide context about the disaster situation.")
    print("Examples:")
    print("  • 'Earthquake aftermath in residential area'")
    print("  • 'Forest fire evacuation'") 
    print("  • 'Building collapse rescue'")
    print("  • 'Flood rescue operation'")
    
    context = input("\nEnter situation context: ").strip()
    
    if not context:
        context = "General disaster rescue situation"
        print("Using default context: General disaster rescue situation")
    else:
        print(f"Situation set to: {context}")
    
    return context