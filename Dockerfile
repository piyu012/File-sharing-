FROM python:3.10-slim

WORKDIR /app

# System updates + supervisor
RUN apt-get update && apt-get install -y supervisor && apt-get clean

COPY requirements.txt requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .

# Add supervisor config
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

CMD ["/usr/bin/supervisord"]
