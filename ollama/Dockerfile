FROM ollama/ollama:latest

# Install curl for health checks (optional but useful)
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Pre-download the model during build
# We start the server in the background, wait, pull, then kill the server
RUN nohup bash -c "ollama serve &" && \
    sleep 5 && \
    ollama pull gemma3:12b && \
    pkill ollama

# Expose Ollama API port
EXPOSE 11434

# Copy the updated startup script
COPY start-ollama.sh /start-ollama.sh
RUN chmod +x /start-ollama.sh

ENTRYPOINT ["/bin/bash", "/start-ollama.sh"]