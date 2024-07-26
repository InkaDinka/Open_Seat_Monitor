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
import re

app = Flask(__name__)

#Creates a instance of the database in the working directory.
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.sqlite3'
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

load_dotenv()

#Association table for when a single email has multiple classes.
association_table = db.Table('user_class', 
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('class_id', db.Integer, db.ForeignKey('classes.id'), primary_key=True)
)

#Class for creating a new user.
class User(db.Model):
    __tablename__ = 'users'
    #Unique id for each user
    id = db.Column("id", db.Integer, primary_key=True)
    
    #Class and user information
    email = db.Column(db.String(100), unique=True, nullable=False)
    classes = db.relationship('Class', secondary=association_table, backref=db.backref('users', lazy='dynamic'))

class Class(db.Model):
    __tablename__ = 'classes'
    id = db.Column("id", db.Integer, primary_key=True)
    classNum = db.Column(db.Integer)
    initialSeats = db.Column(db.Integer, nullable=True, default=None)
    term = db.Column(db.String(20))

def monitor(driver):
    #Function that takes a chrome driver and form submission info from sqlite database for unique class search link for monitoring.
    def get_page_content(classNum, term, driver):

        url = f'https://catalog.apps.asu.edu/catalog/classes/classlist?advanced=true&campusOrOnlineSelection=A&classNbr={classNum}&honors=F&promod=F&searchType=all&term={term}'

        driver.get(url)

        open_seats = None
        
        try:
            # Gives driver wait time for elements on webpage to be found and for page to load
            driver.implicitly_wait(1)
            
            #Finds elements under a tree of html tags and puts all elements under that tree in a list
            elements = driver.find_elements(By.XPATH, f"/html/body/div[2]/div[2]/div[2]/div/div/div[5]/div/div/div/div[2]")

        except:
            open_seats = None

        #Filters the elements list for the open_seats. Ex) 8 of 54 - returns 8
        if elements:
            for ele in elements:
                data = ele.text.strip()
                seat_element = re.findall(r'(\d+ of \d+)', data)
                print(seat_element[0])
                if data:
                    open_seats = int(str(seat_element[0])[0:seat_element[0].find(" ")])

        try:
            #Scans for bold-hypherlink tag to find class name
            waits = WebDriverWait(driver, 30)
            span_elements = waits.until(EC.presence_of_all_elements_located((By.CLASS_NAME, 'bold-hyperlink')))
            class_name = span_elements[2].text

        except Exception as e:
            print(f"Retrying... {e}")
            import traceback
            traceback.print_exc()
            time.sleep(1)
            

        if open_seats != None and class_name != None:
            
            return open_seats, class_name
        else:
            return None, None

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
            classes = Class.query.all()
        except Exception as e:
            print(f"An error occurred: {e}")
            import traceback
            traceback.print_exc()
        #Each users' class will be scraped for the open seats using get_page_content which passes the inputted class information from the database.
        for cls in classes:
            receiver_emails = [user.email for user in cls.users]
            classNum = int(cls.classNum)
            if cls.initialSeats == None:
                #Grabs initial seats to monitor.
                cls.initialSeats, _ = get_page_content(classNum, term_dict.get(cls.term), driver)
                #Commits initial seats to databasae.
                session.commit()

            #Searches current seats that will be compared to the inital seats of current user.
            current_seats, class_name = get_page_content(classNum, term_dict.get(cls.term), driver)

            if current_seats == None or class_name == None:
                print(f"Class {cls.classNum} not found\n")
                continue

            # print(f"Class Name: {class_name}   -   Email: {user.email}   -   Class Number: {user.classNum}   -   Initial Seats: {user.initialSeats}   -   Term: {user.term}\n")

            #Checks for changes in the seats available and if there's a change an email is sent.
            if int(current_seats) != int(cls.initialSeats):
                email_users(receiver_emails, class_name, current_seats)
                #Updates the initial seats to current seats in the database.
                cls.initialSeats = int(current_seats)

        #Changes will be applied to the database.
        session.commit()
        session.close()
        #Decreases CPU usage from APScheduler
        time.sleep(1)


def email_users(reciever_emails, class_name, current_seats):
    with app.app_context():
        for receiver_email in reciever_emails:
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
                time.sleep(2)

#Options that are needed to hide third-party cookie log messages and to use the chrome driver in tabless.
chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--log-level=3')

driver = webdriver.Chrome(options=chrome_options)

scheduler = BackgroundScheduler()
scheduler.add_job(monitor, 'interval', seconds=10, args=[driver])
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
                #[user.email for user in cls.users]
                user = User.query.filter_by(email=email).first()
            
                # If the user does not exist, create a new user
                if not user:
                    user = User(email=email)
                    db.session.add(user)

                # Check if the class exists
                cls = Class.query.filter_by(classNum=classNum).first()
                
                # If the class does not exist, create a new class
                if not cls:
                    cls = Class(classNum=classNum, term=term, initialSeats=None)
                    db.session.add(cls)

                # Add the class to the user if not already added
                if cls not in user.classes:
                    user.classes.append(cls)

                # Commit the changes
                db.session.commit()

            elif 'remove' in request.form:
                #Filters database to find the first user that matches submitted email and class number and deletes that user from the database.
                user = User.query.filter_by(email=email).first()
                if user:
                    # Remove all classes associated with this user
                    user.classes = []
                    db.session.delete(user)
                    db.session.commit()
    #Responds with the same html containing the form for more user submissions.
    return render_template('index.html')

#Route to view users and classes being monitored        
@app.route('/users', methods=['GET'])
def get_users():
    users = User.query.all()
    classes = Class.query.all()

    table = """
    <table bgcolor="grey" width="1000"; border-collapse: collapse;" align="center" >
        <thead>
            <tr bgcolor="lightgrey" align="center">
                <th>Email</th>
                <th>Class Number</th>
            </tr>
        </thead>
        <tbody>
    """

    for user in users:
        classNum = ', '.join(str(cls.classNum) for cls in user.classes)
        table += f"""
        <tr bgcolor="lightblue" align="center">
            <td>{user.email}</td>
            <td>{classNum}</td>
        </tr>
        """
#Once all users are added close table body and table tags
    table += """
        </tbody>
    </table>
    """

    table += """
    <table bgcolor="grey" width="1000"; border-collapse: collapse;" align="center" >
        <thead>
            <tr bgcolor="lightgrey" align="center">
                <th>Class Number</th>
                <th>Initial Seats</th>
                <th>Associated Emails</th>
                <th>Term</th>
            </tr>
        </thead>
        <tbody>
    """

    for cls in classes:
        associated_emails = cls.users.count()
        table += f"""
        <br><tr bgcolor="lightblue" align="center">
            <td>{cls.classNum}</td>
            <td>{cls.initialSeats}</td>
            <td>{associated_emails}</td>
            <td>{cls.term}</td>
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
        db.drop_all()
        db.create_all()
    #Set debug to true so server doesn't need to be executed with every change.
    try:
        app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
    except(KeyboardInterrupt, SystemExit):
        driver.quit()
        scheduler.shutdown()
