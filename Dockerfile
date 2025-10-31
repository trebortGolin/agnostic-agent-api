# Step 1: Base Image
# We use a lightweight Python 3.11-slim image for production.
FROM python:3.11-slim

# Step 2: Set the working directory
# This is where our code will live inside the container.
WORKDIR /app

# Step 3: Copy and install dependencies
# We copy requirements.txt first to optimize Docker's layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Step 4: Copy the application code
# Copy agent_client.py, orchestrator.py, etc. into the container.
COPY . .

# Step 5: Define Flask environment variables
# Tells Flask which app to run and to run in production mode (not debug).
ENV FLASK_APP=orchestrator.py
ENV FLASK_ENV=production

# Step 6: Expose the port
# Informs Docker that our Flask application listens on port 5000.
EXPOSE 5000

# Step 7: Run command
# The command to start the Flask server for production.
# We use "--host=0.0.0.0" to make it accessible from outside the container.
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]

