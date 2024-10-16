Open Seat Monitor is a full-stack web application that monitors classes for open seats and notifies users when a seat is available. The back-end was developed using python and a sqlite3 database while the front-end was developed with HTML/CSS. Using docker, this application used to be hosted on Google Cloud Run but is no longer up due to free-trial time limit. If you would like to run this yourself you'll need to create a .env file with the following:

1. An email where App Passwords are enabled
2. The App Password
3. A random password for the App Secret used for the Flask Server
4. Port number
