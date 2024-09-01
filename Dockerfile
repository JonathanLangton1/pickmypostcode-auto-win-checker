# Use an official Python image as the base image
FROM python:3.9-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements.txt file and install dependencies
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Install cron (if you plan to run this as a cron job inside the container)
RUN apt-get update && apt-get install -y cron

# Add the cron job to the crontab (optional, only if needed for automated runs)
# Example cron job to run your script at 14:00 every day
RUN echo "0 14 * * * /usr/local/bin/python /app/run.py >> /var/log/cron.log 2>&1" >> /etc/cron.d/mycron

# Give execution rights on the cron job
RUN chmod 0644 /etc/cron.d/mycron

# Apply cron job (optional)
RUN crontab /etc/cron.d/mycron

# Create the log file to be able to run tail (optional)
RUN touch /var/log/cron.log

# Start the cron service and keep the container running
CMD ["cron", "-f"]