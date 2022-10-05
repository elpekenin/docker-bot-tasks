FROM python:3.10.6
SHELL ["/bin/bash", "-c"]

MAINTAINER Pablo (elpekenin) Martinez Bernal "martinezbernalpablo@gmail.com"

# Download all files
WORKDIR /app
RUN git clone https://github.com/elpekenin/docker-bot-tasks && shopt -s dotglob && mv -v docker-bot-tasks/* .

# Install dependencies
RUN pip3 install -r requirements.txt

ENTRYPOINT ["python3", "main.py"]
