# Use an official Python image as the base image
FROM python:3.9-slim

# Set the working directory inside the container
WORKDIR /app

# Install cron
RUN apt-get update && apt-get install -y --no-install-recommends cron \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Cron daemon runs jobs with a stripped env. The entrypoint snapshots the
# container's env to /container.env, and the cron line sources it.
RUN printf '0 14 * * * root . /container.env && /usr/local/bin/python /app/run.py >> /var/log/cron.log 2>&1\n' > /etc/cron.d/pmp-checker \
    && chmod 0644 /etc/cron.d/pmp-checker \
    && touch /var/log/cron.log

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["cron", "-f"]
