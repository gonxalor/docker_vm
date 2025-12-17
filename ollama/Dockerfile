FROM ollama/ollama:latest

# Install curl for health checks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Expose Ollama API port
EXPOSE 11434

# Copy startup script
COPY start-ollama.sh /start-ollama.sh
RUN chmod +x /start-ollama.sh

# Use bash to execute the script
ENTRYPOINT ["/bin/bash", "/start-ollama.sh"]