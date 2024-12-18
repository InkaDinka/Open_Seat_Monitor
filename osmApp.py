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
from flask import Flask, render_template, request, Response, redirect, url_for, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
import os
import re
# import chromedriver_binary  # Adds chromedriver binary to path

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('APP_SECRET')

#Creates a instance of the database in the working directory.
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.sqlite3'
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

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
    password = db.Column(db.String(200), nullable=False)
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
            driver.implicitly_wait(10)
            
            #Finds elements under a tree of html tags and puts all elements under that tree in a list
            elements = driver.find_elements(By.XPATH, f"/html/body/div[2]/div[2]/div[2]/div/div/div[5]/div/div/div/div[2]")

        except:
            open_seats = None

        #Filters the elements list for the open_seats. Ex) 8 of 54 - returns 8
        if elements:
            for ele in elements:
                data = ele.text.strip()
                seat_element = re.findall(r'(\d+ of \d+)', data)

                if data:
                    open_seats = int(str(seat_element[0])[0:seat_element[0].find(" ")])

        try:
            #Scans for bold-hypherlink tag to find class name
            waits = WebDriverWait(driver, 30)
            span_elements = waits.until(EC.presence_of_all_elements_located((By.CLASS_NAME, 'bold-hyperlink')))
            class_name = ""
            for i in range(len(span_elements) - 1):
                if span_elements[i].text != "":
                    class_name = span_elements[i].text + " " + span_elements[i + 1].text
                    break
           

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

            #Searches current seats that will be compared to the inital seats of current user.
            current_seats, class_name = get_page_content(classNum, term_dict.get(cls.term), driver)

            if cls.initialSeats == None:
                #Grabs initial seats to monitor.
                cls.initialSeats = current_seats
                #Commits initial seats to databasae.
                session.commit()

            if current_seats == None or class_name == None:
                print(f"Class {cls.classNum} not found\n")
                continue

            #Checks for changes in the seats available and if there's a change an email is sent.
            if int(current_seats) != int(cls.initialSeats):
                email_users(receiver_emails, class_name, current_seats)

                #Updates the initial seats to current seats in the database.
                cls.initialSeats = int(current_seats)

        #Changes will be applied to the database.
        session.commit()
        session.close()
        #Decreases CPU usage from APScheduler


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


#Adds background process for monitoring classes where the function is called at an interval.
scheduler = BackgroundScheduler()

chrome_options = Options()
chrome_options.add_argument('--headless=new')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument("window-size=1024,768")
chrome_options.add_argument("enable-automation")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--dns-prefetch-disable")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument('--log-level=3')

driver = webdriver.Chrome(options=chrome_options)
                                                    # args=[driver] (for if only one driver is used instead of creating a new one with each function call)
#Creating a driver for each function call allows for multiple instances. The result is slower function run time but multiple instances of the function being called.
scheduler.add_job(monitor, 'interval', seconds=15, args=[driver])
scheduler.start()

#If user is not registered add them to the database
@app.route('/', methods=['GET', 'POST'])
def login_user():
    user_authenticated = None
    if request.method == 'POST':
        email = request.form["email"]
        password = request.form["password"]
    
        if email and password:

            user_authenticate = User.query.filter_by(email=email).first()

            #Cross checks hashed password and password entered in the form.
            if user_authenticate and check_password_hash(user_authenticate.password, password):
                user_authenticated = True

                #Stores users email in session to be used when adding classes associated with that email.
                session['user_email'] = email
                return redirect(url_for('webpage'))
            else:
                user_authenticated = False
                return render_template('login.html', user_authenticated=user_authenticated)

    return render_template('login.html', user_authenticated=user_authenticated) 

@app.route('/logout')
def logout():
    session.pop('user_email', None)
    return redirect(url_for('login_user'))

@app.route('/delete')
def delete_account():
    #Get user in session
    user = User.query.filter_by(email=session["user_email"]).first()

    #If the user to be deleted is found remove each class associated with the user and remove 
    #the class from the db if no emails are associated with the class
    if user:
        for cls in user.classes:
            user.classes.remove(cls)
            if cls.users.count() == 0:
                db.session.delete(cls)

    #Delete user and remove user from session
        db.session.delete(user)
        session.pop('user_email', None)
        db.session.commit()

    #Set user_deleted to true to display the user deleted text on the webpage.
        user_deleted = True
        return redirect(url_for('registration', user_deleted=user_deleted))
        


#Root route to ask user to register or login if they already have an account
@app.route('/register', methods=['GET', 'POST'])
def registration():

    if request.method == 'GET':

        user_deleted = request.args.get('user_deleted')
        #Displays registration with user deleted display message so the user can make another account if needed.
        if user_deleted:
            return render_template('register.html', user_exists=False, user_deleted=True)
        return render_template('register.html', user_exists=False, user_deleted=False)

    if request.method == 'POST':
        #Gathers email and password from form data in POST request.
        email = request.form["email"]
        password = request.form["password"]

        #Check if user that attempted to register exists in the database
        exists = User.query.filter_by(email=email).first()
        if exists:
            return render_template('register.html', user_exists=True)
        
        #If user exists and provided valid email/password add user to database.
        elif email and password:
            #Hashes user password for safe storage.
            password_hash = generate_password_hash(password, method='pbkdf2:sha256')

            new_user = User(email=email, password=password_hash)
            db.session.add(new_user)
            db.session.commit()

            #url_for is the function name while render_template is the html file name
            return redirect(url_for('login_user'))

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():

    if request.method == 'POST':
        user = User.query.filter_by(email=request.form['email']).first()
        #If the user forgot their password they can delete their account so they can make a new one with the same email.
        if user:
            session['user_email'] = request.form['email']
            return redirect(url_for('delete_account'))
        
        else:
            no_user = True
            return render_template('forgot.html', no_user=no_user)
    
    return render_template('forgot.html')

#Root route that gets information from the submitted form and creates new users in the sql database.
@app.route('/monitor', methods=['GET', 'POST'])
def webpage():
    if 'user_email' not in session:
        return redirect(url_for('login_user'))
    
    user = User.query.filter_by(email=session['user_email']).first()

    #Gets user classes if user exist else create empty list
    user_classes = user.classes if user else []

    if request.method == 'POST':

        #Fetches class and email info from the form submission
        classNum = request.form["Class Number"]
        term = request.form.get("term_select")
        
        #If the user submitted a class and provided all info then check if user is already monitoring the class and if not append that class to that users associated classes.
        if request.form.get('submit') and term and classNum:

            #Needs no autoflush otherwise the query will not be compatible with the current session.
            with db.session.no_autoflush:
                #Check if the class exists
                cls = Class.query.filter_by(classNum=classNum).first()
            
                #If the class does not exist, create a new class
                if not cls and len(user.classes) < 2:
                    cls = Class(classNum=classNum, term=term, initialSeats=None)
                    db.session.add(cls)

                #Add the class to the user if not already added
                if cls not in user.classes and len(user.classes) < 2:
                    user.classes.append(cls)

                #Commit the changes
                db.session.commit()

        elif request.form.get('remove') and classNum:

            with db.session.no_autoflush:
                remove_cls = Class.query.filter_by(classNum=classNum).first()

            #Remove all classes associated with this user
            if remove_cls in user.classes:
                user.classes.remove(remove_cls)
                #If there are no emails associated with the class delete from db
                if remove_cls.users.count() == 0:
                    db.session.delete(remove_cls)

            db.session.commit()
    #Responds with the same html containing the form for more user submissions.
    return render_template('index.html', user=user, user_classes=user_classes)

@app.route('/adminsignin', methods=['GET', 'POST'])
def admin_signin():
    if request.method == 'POST':
        admin_password = request.form['password']
        if admin_password:
            session['admin_password'] = admin_password
            return redirect(url_for('get_users'))
        
    return render_template('admin.html')

#Route to view users and classes being monitored        
@app.route('/users', methods=['GET'])
def get_users():
    #Compares password from form with the environment variable for viewing users.
    if session['admin_password'] == os.getenv('ADMIN_PASSWORD'):
        users = User.query.all()
        classes = Class.query.all()
        user_table = ""
        class_table = ""

        #Dynamically builds table by concatenating each user and class to a row in a table to be passed to admin_table.html
        for user in users:
            classNum = ', '.join(str(cls.classNum) for cls in user.classes)
            user_table += f"""
            <tr style="border: 1px solid black;" bgcolor="lightblue" align="center">
                <td class="td">{user.email}</td>
                <td class="td">{classNum}</td>
                <td class="td">{user.password}</td>
            </tr>
            """

        #Checks for classes not associated with any user emails.
        for cls in classes:
            associated_emails = cls.users.count()
            if associated_emails == 0:
                db.session.delete(cls)
                db.session.commit()
            else:
                class_table += f"""
                <tr style="border: 1px solid black;" bgcolor="lightblue" align="center">
                    <td class="td">{cls.classNum}</td>
                    <td class="td">{cls.initialSeats}</td>
                    <td class="td">{associated_emails}</td>
                    <td class="td">{cls.term}</td>
                </tr>
                """

        return render_template('admin_table.html', class_table=class_table, user_table=user_table)
    return redirect(url_for('admin_signin'))
    #return Response(table, content_type='text/html')

@app.route('/robots.txt')
def robots_txt():
    return send_from_directory(app.root_path, 'robots.txt')

if __name__ == '__main__':
    #Creates instance of database in current flask context. 
    with app.app_context():
        db.drop_all()
        db.create_all()
    #Set debug to true so server doesn't need to be executed with every change.
    try:
        app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
    except(KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        driver.quit()
