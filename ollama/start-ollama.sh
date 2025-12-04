#!/bin/bash

# Start Ollama in the background
/bin/ollama serve &

# Wait for Ollama to be ready
sleep 5

# Pull the llama 3.1 8B model
ollama pull llama3.1:8b

# Keep the container running
wait