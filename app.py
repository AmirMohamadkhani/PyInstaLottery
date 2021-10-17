from os import stat, truncate
from flask import Flask, render_template, flash, redirect, url_for, session, request, logging
from flask_mysqldb import MySQL
from flask import Response
from wtforms import Form, StringField, TextAreaField, PasswordField, validators
from passlib.hash import sha256_crypt
from functools import wraps
from InstaLottery import InstaLottery
import pandas as pd
from pay_ir.api.client import PayIrClient
import uuid
from flask import send_file
import os






app = Flask(__name__)
# Config MySQL
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'root'
app.config['MYSQL_DB'] = 'instagiveaway'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'
# init MYSQL
mysql = MySQL(app)
client = PayIrClient('test')

# Index
@app.route('/')
def index():
    return render_template('home.html')

# About
@app.route('/about')
def about():
    return render_template('about.html')

# Register Form Class
class RegisterForm(Form):
    name = StringField('Name', [validators.Length(min=1, max=50)])
    username = StringField('Username', [validators.Length(min=4, max=25)])
    email = StringField('Email', [validators.Length(min=6, max=50)])
    password = PasswordField('Password', [
        validators.DataRequired(),
        validators.EqualTo('confirm', message='Passwords do not match')
    ])
    confirm = PasswordField('Confirm Password')


# User Register
@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm(request.form)
    if request.method == 'POST' and form.validate():
        name = form.name.data
        email = form.email.data
        username = form.username.data
        password = sha256_crypt.encrypt(str(form.password.data))

        # Create cursor
        cur = mysql.connection.cursor()

        # Execute query
        cur.execute("INSERT INTO users(name, email, username, password) VALUES(%s, %s, %s, %s)", (name, email, username, password))

        # Commit to DB
        mysql.connection.commit()

        # Close connection
        cur.close()

        flash('You are now registered and can log in', 'success')

        return redirect(url_for('login'))
    return render_template('register.html', form=form)

# User login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Get Form Fields
        username = request.form['username']
        password_candidate = request.form['password']

        # Create cursor
        cur = mysql.connection.cursor()

        # Get user by username
        result = cur.execute("SELECT * FROM users WHERE username = %s", [username])

        if result > 0:
            # Get stored hash
            data = cur.fetchone()
            password = data['password']

            # Compare Passwords
            if sha256_crypt.verify(password_candidate, password):
                # Passed
                session['logged_in'] = True
                session['username'] = username

                flash('You are now logged in', 'success')
                return redirect(url_for('giveaway'))
            else:
                error = 'Invalid login'
                return render_template('login.html', error=error)
            # Close connection
            cur.close()
        else:
            error = 'Username not found'
            return render_template('login.html', error=error)

    return render_template('login.html')

# Check if user logged in
def is_logged_in(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'logged_in' in session:
            return f(*args, **kwargs)
        else:
            flash('Unauthorized, Please login', 'danger')
            return redirect(url_for('login'))
    return wrap

# Logout
@app.route('/logout')
@is_logged_in
def logout():
    session.clear()
    flash('You are now logged out', 'success')
    return redirect(url_for('login'))

# Dashboard
@app.route('/giveaway')
@is_logged_in
def giveaway():
    return render_template('dashboard.html')


def deleteFilesWithExt(dir_name, extension):
    dirFiles = os.listdir(dir_name)
    for item in dirFiles:
        if item.endswith(extension):
            os.remove(os.path.join(dir_name, item))
    

@app.route("/downloadResult", methods=['GET', 'POST'])
@is_logged_in
def downloadResult():
    #delete previous files if exist
    deleteFilesWithExt(os.path.dirname(os.path.realpath(__file__)), ".xlsx")

    filename = str(uuid.uuid1()) + ".xlsx"
    resFrame = pd.DataFrame(eval(request.form['df']))    

    excelFile = resFrame.to_excel(filename)

    return send_file(filename, attachment_filename = filename)

    # return Response(excelFile,
    #                      headers={"Content-Disposition":
    #                      "attachment;filename=" + filename})



# Process Giveaway
@app.route("/try_giveaway", methods=['GET', 'POST'])
@is_logged_in
def tryGiveaway():

    instalottory = InstaLottery("instauser12442021", "7272amir")
    status = request.args.get("status")
    token = request.args.get("token")
    if (status != None):
        if status == '1':
            finalRes = pd.DataFrame(session['finalRes'])
            postID = session['postID']
           
        else:
            flash('Unsuccessful payment', 'danger')
            return redirect(url_for('giveaway'))
            
    else:
    
        if not(bool(request.form.get("comments")) or bool(request.form.get("mentions")) or bool(request.form.get("follower"))
            or bool(request.form.get("likeit"))) :
            flash('Choose one fature', 'danger')
            return redirect(url_for('giveaway'))

        postURL = request.form["instaurl"]
        if "www.instagram.com/p" not in postURL:
            flash('Not Valid Instagram post URL', 'danger')
            return redirect(url_for('giveaway'))
        postID = postURL[postURL.rfind("/p/") + 3 : -1]

        session['winnerCount'] = request.form["winnerCount"]

        minComments = 0
        if bool(request.form.get("comments")):
            minComments = request.form["minComments"]

      
        post = instalottory.fetch_post(postID)

        feturesDict = {}
        feturesDict["comments"] = bool(request.form.get("comments"))
        feturesDict["mentions"] = bool(request.form.get("mentions"))
        feturesDict["follower"] = bool(request.form.get("follower"))
        feturesDict["likeit"] = bool(request.form.get("likeit"))

        
        finalRes = instalottory.createOutputFile(post, feturesDict, minComments)

        finalRes = instalottory.calculateScore(finalRes, minComments)

        
        if feturesDict["comments"]:
            if (pd.DataFrame(finalRes))['commentCount'].sum() > 100:
                session['finalRes'] = finalRes.to_dict()
                session['postID'] = postID
                response = client.init_transaction(50000, 'http://127.0.0.1:5000/try_giveaway')        
                return redirect(response['payment_url'])
                #if not successfull payment return error

        
    #Delete inside temp_images 
    instalottory.deleteWinnersImage()

    generator = instalottory.saveDftoExcel(finalRes) 

    winners = instalottory.executeLottery(finalRes, session['winnerCount'])
    if len(winners) > 0:
        return render_template("winner.html", winnerResults = winners, finalResult = finalRes.to_dict(orient='list'), generator = generator)
    else:
        return render_template("noresult.html")

    


    # Select features
    # Excel data
    # points
    # Download excel  
    

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


if __name__ == '__main__':
    app.secret_key='secret123'
    app.run(debug=True)
