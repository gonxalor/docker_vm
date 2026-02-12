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
import shlex
import time
import subprocess


class AudioManager:
    """Manages audio recording, speech-to-text, and text-to-speech functionality"""
    
    def __init__(self, empathy_level: str = "medium", whisper_model: str = "base", language: str = "en",local: bool = True):
        """
        Initialize audio manager with offline capabilities.
        
        Args:
            empathy_level: Level of empathy affecting TTS speed (low, medium, high)
            whisper_model: Whisper model size (tiny, base, small, medium, large)
        """
        self.empathy_level = empathy_level
        self.language = language
        self.local = local
        
        #self.microphone = "http://media01.carma:8889/ugv/a31de2dd-0adc-48d1-b562-9715ae7b633e/mic"
        #self.speaker = "http://media01.carma:8889/ugv/a31de2dd-0adc-48d1-b562-9715ae7b633e/speaker"
        
        #Optional links, just testing
        self.microphone = "rtsp://media01.carma:8554/ugv/a31de2dd-0adc-48d1-b562-9715ae7b633e/mic"
        self.speaker = "rtsp://media01.carma:8554/ugv/a31de2dd-0adc-48d1-b562-9715ae7b633e/speaker"


        device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # Load Whisper model
        print(f"Loading Whisper model '{whisper_model}' on {device.upper()} for offline speech recognition...")
        if self.local:
            self.whisper_model = whisper.load_model(whisper_model, device=device)
        else:
            self.whisper_model = whisper.load_model(whisper_model,download_root="/models/whisper", device=device)
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
        
        if self.local:
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
        else:
            print(f"Connecting to stream: {self.microphone}")
        
            command = [
                'ffmpeg',
                '-nostdin',                 # Prevents FFmpeg from trying to read terminal input
                '-rtsp_transport', 'tcp', 
                '-i', self.microphone,      # Use the direct IP URL
                '-t', str(duration),
                '-f', 's16le',
                '-acodec', 'pcm_s16le',
                '-ar', '16000',
                '-ac', '1',
                '-'
            ]
                        
            try:
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                raw_audio, error = process.communicate()
                
                #if process.returncode != 0:
                 #   print(f"STREAM ERROR: Could not connect to {self.microphone}")
                  #  print(f"FFmpeg says: {error.decode()}")
                   # return np.array([])
                
                if not raw_audio:
                    print(f"STDOUT: {raw_audio}")
                    print(f"STREAM ERROR: Could not connect to {self.microphone}")
                    return np.array([])

                # Convert to numpy for Whisper
                print("No problem what so ever")
                audio_np = np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32) / 32768.0
                return audio_np
            except Exception as e:
                print(f"Streaming record error: {e}")
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
    
    def _get_persistent_ffmpeg(self):
        """Checks if the RTSP stream is alive; if not, starts it."""
        if not hasattr(self, 'rtsp_process') or self.rtsp_process.poll() is not None:
            print(f"Opening persistent stream to {self.speaker}...")
            # We use pipe:0 (stdin) so we can push audio data manually
            command = [
                'ffmpeg', '-loglevel', 'error', '-re',
                '-f', 's16le', '-ar', '22050', '-ac', '1', '-i', 'pipe:0',
                '-rtsp_transport', 'tcp',
                '-c:a', 'libopus', '-b:a', '32k', '-application', 'lowdelay',
                '-f', 'rtsp', self.speaker
            ]
            self.rtsp_process = subprocess.Popen(command, stdin=subprocess.PIPE)
        return self.rtsp_process
    
    def text_to_speech(self, text: str, blocking: bool = True):
        # Ensure text is not empty
        if not text or not text.strip():
            return

        # Map the language codes to the actual filenames
        voice_map = {
            "en": "en_US-lessac-medium.onnx",
            "es": "es_ES-sharvard-medium.onnx",
            "fr": "fr_FR-siwis-medium.onnx"
        }
        
        model_file = voice_map.get(self.language, "en_US-lessac-medium.onnx")
        model_path = f"/models/{model_file}"
        safe_text = text.replace('"', '\\"')
        
        if self.local:
            # We use aplay to play the raw audio stream coming out of Piper
            # -r 22050 is required for 'medium' models.
            # Note: Using double quotes around text to handle single quotes in speech
            command = f'echo "{safe_text}" | piper --model {model_path} --output-raw | aplay -r 22050 -f S16_LE -t raw -'
            command = (
            f'echo {safe_text} | piper --model {model_path} --output-raw | '
            f'ffmpeg -f s16le -ar 22050 -ac 1 -i - '
            f'-c:a libopus -b:a 32k -application lowdelay '  # <--- Add Opus encoding
            f'-f rtsp {self.speaker}' 
            )
            try:
                if blocking:
                    subprocess.run(command, shell=True, check=True)
                else:
                    subprocess.Popen(command, shell=True)
            except Exception as e:
                print(f"Offline TTS Error: {e}")
                print(f"Robot says: {text}")
        else:
            try:
                piper_proc = subprocess.Popen(
                    ['piper', '--model', model_path, '--output-raw'],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                audio_bytes, _ = piper_proc.communicate(input=text.encode('utf-8'))

                if audio_bytes:
                    # 2. Get our long-running ffmpeg process
                    rtsp_pipe = self._get_persistent_ffmpeg()
                    
                    # 3. Write the bytes to the server stream
                    rtsp_pipe.stdin.write(audio_bytes)
                    rtsp_pipe.stdin.flush()
                    
                    print(f"Sent {len(audio_bytes)} bytes to RTSP stream.")

                    
                    # Approximate duration (2 bytes per sample @ 22050Hz)
                    duration = (len(audio_bytes) / 2) / 22050
                    time.sleep(duration)

            except Exception as e:
                print(f"TTS Error: {e}")
            
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
