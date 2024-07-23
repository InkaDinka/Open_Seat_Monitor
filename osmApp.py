import time
import smtplib
import os
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from dotenv import load_dotenv
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from flask import Flask, render_template, request, Response
from flask_sqlalchemy import SQLAlchemy
import os
import requests

app = Flask(__name__)

#Creates a instance of the database in the working directory.
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.sqlite3'
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

#Class for creating a new user.
class User(db.Model):
#Creates columns in database for each attribute.

#Unique id for each user
    _id = db.Column("id", db.Integer, primary_key=True)
#Class and user information
    classNum = db.Column(db.Integer)
    email = db.Column(db.String(100))
    initialSeats = db.Column(db.Integer, nullable=True, default=None)
    term = db.Column(db.String(20))

#Constructor do build objects with passed parameters.
    def __init__(self, classNum, email, initialSeats, term):
        self.classNum = classNum
        self.email = email
        self.initialSeats = initialSeats
        self.term = term


def monitor(driver):
    #Function that takes a chrome driver and form submission info from sqlite database for unique class search link for monitoring.
    def get_page_content(classNum, term, driver):

        url = f'https://catalog.apps.asu.edu/catalog/classes/classlist?advanced=true&campusOrOnlineSelection=A&classNbr={classNum}&honors=F&promod=F&searchType=all&term={term}'
        
        driver.get(url)

        element = 0
        #Stores all 6 text-nowrap tags on the site in a list.
        while element < 6:
            for trial in range(200):
                try:
                    wait = WebDriverWait(driver, 30)
                    elements = wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, 'text-nowrap')))
                    element += 1
                except:
                    time.sleep(1)

        word = ""
        open_seats = None

        #Searches for the tag containing the open seat information.
        for element in elements:
            data = element.text.strip() 
            if ' of ' in data:  
                #If text-nowrap tag with open seat information is found build a string of the open seat number until a space is reached which will result in a ValueError.
                for character in data:
                    try:
                        number = int(character)
                        word += str(number)
                    except ValueError:
                        break 
                open_seats = int(word)
        #Scans for bold-hypherlink tag to find class name
        waits = WebDriverWait(driver, 30)
        span_elements = waits.until(EC.presence_of_all_elements_located((By.CLASS_NAME, 'bold-hyperlink')))
        class_name = span_elements[2].text

        if open_seats != None and class_name != None:
            return open_seats, class_name
        else:
            return None, None

    load_dotenv()

    #Monitoring loop

    #Current context of webpage and contents in database.
    with app.app_context():
        session = db.session()
        term_dict = {
            "Fall 2024": 2247,
            "Spring 2025": 2251,
            "Summer 2025": 2254,
            "Fall 2025": 2257,
            "Spring 2026": 2261,
            "Summer 2026": 2263,
            "Fall 2026": 2267,
        }
        try:
            #Collects all users in the database in a list
            full_users = User.query.all()
        except Exception as e:
            print(f"An error occurred: {e}")
            import traceback
            traceback.print_exc()
        #Each users' class will be scraped for the open seats using get_page_content which passes the inputted class information from the database.
        for user in full_users:
            receiver_email = user.email
            classNum = int(user.classNum)
            if user.initialSeats == None:
                #Grabs initial seats to monitor.
                user.initialSeats, _ = get_page_content(classNum, term_dict.get(user.term), driver)
                #Commits initial seats to databasae.
                session.commit()

            #Searches current seats that will be compared to the inital seats of current user.
            current_seats, class_name = get_page_content(classNum, term_dict.get(user.term), driver)

            if current_seats == None or class_name == None:
                print(f"Class {user.classNum} not found\n")
                continue

            # print(f"Class Name: {class_name}   -   Email: {user.email}   -   Class Number: {user.classNum}   -   Initial Seats: {user.initialSeats}   -   Term: {user.term}\n")

            #Checks for changes in the seats available and if there's a change an email is sent.
            if int(current_seats) != int(user.initialSeats):

                #Email credentials are fetched from github repository secrets.
                sender_email = os.getenv('MASS_EMAIL')
                password = os.getenv('EMAIL_PASSWORD')

                message = MIMEMultipart()
                message['From'] = sender_email
                message['To'] = receiver_email
                message['Subject'] = f'Seat(s) Available: {class_name}'

                body = f'\nNumber of seats available: {current_seats}'
                message.attach(MIMEText(body, 'plain'))

                try:
                #587 is the port number for the SMTP (Simple Mail Transfer Protocol) server.
                    with smtplib.SMTP('smtp.gmail.com', 587) as server:  
                        server.starttls()
                        server.login(sender_email, password)
                        server.sendmail(sender_email, receiver_email, message.as_string())
                        initial_seats = current_seats

                except Exception as e:
                    print(f'Failed to send email: {e}')
                    time.sleep(15)
                #Updates the initial seats to current seats in the database.
                user.initialSeats = int(current_seats)


        #Changes will be applied to the database.
        session.commit()
        session.close()
        #Decreases CPU usage from APScheduler
        time.sleep(1)

#Options that are needed to hide third-party cookie log messages and to use the chrome driver in tabless.
chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--log-level=3')

driver = webdriver.Chrome(options=chrome_options)

scheduler = BackgroundScheduler()
scheduler.add_job(monitor, 'interval', seconds=30, args=[driver])
scheduler.start()

#Root route that gets information from the submitted form and creates new users in the sql database.
@app.route('/', methods=['GET', 'POST'])
def webpage():

    if request.method == 'POST':

#Fetches class and email info from the form submission
        classNum = request.form["Class Number"]
        email = request.form["email"]
        term = request.form.get("term_select")

        if email and classNum:
            if 'submit' in request.form:
                new_user = User(email=email, classNum=classNum, term=term, initialSeats=None)
                db.session.add(new_user)
                db.session.commit()
            elif 'remove' in request.form:
#Filters database to find the first user that matches submitted email and class number and deletes that user from the database.
                user = User.query.filter_by(email=email, classNum=classNum).first()
                if user:
                    db.session.delete(user)
                    db.session.commit()
#Responds with the same html containing the form for more user submissions.
    return render_template('index.html')

#Route to view users and classes being monitored        
@app.route('/users', methods=['GET'])
def get_current_courses():
 
    users = User.query.all()

#Sets table colors and table headers.
    table = """
    <table bgcolor="grey" width="1000"; border-collapse: collapse;" align="center" >
        <thead>
            <tr bgcolor="lightgrey" align="center">
                <th>Email</th>
                <th>Class Number</th>
                <th>Initial Seats</th>
                <th>Term</th>
            </tr>
        </thead>
        <tbody>
    """

#Add table rows for each user to display
    for user in users:
        table += f"""
        <tr bgcolor="lightblue" align="center">
            <td>{user.email}</td>
            <td>{user.classNum}</td>
            <td>{user.initialSeats}</td>
            <td>{user.term}</td>
        </tr>
        """

#Once all users are added close table body and table tags
    table += """
        </tbody>
    </table>
    """
    return Response(table, content_type='text/html')

if __name__ == '__main__':
#Creates instance of database in current flask context. 
    with app.app_context():
        db.create_all()
#Set debug to true so server doesn't need to be executed with every change.
    try:
        app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
    except(KeyboardInterrupt, SystemExit):
        driver.quit()
        scheduler.shutdown()
