FROM ollama/ollama:latest

# Expose Ollama API port
EXPOSE 11434

# Copy a startup script that pulls the model
COPY start-ollama.sh /start-ollama.sh
RUN chmod +x /start-ollama.sh

CMD ["/start-ollama.sh"]