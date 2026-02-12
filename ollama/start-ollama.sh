#!/bin/bash
set -e

echo "Starting Ollama server..."
# Start Ollama in the background
/bin/ollama serve &

# Wait for Ollama to be ready
echo "Waiting for Ollama API to be ready..."
until curl -s http://localhost:11434/api/tags > /dev/null 2>&1; do
    sleep 2
done

echo "Ollama server is ready!"
echo "Available models in this image:"
ollama list

# Keep container running
wait