FROM python:3.12.0

# Install system dependencies including espeak-ng, audio libraries, and PulseAudio
RUN apt-get update && apt-get install -y \
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
    wget \
    ca-certificates \
    ffmpeg \
    mosquitto \
    mosquitto-clients \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y wget ca-certificates && rm -rf /var/lib/apt/lists/* 
RUN apt-get update && apt-get install -y mosquitto mosquitto-clients

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ]; then PIPER_ARCH="amd64"; \
    elif [ "$ARCH" = "aarch64" ]; then PIPER_ARCH="arm64"; \
    else echo "Unsupported architecture: $ARCH" && exit 1; fi && \
    wget "https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_${PIPER_ARCH}.tar.gz" && \
    tar -xzf "piper_${PIPER_ARCH}.tar.gz" -C /usr/local/bin --strip-components=1 && \
    rm "piper_${PIPER_ARCH}.tar.gz"
    
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

RUN mkdir -p /mosquitto/data /mosquitto/log /mosquitto/config

# Pre-download Whisper model to avoid runtime permission issues
# Define a permanent location for models
ENV WHISPER_CACHE_DIR=/models/whisper
RUN mkdir -p $WHISPER_CACHE_DIR

# Download the model to that specific directory
RUN python -c "import whisper; whisper.load_model('base', download_root='/models/whisper')"

# Ensure permissions are open if you run as user 1000
RUN chmod -R 777 /models/whisper

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
COPY ./config/mosquitto.conf /mosquitto/config/mosquitto.conf

# Create cache directory with proper permissions for any runtime caching
RUN echo 'pcm.!default { type pulse }' > /etc/asound.conf && \
    echo 'ctl.!default { type pulse }' >> /etc/asound.conf
RUN mkdir -p /.cache && chmod -R 777 /.cache
RUN chmod -R 777 /mosquitto

#Coment this 3 lines for two image solution
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
# Chang
CMD ["/entrypoint.sh"]


# Set working directory
WORKDIR /