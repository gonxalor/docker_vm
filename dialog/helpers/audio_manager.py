"""
Audio Manager Module
Handles all audio-related functionality including TTS and STT
"""
import numpy as np
import pyaudio
import whisper
import platform
import pyttsx3
import threading
import torch


class AudioManager:
    """Manages audio recording, speech-to-text, and text-to-speech functionality"""
    
    def __init__(self, empathy_level: str = "medium", whisper_model: str = "base", language: str = "en"):
        """
        Initialize audio manager with offline capabilities.
        
        Args:
            empathy_level: Level of empathy affecting TTS speed (low, medium, high)
            whisper_model: Whisper model size (tiny, base, small, medium, large)
        """
        self.empathy_level = empathy_level
        self.language = language

        device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # Load Whisper model
        print(f"Loading Whisper model '{whisper_model}' on {device.upper()} for offline speech recognition...")
        self.whisper_model = whisper.load_model(whisper_model, device=device)
        print("Whisper model loaded successfully")
        
        # Initialize text-to-speech
        self.tts_engine = pyttsx3.init(driverName='espeak')
        self.setup_tts_voice()
        
        # Initialize audio recording
        self.setup_audio_recording()
    
    def setup_tts_voice(self):
        """
        Configures TTS voice for both Windows and Linux
        """
        system = platform.system()
        voices = self.tts_engine.getProperty('voices')
        
        if system == 'Windows':
            print("Running on Windows - Using SAPI5 voices")
            # Your existing Windows voice selection code
            if self.language == 'es':
                target_codes = ['es-es', 'es-la', 'es-mx', 'spanish']
            elif self.language == 'fr':
                target_codes = ['fr-fr', 'fr-ca', 'fr-be', 'fr-ch', 'french']
            elif self.language == 'en':
                target_codes = ['en-us', 'en-gb', 'en-in', 'english']
            else:
                target_codes = []    

        elif system == 'Linux':
            print("Running on Linux - Using espeak-ng voices")
            # Simpler espeak voice selection
            if self.language == 'es':
                target_codes = ['spanish', 'es']
            elif self.language == 'fr':
                target_codes = ['french', 'fr']
            elif self.language == 'en':
                target_codes = ['english', 'en']
            else:
                target_codes = []
                
            # espeak voices have different naming
            for voice in voices:
                if any(code in voice.name.lower() for code in target_codes):
                    self.tts_engine.setProperty('voice', voice.id)
                    print(f"Selected espeak voice: {voice.name}")
                    break
        
        # Set rate and volume (works on both)
        rate_mapping = {"low": 220, "medium": 200, "high": 180}
        rate = rate_mapping.get(self.empathy_level, 200)
        self.tts_engine.setProperty('rate', rate)
        self.tts_engine.setProperty('volume', 0.9)

    def setup_audio_recording(self):
        """Configure audio recording settings for Whisper"""
        self.sample_rate = 16000
        self.chunk_size = 1024
        self.audio_format = pyaudio.paInt16
        self.channels = 1
        
        self.audio = pyaudio.PyAudio()
        print("Audio recording configured for Whisper (16kHz, mono)")
    
    def record_audio(self, duration: int = 10, silence_threshold: float = 0.01,
                    silence_duration: float = 2.0) -> np.ndarray:
        """
        Record audio with automatic silence detection
        
        Args:
            duration: Maximum recording duration in seconds
            silence_threshold: RMS threshold for silence detection
            silence_duration: Seconds of silence before stopping
            
        Returns:
            Audio data as numpy array
        """
        print("Recording audio... (speak now)")
        
        stream = self.audio.open(
            format=self.audio_format,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size
        )
        
        frames = []
        silence_frames = 0
        silence_threshold_frames = int(silence_duration * self.sample_rate / self.chunk_size)
        max_frames = int(duration * self.sample_rate / self.chunk_size)
        
        try:
            for i in range(max_frames):
                try:
                    data = stream.read(self.chunk_size, exception_on_overflow=False)
                    frames.append(data)
                    
                    audio_data = np.frombuffer(data, dtype=np.int16)
                    
                    if len(audio_data) == 0:
                        rms = 0.0
                    else:
                        audio_float = audio_data.astype(np.float32)
                        mean_square = np.mean(np.square(audio_float))
                        
                        rms = np.sqrt(mean_square) if np.isfinite(mean_square) and mean_square >= 0 else 0.0
                        rms = rms / 32767.0
                    
                    if rms < silence_threshold:
                        silence_frames += 1
                        if silence_frames >= silence_threshold_frames and len(frames) > 10:
                            print("Silence detected, stopping recording")
                            break
                    else:
                        silence_frames = 0
                        
                except Exception as chunk_error:
                    print(f"WARNING: Audio chunk error: {chunk_error}")
                    continue
                    
        except Exception as e:
            print(f"WARNING: Recording error: {e}")
        finally:
            stream.stop_stream()
            stream.close()
        
        if not frames:
            print("No audio data recorded")
            return np.array([])
        
        try:
            audio_data = b''.join(frames)
            if len(audio_data) == 0:
                return np.array([])
                
            audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            
            if not np.isfinite(audio_np).all():
                print("WARNING: Audio contains invalid values, cleaning...")
                audio_np = np.nan_to_num(audio_np, nan=0.0, posinf=0.0, neginf=0.0)

            print(f"Recorded {len(audio_np)/self.sample_rate:.1f} seconds of audio")
            return audio_np
            
        except Exception as conversion_error:
            print(f"Audio conversion error: {conversion_error}")
            return np.array([])
    
    def whisper_speech_to_text(self, audio_data: np.ndarray, language: str = "en") -> str:
        """
        Convert speech to text using Whisper (offline)
        
        Args:
            audio_data: Audio data as numpy array
            language: Language code (en, es, pt, etc.)
            
        Returns:
            Transcribed text
        """
        if len(audio_data) == 0:
            return ""
        
        try:
            print("Processing speech with Whisper...")

            result = self.whisper_model.transcribe(
                audio_data,
                language=language,
                fp16=False,
                verbose=False
            )
            
            text = str(result.get("text", "")).strip()
            
            if text:
                print(f"Whisper transcription: '{text}'")
                return text
            else:
                print("Whisper: No speech detected")
                return ""
                
        except Exception as e:
            print(f"Whisper error: {e}")
            return ""
    
    def speech_to_text(self, max_duration: int = 10, retries: int = 1) -> str:
        """
        Convert speech to text using Whisper with retry mechanism
        
        Args:
            max_duration: Maximum recording duration
            retries: Number of retry attempts if Whisper fails
            
        Returns:
            Transcribed text
        """
        attempt = 0
        while attempt <= retries:
            audio_data = self.record_audio(duration=max_duration)
            
            if len(audio_data) > 0:
                text = self.whisper_speech_to_text(audio_data,language=self.language)
                if text:
                    return text
            
            attempt += 1
            if attempt <= retries:
                print(f"Retrying Whisper STT (attempt {attempt}/{retries})...")
        
        print("Whisper failed after retries")
        return ""
    
    def text_to_speech(self, text: str, blocking: bool = True):
        """
        Convert text to speech using offline TTS
        
        Args:
            text: Text to convert to speech
            blocking: Whether to wait for speech to complete
        """
        try:
            if blocking:
                self.tts_engine.say(text)
                self.tts_engine.runAndWait()
            else:
                def speak_async():
                    self.tts_engine.say(text)
                    self.tts_engine.runAndWait()
                
                speech_thread = threading.Thread(target=speak_async)
                speech_thread.daemon = True
                speech_thread.start()
    
            
        except Exception as e:
            print(f"TTS Error: {e}")
            print(f"Robot says (text only): {text}")

    def test_audio_systems(self):
        """Test both TTS and STT systems offline"""
        print("\n=== TESTING OFFLINE AUDIO SYSTEMS ===")
        
        # Test TTS
        print("Testing Text-to-Speech...")
        test_message = "Hello, this is a test of the robot's offline speech system. Can you hear me clearly?"
        self.text_to_speech(test_message)
        
        # Test Whisper STT
        print("\nTesting Whisper Speech-to-Text...")
        print("Please say: 'This is a test of offline speech recognition'")
        result = self.speech_to_text(max_duration=8)
        
        if result:
            print(f"Whisper STT Test successful! Heard: '{result}'")
        else:
            print("STT Test failed - no speech detected")
  
        input("\nPress Enter to continue with the rescue dialogue...")
    
    def cleanup(self):
        """Clean up audio resources"""
        if hasattr(self, 'audio'):
            self.audio.terminate()
