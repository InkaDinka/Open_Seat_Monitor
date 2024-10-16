Open Seat Monitor is a full-stack web application that monitors classes for open seats and notifies users when a seat is available. The back-end was developed using python and a sqlite3 database while the front-end was developed with HTML/CSS. Using docker, this application used to be hosted on Google Cloud Run but is no longer up due to free-trial time limit. An email with app passwords enabled is needed for full functionality of sending and recieving emails but basic functionality can be seen by running the application with no email environment variables.

In your environment you can run the following docker commands with the environment variable preceding the "docker compose up" command to run the application:

1. docker build -t osm .

2. PORT={port} MASS_EMAIL={optional} EMAIL_PASSWORD={optional} ADMIN_PASSWORD={optional} APP_SECRET={random_secret} docker compose up

   (APP_SECRET can contain any letters or numbers) 
