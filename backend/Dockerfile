# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source code and data into the container
COPY src/ ./src/
COPY llm_fantasy_data.db .
COPY data/ ./data/

# Make port 8000 available to the world outside this container
EXPOSE 8000

# Run the main API
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
