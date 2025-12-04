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
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

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

# Create cache directory with proper permissions for any runtime caching
RUN mkdir -p /.cache && chmod -R 777 /.cache

# Set working directory
WORKDIR /