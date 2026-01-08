FROM python:3.12.0

# Install system dependencies including espeak-ng, audio libraries, and PulseAudio
RUN apt-get update -o Acquire::Check-Valid-Until=false && apt-get install -y \
    gcc \
    espeak-ng \
    espeak-ng-data \
    libespeak-ng1 \
    alsa-utils \
    portaudio19-dev \
    pulseaudio-utils \
    libpulse0 \
    libpulse-dev \
    libasound2-plugins \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y wget ca-certificates && rm -rf /var/lib/apt/lists/*    

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# 1. Install Piper TTS (Corrected Link)
RUN wget https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_amd64.tar.gz && \
    tar -xzf piper_amd64.tar.gz -C /usr/local/bin --strip-components=1 && \
    rm piper_amd64.tar.gz

# 2. Download high-quality models for Offline use (English, Spanish, French)
RUN mkdir -p /models && \
    # English (Lessac Medium)
    wget -O /models/en_US-lessac-medium.onnx https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx && \
    wget -O /models/en_US-lessac-medium.onnx.json https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json && \
    # Spanish (Sharvard Medium)
    wget -O /models/es_ES-sharvard-medium.onnx https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_ES/sharvard/medium/es_ES-sharvard-medium.onnx && \
    wget -O /models/es_ES-sharvard-medium.onnx.json https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_ES/sharvard/medium/es_ES-sharvard-medium.onnx.json && \
    # French (Siwis Medium)
    wget -O /models/fr_FR-siwis-medium.onnx https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx && \
    wget -O /models/fr_FR-siwis-medium.onnx.json https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx.json

# ... (Keep the rest of your Dockerfile) ...

# Pre-download Whisper model to avoid runtime permission issues
RUN python -c "import whisper; whisper.load_model('base')"

# Copy all project files and directories
COPY agents/ ./agents/
COPY backup_questions/ ./backup_questions/
COPY data/ ./data/
COPY helpers/ ./helpers/
COPY prompts/ ./prompts/
COPY config/ ./config/
COPY dialog_manager.py .
COPY text2speech2text.py .
COPY asound.conf /etc/asound.conf

# Create cache directory with proper permissions for any runtime caching
RUN echo 'pcm.!default { type pulse }' > /etc/asound.conf && \
    echo 'ctl.!default { type pulse }' >> /etc/asound.conf
RUN mkdir -p /.cache && chmod -R 777 /.cache


# Set working directory
WORKDIR /