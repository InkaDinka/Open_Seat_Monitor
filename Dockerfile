#Declares language version
FROM python:3.12

#Logs outputs. Useful for debugging
ENV PYTHONUNBUFFERED 1

#Avoids creation of .pyc files to filesystem.
ENV PYTHONDONTWRITEBYTECODE 1

#Run commands needed to create chrome instances so chrome.exe is not needed in working directory. 
RUN apt-get update

RUN apt-get update && apt-get install -y libsdl2-dev

RUN apt-get install -y chromium

RUN apt-get install -y chromium-driver

#Sets path of container to host the other commands.
WORKDIR /app

#Copies dependencies to /app/requirements.txt path
COPY requirements.txt requirements.txt

#Installs dependencies in container.
RUN pip install -r requirements.txt

#Copies all files in the current directory to the working directory of the container.
COPY . .
