#!/bin/bash
set -e

echo "Starting Ollama server..."
# Start Ollama in the background
/bin/ollama serve &

# Wait for Ollama to be ready
echo "Waiting for Ollama server to start..."
sleep 10

# Check if server is ready
until curl -s http://localhost:11434/api/tags > /dev/null 2>&1; do
    echo "Waiting for Ollama API to be ready..."
    sleep 2
done

echo "Ollama server is ready!"

# Pull the gemma2:2b model (change to your preferred model)
#echo "Pulling llama3.1:8b model..."
echo "Pulling gemma3:12b model..."
#ollama pull llama3.1:8b
ollama pull gemma3:12b

echo "Model downloaded successfully!"
ollama list

# Keep container running by waiting for the ollama serve process
wait