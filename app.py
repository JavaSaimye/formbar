from flask import Flask, redirect, url_for, request, render_template
from websocket_server import WebsocketServer
import board, neopixel
import pandas
import json, csv
import pygame
import time, math
import threading
import netifaces as ni
import logging

logging.basicConfig(filename='info.log',
                            filemode='a',
                            format='%(asctime)s.%(msecs)d %(levelname)s %(message)s',
                            datefmt='%H:%M:%S',
                            level=logging.DEBUG)
# set up logging to console
console = logging.StreamHandler()
console.setLevel(logging.DEBUG)
# set a format which is simpler for console use
formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
console.setFormatter(formatter)
# add the handler to the root logger
logging.getLogger('').addHandler(console)
logger = logging.getLogger(__name__)

#Get internal IP address
#ip = ni.ifaddresses('wlan0')[ni.AF_INET][0]['addr']
ip = ni.ifaddresses('eth0')[ni.AF_INET][0]['addr']

WSPORT=9001

logging.info('Running formbar server on:' + ip)

import letters
import sfx
import bgm
from colors import colors, hex2dec
import lessons

import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

BARPIX = 240
MAXPIX = 762

sfx.updateFiles()
bgm.updateFiles()
pygame.init()

pixels = neopixel.NeoPixel(board.D21, MAXPIX, brightness=1.0, auto_write=False)

app = Flask(__name__)

groups = {
    'teacher': 0,
    'mod': 1,
    'student': 2,
    'anyone': 3,
    'banned': 4
}

settingsPerms = {
    'admin' : 0,
    'users' : 1,
    'api' : 3,
    'sfx' : 1,
    'bgm' : 1,
    'say' : 1,
    'bar' : 1
}

settingsBoolDict = {
    'locked' : False,
    'paused' : False,
    'blind' : False,
    'showinc' : True,
    'captions' : True,
    'autocount' : True
}
settingsIntDict = {
    'numStudents': 8
}

settingsStrDict = {
    'mode': 'thumbs',
    'upcolor': 'green',
    'wigglecolor': 'blue',
    'downcolor': 'red'
}

settingsStrList = {
    'modes': ['thumbs', 'survey', 'quiz', 'essay', 'progress', 'playtime']
}

whiteList = [
    '127.0.0.1',
    '172.21.3.5'
    ]

banList = []

studentList = {
}

lessonData = {}

sessionData = {
    'wawdLink': '/',
    'agendaStep': 0,
    'currentEssay': 0,
    'currentProgress': 0,
    'currentQuiz': 0,
    'stepResults': []
}

settingsIntDict['numStudents'] = 8
up = down = wiggle = 0
helpList = {}
blockList = []
colorDict = {
        '14': (255, 255, 0),
        '15': (196, 150, 128),
        '16': (255, 96, 0),
        '56': (0, 192, 192),
        }

quizQuestion = ''
quizAnswers = []
quizCorrect = ''

backButton = "<button onclick='window.history.back()'>Go Back</button><script language='JavaScript' type='text/javascript'>setTimeout(\"window.history.back()\",5000);</script>"

def aniTest():
    fillBar((0,0,0))
    for i in range(0, BARPIX - 40):
        pixRange = range(i+20, i + 40)
        pixRange2 = range(i, i + 20)
        for j, pix in enumerate(pixRange):
            pixels[pix] = blend(pixRange, j, colors['blue'], colors['red'])
        for j, pix in enumerate(pixRange2):
            pixels[pix] = blend(pixRange2, j, colors['green'], colors['blue'])
        pixels.show()

@app.route('/anitest')
def endpoint_anitest():
    if len(threading.enumerate()) < 5:
        threading.Thread(target=aniTest, daemon=True).start()
        return 'testing...'
    else:
        return 'Too many threads'

def newStudent(remote, username, forward='', pin=''):
    global studentList
    if not remote in studentList:
        studentList[remote] = {
            'name': username,
            'thumb': '',
            'survey': '',
            'essays': [],
            'quizzes': [],
            'progress': [],
            'perms': 2
        }
        if len(studentList) - 1:
            logging.info("New user logged in. Made them a student: " + username)
            studentList[remote]['perms'] = 2
        else:
            logging.info("First user logged in. Made them a Teacher: " + username)
            studentList[remote]['perms'] = 0
        playSFX("sfx_up02")
        if forward:
            return redirect(forward, code=302)

def playSFX(sound):
    try:
        pygame.mixer.Sound(sfx.sound[sound]).play()
        return "Succesfully played: "
    except:
        return "Invalid format: "
def playBGM(bgm_filename, volume=1.0):
    pygame.mixer.music.load(bgm.bgm[bgm_filename])
    pygame.mixer.music.set_volume(volume)
    pygame.mixer.music.play(loops=-1)
def stopBGM():
    pygame.mixer.music.stop()

def str2bool(strng):
    strng.lower()
    if strng == 'true':
        return True
    elif strng == 'false':
        return False
    else:
        return strng

def fadein(irange, current, color):
    return [int(x * (current / len(irange))) for x in color]

def fadeout(irange, current, color):
    return [int(x * ((len(irange) - current) / len(irange))) for x in color]

def blend(irange, current, color1, color2):
    blendColor = fadein(irange, current, color2)
    for i, rgb in enumerate(blendColor):
        blendColor[i] += fadeout(irange, current, color1)[i]
    return blendColor

def addBlock():
    if blockList[-1][0] in colorDict:
        pixels[len(blockList)-1] = colorDict[blockList[-1][0]]
    else:
        pixels[len(blockList)-1] = colors['default']
    pixels.show()

def fillBlocks():
    for i, block in enumerate(blockList):
        if block[0] in colorDict:
            pixels[i] = colorDict[block[0]]
        else:
            pixels[i] = colors['default']
    pixels.show()

def percFill(amount, fillColor=colors['green'], emptyColor=colors['red']):
    if amount > 100 and amount < 0 and type(amount) is not int:
        raise TypeError("Out of range. Must be between 0 - 1 or 0 - 100.")
    else:
        pixRange = math.ceil(BARPIX * (amount * 0.01))
        for pix in range(0, BARPIX):
            if pix <= pixRange:
                pixels[pix] = fillColor
            else:
                pixels[pix] = emptyColor
        pixels.show()

def fillBar(color=colors['default'], stop=BARPIX, start=0):
    #If you provide no args, the whole bar is made the default color
    #If you provide one arg, the whole bar will be that color
    #If you provide two args, the bar will be that color until the stop point
    #If you provide three args, pixels between the stop and start points will be that color
    for pix in range(start, stop):
        pixels[pix] = color

def clearBar():
    #fill with default color to clear bar
    for pix in range(0, BARPIX):
        pixels[pix] = colors['default']

def clearString():
    for i in range(BARPIX, MAXPIX):
        pixels[i] = colors['bg']

def showString(toShow, startLocation=0, fg=colors['fg'], bg=colors['bg']):
    for i, letter in enumerate(toShow.lower()):
        printLetter(letter, (i * (8 * 6)) + ((startLocation * 48) + BARPIX), fg, bg)

def printLetter(letter, startLocation, fg=colors['fg'], bg=colors['bg']):
    if (MAXPIX - startLocation) >= 48:
        if letter in letters.ASCIIdict:
            for i, pull_row in enumerate(letters.ASCIIdict[letter]):
                #temporary variable (keeps it from permanently flipping letter pixels)
                row = []
                for pix in pull_row:
                    row.append(pix)
                # If this is an even row, reverse direction
                if not i%2:
                    row.reverse()
                for j, pixel in enumerate(row):
                    pixPoint = startLocation + (i*8)
                    if pixel:
                        pixels[pixPoint + j] = fg
                    else:
                        pixels[pixPoint + j] = bg
                pixPoint = startLocation + (i + (8*5))
                for j in range(pixPoint, pixPoint + 4):
                    pixels[j] = bg

        else:
            logging.warning("Warning! Letter ", letter, " not found.")
    else:
        logging.warning("Warning! Not enough space for this letter!")

def surveyBar():
    results = [] # Create empty results list
    clearBar()
    #Go through IP list and see what each IP sent as a response
    for x in studentList:
        #add this result to the results list
        results.append(studentList[x])
    #The number of results is how many have completed the survey
    complete = len(results)
    #calculate the chunk length for each student
    chunkLength = math.floor(BARPIX / settingsIntDict['numStudents'])
    #Sort the results by "alphabetical order"
    results.sort()
    #Loop through each result, and show the correct color
    for index, result in enumerate(results):
        #Calculate how long this chunk will be and where it starts
        pixRange = range((chunkLength * index), (chunkLength * index) + chunkLength)
        #Fill in that chunk with the correct color
        if result == 'a':
            for i, pix in enumerate(pixRange):
                #If it's the first pixel of the chunk, make it a special color
                if i == 0:
                    pixels[pix] = colors['student']
                else:
                    if settingsBoolDict['blind'] and complete != settingsIntDict['numStudents']:
                        pixels[pix] = fadein(pixRange, i, colors['blind'])
                    else:
                        pixels[pix] = fadein(pixRange, i, colors['red'])
        elif result == 'b':
            for i, pix in enumerate(pixRange):
                if i == 0:
                    pixels[pix] = colors['student']
                else:
                    if settingsBoolDict['blind'] and complete != settingsIntDict['numStudents']:
                        pixels[pix] = fadein(pixRange, i, colors['blind'])
                    else:
                        pixels[pix] = fadein(pixRange, i, colors['blue'])
        elif result == 'c':
            for i, pix in enumerate(pixRange):
                if i == 0:
                    pixels[pix] = colors['student']
                else:
                    if settingsBoolDict['blind'] and complete != settingsIntDict['numStudents']:
                        pixels[pix] = fadein(pixRange, i, colors['blind'])
                    else:
                        pixels[pix] = fadein(pixRange, i, colors['yellow'])
        elif result == 'd':
            for i, pix in enumerate(pixRange):
                if i == 0:
                    pixels[pix] = colors['student']
                else:
                    if settingsBoolDict['blind'] and complete != settingsIntDict['numStudents']:
                        pixels[pix] = fadein(pixRange, i, colors['blind'])
                    else:
                        pixels[pix] = fadein(pixRange, i, colors['green'])
    if settingsBoolDict['captions']:
        clearString()
        showString("SRVY " + str(complete) + "/" + str(settingsIntDict['numStudents']))
    pixels.show()

def tutdBar():
    global studentList
    if settingsBoolDict['autocount']:
        autoStudentCount()
    upFill = upCount = downFill = wiggleFill = 0
    complete = 0
    for x in studentList:
        if studentList[x]['thumb']:
            if studentList[x]['thumb'] == 'up':
                upFill += 1
                upCount += 1
            elif studentList[x]['thumb'] == 'down':
                downFill += 1
            elif studentList[x]['thumb'] == 'wiggle':
                wiggleFill += 1
            complete += 1
    for pix in range(0, BARPIX):
        pixels[pix] = colors['default']
    if settingsBoolDict['showinc']:
        chunkLength = math.floor(BARPIX / settingsIntDict['numStudents'])
    else:
        chunkLength = math.floor(BARPIX / complete)
    for index, ip in enumerate(studentList):
        pixRange = range((chunkLength * index), (chunkLength * index) + chunkLength)
        if upFill > 0:
            for i, pix in enumerate(pixRange):
                if i == 0:
                    pixels[pix] = colors['student']
                else:
                    if settingsBoolDict['blind'] and complete != settingsIntDict['numStudents']:
                        pixels[pix] = fadein(pixRange, i, colors['blind'])
                    else:
                        pixels[pix] = fadein(pixRange, i, colors['green'])
            upFill -= 1
        elif wiggleFill > 0:
            for i, pix in enumerate(pixRange):
                if i == 0:
                    pixels[pix] = colors['student']
                else:
                    if settingsBoolDict['blind'] and complete != settingsIntDict['numStudents']:
                        pixels[pix] = fadein(pixRange, i, colors['blind'])
                    else:
                        pixels[pix] = fadein(pixRange, i, colors['blue'])
            wiggleFill -= 1
        elif downFill > 0:
            for i, pix in enumerate(pixRange):
                if i == 0:
                    pixels[pix] = colors['student']
                else:
                    if settingsBoolDict['blind'] and complete != settingsIntDict['numStudents']:
                        pixels[pix] = fadein(pixRange, i, colors['blind'])
                    else:
                        pixels[pix] = fadein(pixRange, i, colors['red'])
            downFill -= 1
    if settingsBoolDict['captions']:
        clearString()
        showString("TUTD " + str(complete) + "/" + str(settingsIntDict['numStudents']))
        pixels.show()
    if upCount >= settingsIntDict['numStudents']:
        settingsBoolDict['paused'] = True
        pixels.fill((0,0,0))
        playSFX("sfx_success01")
        for i, pix in enumerate(range(0, BARPIX)):
                pixels[pix] = blend(range(0, BARPIX), i, colors['blue'], colors['red'])
        if settingsBoolDict['captions']:
            clearString()
            showString("MAX GAMER!", 0, colors['purple'])
    pixels.show()

def autoStudentCount():
    settingsIntDict['numStudents'] = 0
    for user in studentList:
        if studentList[user]['perms'] == 2:
            settingsIntDict['numStudents'] += 1
    if settingsIntDict['numStudents'] == 0:
        settingsIntDict['numStudents'] = 1

@app.route('/')
def endpoint_home():
    return render_template('index.html')

@app.route('/wawd')
def endpoint_wawd():
    return redirect(sessionData['wawdLink'])

@app.route('/login', methods = ['POST', 'GET'])
def endpoint_login():
    remote = request.remote_addr
    if remote in banList:
        return "This IP is in the banlist."
    else:
        if request.method == 'POST':
            username = request.form['username']
            forward = request.form['forward']
            #pin = request.form['pin']
            if username.strip():
                newStudent(remote, username, forward)
                return redirect('/', code=302)
            else:
                return render_template("message.html", message="You cannot have a blank name.")
        elif request.args.get('name'):
            newStudent(remote, request.args.get('name'))
            return redirect('/', code=302)
        else:
            return render_template("login.html")

@app.route('/color')
def endpoint_color():
    if not request.remote_addr in studentList:
        # This will have to send along the current address as "forward" eventually
        return redirect('/login')
    '''
    if settingsBoolDict['locked'] == True:
        if not request.remote_addr in whiteList:
            return render_template("message.html", message = "You are not whitelisted. " )
    '''
    if studentList[request.remote_addr]['perms'] > settingsPerms['bar']:
        return render_template("message.html", message = "You do not have high enough permissions to do this right now. " )
    else:
        try:
            r = int(request.args.get('r'))
            g = int(request.args.get('g'))
            b = int(request.args.get('b'))
        except:
            r = ''
            g = ''
            b = ''
        hex = request.args.get('hex')
        if hex2dec(hex):
            fillBar(hex2dec(hex))
        elif r and b and g:
            fillBar((r, g, b))
        else:
            return "Bad ArgumentsTry <b>/color?hex=FF00FF</b> or <b>/color?r=255&g=0&b=255</b>"
        pixels.show()
        return render_template("message.html", message = "Color sent!" )

@app.route('/hangman')
def endpoint_hangman():
    return render_template("hangman.html")

@app.route('/segment')
def endpoint_segment():
    if not request.remote_addr in studentList:
        # This will have to send along the current address as "forward" eventually
        return redirect('/login')
    if studentList[request.remote_addr]['perms'] > settingsPerms['bar']:
        return render_template("message.html", message = "You do not have high enough permissions to do this right now. " )
    else:
        type = request.args.get('type')
        hex = request.args.get('hex')
        hex2 = request.args.get('hex2')
        start = request.args.get('start')
        end = request.args.get('end')
        if not hex:
            return "Bad ArgumentsTry <b>/segment?start=0&end=10&hex=FF00FF</b> (you need at least one color)"
        if not hex2dec(hex):
            return "Bad ArgumentsTry <b>/segment?start=0&end=10&hex=FF00FF</b> (you did not use a proper hexadecimal color)"
        if not start or not end:
            return "Bad ArgumentsTry <b>/segment?start=0&end=10&hex=FF00FF</b> (you need a start and end point)"
        else:
            try:
                start = int(start)
                end = int(end)
            except:
                return "Bad ArgumentsTry <b>/segment?start=0&end=10&hex=FF00FF</b> (start and end must be and integer)"
        if start > BARPIX or end > BARPIX:
            return "Bad ArgumentsTry <b>/segment?start=0&end=10&hex=FF00FF</b> (Your start or end was higher than the number of pixels: " + str(BARPIX) + ")"
        pixRange = range(start, end)
        if type == 'fadein':
            for i, pix in enumerate(pixRange):
                pixels[pix] = fadein(pixRange, i, hex2dec(hex))
        elif type == 'fadeout':
            for i, pix in enumerate(pixRange):
                pixels[pix] = fadeout(pixRange, i, hex2dec(hex))
        elif type == 'blend':
            if not hex:
                return "Bad ArgumentsTry <b>/segment?start=0&end=10&hex=FF00FF&hex2=00FF00</b> (you need at least two colors)"
            if not hex2dec(hex):
                return "Bad ArgumentsTry <b>/segment?start=0&end=10&hex=FF00FF&hex2=00FF00</b> (you did not use a proper hexadecimal color)"
            else:
                for i, pix in enumerate(pixRange):
                    pixels[pix] = blend(pixRange, i, hex2dec(hex), hex2dec(hex2))
        elif type == 'color':
                for i, pix in enumerate(pixRange):
                    pixels[pix] = hex2dec(hex)
        else:
            if hex2dec(hex):
                fillBar(hex2dec(hex))
            else:
                return "Bad ArgumentsTry <b>/color?hex=FF00FF</b> or <b>/color?r=255&g=0&b=255</b>"
        pixels.show()
        return render_template("message.html", message = "Color sent!" )


@app.route('/loadlesson')
def endpoint_loadlesson():
    global lessonData
    lessonData = lessons.readFolder()[0]
    for student in studentList:
        for i, prog in enumerate(lessonData['progressList']):
            newProg = []
            for j in range(len(lessonData['progressList'][i]['task'])):
                newProg.append(False)
            studentList[student]['progress'].append(newProg)
    print(studentList)
    return render_template("message.html", message = "Lesson loaded for all students.")


@app.route('/progress')
def endpoint_progress():
    if not request.remote_addr in studentList:
        # This will have to send along the current address as "forward" eventually
        return redirect('/login')
    if studentList[request.remote_addr]['perms'] > groups['student']:
        return render_template("message.html", message = "You do not have high enough permissions to do this right now. " )
    elif studentList[request.remote_addr]['perms'] == groups['teacher']:
        print(lessonData)
        resString = '<ul>'
        #Show current progress total bar of students combined
        #Show each student and current progress
        for student in studentList:
            resString += '<li>' + studentList[student]['name'] + '</li><ul><li>'
            for i, prog in enumerate(studentList[student]['progress'][sessionData['currentProgress']]):
                resString += str(studentList[student]['progress'][sessionData['currentProgress']][i])
                if i < len(studentList[student]['progress'][sessionData['currentProgress']]) - 1:
                    resString += ', '
            resString += '</ul>'
        resString += '</ul>'
        #Click on student to show all progresses (clientside)
        return render_template("general.html", content=resString)
    else:
        if request.args.get('progindex'):
            progIndex = request.args.get('progindex')
            checkIndex = request.args.get('checkindex')
            checkVal = request.args.get('checkval')
            if checkIndex and checkVal:

                pass
            else:
                if len(lessonData[sessionData['currentProgress']]['progressList']):
                    resString = '<ul>'
                    for i, task in enumerate(lessonData[0]['progressList'][0]['task']):
                        resString += '<li><input type="checkbox"> ' + task
                        resString += '<ul><li>' + lessonData[0]['progressList'][0]['desc'][i] + '</li></ul></li>'
                    resString += '</ul>'
                    return render_template("general.html", content=resString)
                else:
                    return render_template('message.html', message="There was an error?")

@app.route('/settings', methods = ['POST', 'GET'])
def settings():
    if not request.remote_addr in studentList:
        # This will have to send along the current address as "forward" eventually
        return redirect('/login')
    '''
    if settingsBoolDict['locked'] == True:
        if not request.remote_addr in whiteList:
            return render_template("message.html", message = "You are not whitelisted. " )
    '''
    if studentList[request.remote_addr]['perms'] > settingsPerms['bar']:
        return render_template("message.html", message = "You do not have high enough permissions to do this right now. " )
    else:
        if request.method == 'POST':
            # quizQuestion = request.form['qQuestion']
            # quizCorrect = int(request.form['quizlet'])
            # quizAnswers = [request.form['qaAnswer'], request.form['qbAnswer'], request.form['qcAnswer'], request.form['qdAnswer']]
            if settingsStrDict['mode'] == 'thumbs':
                for student in studentList:
                    studentList[student]['thumb'] = ''
                tutdBar()
            elif settingsStrDict['mode'] == 'survey':
                for student in studentList:
                    studentList[student]['survey'] = ''
                surveyBar()
            playSFX("sfx_success01")
            settingsBoolDict['paused'] = False
            return redirect(url_for('settings'))
        else:
            resString = ''
            #Loop through every arg that was sent as a query parameter
            for arg in request.args:
                #See if you save the
                argVal = str2bool(request.args.get(arg))
                #if the argVal resolved to a boolean value
                if isinstance(argVal, bool):
                    if arg in settingsBoolDict:
                        settingsBoolDict[arg] = argVal
                        resString += 'Set <i>' + arg + '</i> to: <i>' + str(argVal) + "</i>"
                    else:
                        resString += 'There is no setting that takes \'true\' or \'false\' named: <i>' + arg + "</i>"
                else:
                    try:
                        argInt = int(request.args.get(arg))
                        if arg in settingsPerms:
                            if argInt > 3 or argInt < 0:
                                resString += "Permission value out of range! "
                            else:
                                settingsPerms[arg] = argInt
                    except:
                        pass

            ###
            ### Everything past this point uses the old method of changing settings. Needs updated
            ###

            if request.args.get('students'):
                settingsIntDict['numStudents'] = int(request.args.get('students'))
                if settingsIntDict['numStudents'] == 0:
                    settingsBoolDict['autocount'] = True
                    autoStudentCount()
                else:
                    settingsBoolDict['autocount'] = False
                resString += 'Set <i>numStudents</i> to: ' + str(settingsIntDict['numStudents'])
            if request.args.get('mode'):
                if request.args.get('mode') in settingsStrList['modes']:
                    settingsStrDict['mode'] = request.args.get('mode')
                    resString += 'Set <i>mode</i> to: ' + settingsStrDict['mode']
                else:
                    resString += 'No setting called ' + settingsStrDict['mode']
            if resString == '':
                return render_template("settings.html")
            else:
                playSFX("sfx_pickup01")
                resString += ""
                return resString

@app.route('/flush')
def endpoint_flush():
    if not request.remote_addr in studentList:
        # This will have to send along the current address as "forward" eventually
        return redirect('/login')
    if studentList[request.remote_addr]['perms'] > settingsPerms['admin']:
        return render_template("message.html", message = "You do not have high enough permissions to do this right now. " )
    else:
        for user in list(studentList):
            if not studentList[user]['perms'] == settingsPerms['admin']:
                del studentList[user]
        playSFX("sfx_splash01")
        return render_template("message.html", message = "Users removed from list." )

@app.route('/quiz')
def endpoint_quiz():
    if not request.remote_addr in studentList:
        # This will have to send along the current address as "forward" eventually
        return redirect('/login')
    '''
    if settingsBoolDict['locked'] == True:
        if not request.remote_addr in whiteList:
            return render_template("message.html", message = "You are not whitelisted. " )
    '''
    if studentList[request.remote_addr]['perms'] > settingsPerms['bar']:
        return render_template("message.html", message = "You do not have high enough permissions to do this right now. " )
    else:
        answer = request.args.get('answer')
        if answer:
            answer = int(answer)
            if request.remote_addr not in studentList:
                if answer == quizCorrect:
                    studentList[request.remote_addr]['thumbs'] = 'up'
                else:
                    studentList[request.remote_addr]['thumbs'] = 'down'
                tutdBar()
                return render_template("message.html", message = "Thank you for your tasty bytes..." )
            else:
                return render_template("message.html", message = "You have already answered this quiz." )
        else:
            resString = '<meta http-equiv="refresh" content="5">'
            if request.remote_addr in studentList:
                resString += '<b><i>You have already answered this question. Wait for a new one</b></i>'
            resString += '<table border=1><tr><td>' + quizQuestion + '</td></tr>'
            for i, question in enumerate(quizAnswers):
                resString += '<tr><td><a href="/quiz?answer=' + str(i) + '">' + question + '</a></td></tr>'
            resString += '</table>'
            return resString

@app.route('/survey')
def endpoint_survey():
    if not request.remote_addr in studentList:
        # This will have to send along the current address as "forward" eventually
        return redirect('/login')
    '''
    if settingsBoolDict['locked'] == True:
        if not request.remote_addr in whiteList:
            return render_template("message.html", message = "You are not whitelisted. " )
    '''
    if studentList[request.remote_addr]['perms'] > settingsPerms['bar']:
        return render_template("message.html", message = "You do not have high enough permissions to do this right now. " )
    else:
        if not settingsStrDict['mode'] == 'survey':
            return render_template("message.html", message = "Not in Survey mode " )
        ip = request.remote_addr
        vote = request.args.get('vote')
        name = request.args.get('name')
        if not name:
            name = 'unknown'
        elif vote:
            logging.info("Recieved " + vote + " from " + name + " at " + ip)
            playSFX("sfx_blip01")
        #if settingsStrDict['mode'] != 'survey':
            #return render_template("message.html", message = "There is no survey right now" )
        if vote:
            if vote in ["a", "b", "c", "d"]:
                studentList[request.remote_addr]['survey'] = vote
                surveyBar()
                return render_template("message.html", message = "Thank you for your tasty bytes... (" + vote + ")" )
            elif vote == 'oops':
                sstudentList[request.remote_addr]['survey'] = ''
                surveyBar()
                return render_template("message.html", message = "I won\'t mention it if you don\'t" )
            else:
                return "Bad ArgumentsTry <b>/survey?vote=a</b>"
        else:
            return render_template("thumbsrental.html")

@app.route('/tutd')
def endpoint_tutd():
    if not request.remote_addr in studentList:
        # This will have to send along the current address as "forward" eventually
        return redirect('/login')
    else:
        ip = request.remote_addr
        thumb = request.args.get('thumb')
        if thumb:
            # logging.info("Recieved " + thumb + " from " + name + " at ip: " + ip)
            if thumb == 'up' or thumb == 'down' or thumb == 'wiggle' :
                if not studentList[request.remote_addr]['thumb']:
                    studentList[request.remote_addr]['thumb'] = request.args.get('thumb')
                    playSFX("sfx_blip01")
                    tutdBar()
                    return render_template("message.html", message = "Thank you for your tasty bytes... (" + thumb + ")" )
                else:
                    return render_template("message.html", message = "You've already sunmitted this answer... (" + thumb + ")" )
            elif thumb == 'oops':
                if studentList[request.remote_addr]['thumb']:
                    studentList[request.remote_addr]['thumb'] = ''
                    playSFX("sfx_hit01")
                    tutdBar()
                    return render_template("message.html", message = "I won\'t mention it if you don\'t" )
                else:
                    return render_template("message.html", message = "You don't have an answer to erase." )
            else:
                return "Bad ArgumentsTry <b>/tutd?thumb=wiggle</b>You can also try <b>down</b> and <b>up</b> instead of <b>wiggle</b>"
        else:
            return render_template("thumbsrental.html")

@app.route('/help', methods = ['POST', 'GET'])
def endpoint_help():
    if not request.remote_addr in studentList:
        # This will have to send along the current address as "forward" eventually
        return redirect('/login')
    if request.method == 'POST':
        name = studentList[request.remote_addr]['name']
        name = name.replace(" ", "")
        if name in helpList:
            return render_template("message.html", message = "You already have a help ticket in. If your problem is time-sensitive, or your last ticket was not cleared, please get the teacher's attention manually." )
        else:
            helpList[name] = "Help ticket"
            playSFX("sfx_up04")
            return render_template("message.html", message = "Your ticket was sent. Keep working on the problem the best you can while you wait." )
    else:
        return render_template("help.html")

@app.route('/needshelp')
def endpoint_needshelp():
    if not request.remote_addr in studentList:
        # This will have to send along the current address as "forward" eventually
        return redirect('/login')
    if studentList[request.remote_addr]['perms'] > settingsPerms['admin']:
        return render_template("message.html", message = "You do not have high enough permissions to do this right now. " )
    else:
        remove = request.args.get('remove')
        '''
        if bool(helpList):
            pixels.fill(colors['red'])
        else:
            pixels.fill((0, 0, 0))
        pixels.show()
        '''
        if remove:
            if remove in helpList:
                del helpList[remove]
                return render_template("message.html", message = "Removed ticket for: " + remove +"" )
            else:
                return render_template("message.html", message = "Couldn't find ticket for: " + remove +"" )
        else:
            resString = '<meta http-equiv="refresh" content="5">'
            if not helpList:
                resString += "No tickets yet. <button onclick='location.reload();'>Try Again</button>"
                return resString
            else:
                resString += "<table border=1>"
                for ticket in helpList:
                    resString += "<tr><td><a href=\'/needshelp?remove=" + ticket +"\'>" + ticket + "</a></td><td>" + helpList[ticket] + "</td></tr>"
                resString += "</table>"
                return render_template("needshelp.html", table = resString)

@app.route('/chat')
def endpoint_chat():
    if not request.remote_addr in studentList:
        # This will have to send along the current address as "forward" eventually
        return redirect('/login')
    if studentList[request.remote_addr]['perms'] > settingsPerms['say']:
        return render_template("message.html", message = "You do not have high enough permissions to do this right now. " )
    else:
        return render_template("chat.html", username = studentList[request.remote_addr]['name'], serverIp = ip)

@app.route('/users')
def endpoint_user():
    if not request.remote_addr in studentList:
        # This will have to send along the current address as "forward" eventually
        return redirect('/login')
    '''
    if settingsBoolDict['locked'] == True:
        if not request.remote_addr in whiteList:
            return render_template("message.html", message = "You are not whitelisted. " )
    '''
    if studentList[request.remote_addr]['perms'] > settingsPerms['users']:
        return render_template("message.html", message = "You do not have high enough permissions to do this right now. " )
    else:
        user = '';
        if request.args.get('name'):
            for key, value in studentList.items():
                if request.args.get('name') == studentList[key]['name']:
                    user = key
                    break
            if not user:
                return render_template("message.html", message = "That user was not found by their name. " )
        if request.args.get('ip'):
            if request.args.get('ip') in studentList:
                user = request.args.get('ip')
            else:
                return render_template("message.html", message = "That user was not found by their IP address. " )
        if user:
            if request.args.get('action'):
                action = request.args.get('action')
                if action == 'kick':
                    if user in studentList:
                        del studentList[user]
                        return "User removed"
                    else:
                        return render_template("message.html", message = "User not in list. " )
                if action == 'ban':
                    if user in studentList:
                        banList.append(user)
                        del studentList[user]
                        return "User removed and added to ban list."
                    else:
                        return render_template("message.html", message = "User not in list. " )
                if action == 'perm':
                    if request.args.get('perm'):
                        try:
                            perm = int(request.args.get('perm'))
                            if user in studentList:
                                if perm > 3 or perm < 0 :
                                    return render_template("message.html", message = "Permissions out of range. " )
                                else:
                                    studentList[user]['perms'] = perm
                                    return render_template("message.html", message = "Changed user permission. " )
                            else:
                                return render_template("message.html", message = "User not in list. " )
                        except:
                            return render_template("message.html", message = "Perm was not an integer. " )
            else:
                return render_template("message.html", message = "No action given. " )
        else:
            return render_template("users.html")

'''
@app.route('/emptyblocks')
def endpoint_emptyblocks():
    blockList = []
    pixels.fill((0,0,0))
    pixels.show()
    return "Emptied blocks"

@app.route('/sendblock')
def endpoint_sendblock():
    if not settingsStrDict['mode'] == 'blockchest':
        return render_template("message.html", message = "Not in blockchest settingsStrDict['mode'] " )
    blockId = request.args.get("id")
    blockData = request.args.get("data")
    if blockId and blockData:
        if blockId in colorDict:
            blockList.append([blockId, blockData])
            addBlock()
            #fillBlocks()
            return "Got Block: " + blockId + ", " + blockData
        else:
            return "Bad block Id"
    else:
        return "Bad Arguments. Requires 'id' and 'data'"
'''

@app.route('/getpix')
def endpoint_getpix():
    return '{"pixels": "'+ str(pixels[:BARPIX]) +'"}'

@app.route('/getstudents')
def endpoint_getstudents():
    if not request.remote_addr in studentList:
        # This will have to send along the current address as "forward" eventually
        return redirect('/login')
    if studentList[request.remote_addr]['perms'] > settingsPerms['api']:
        return render_template("message.html", message = "You do not have high enough permissions to do this right now. " )
    else:
        return json.dumps(studentList)

@app.route('/getpermissions')
def endpoint_getpermissions():
    if not request.remote_addr in studentList:
        # This will have to send along the current address as "forward" eventually
        return redirect('/login')
    if studentList[request.remote_addr]['perms'] > settingsPerms['api']:
        return render_template("message.html", message = "You do not have high enough permissions to do this right now. " )
    else:
        return json.dumps(settingsPerms)

@app.route('/virtualbar')
def endpoint_virtualbar():
    return render_template("virtualbar.html", serverIp = ip)

@app.route('/sfx')
def endpoint_sfx():

    if not request.remote_addr in studentList:
        # This will have to send along the current address as "forward" eventually
        return redirect('/login')
    if studentList[request.remote_addr]['perms'] > settingsPerms['sfx']:
        return render_template("message.html", message = "You do not have high enough permissions to do this right now. " )
    else:
        sfx.updateFiles()
        sfx_file = request.args.get('file')
        if sfx_file in sfx.sound:
            playSFX(sfx_file)
            return render_template("message.html", message = 'Playing: ' + sfx_file )
        else:
            resString = '<h2>List of available sound files:</h2><ul>'
            for key, value in sfx.sound.items():
                resString += '<li><a href="/sfx?file=' + key + '">' + key + '</a></li>'
            resString += '</ul> You can play them by using \'/sfx?file=<b>&lt;sound file name&gt;</b>\''
            return render_template("general.html", content = resString, style = '<style>ul {columns: 2; -webkit-columns: 2; -moz-columns: 2;}</style>')

@app.route('/bgm')
def endpoint_bgm():
    if not request.remote_addr in studentList:
        # This will have to send along the current address as "forward" eventually
        return redirect('/login')
    '''
    if settingsBoolDict['locked'] == True:
        if not request.remote_addr in whiteList:
            return render_template("message.html", message = "You are not whitelisted. " )
    '''
    if studentList[request.remote_addr]['perms'] > settingsPerms['bgm']:
        return render_template("message.html", message = "You do not have high enough permissions to do this right now. " )
    else:
        bgm.updateFiles()
        bgm_file = request.args.get('file')
        if bgm_file in bgm.bgm:
            bgm_volume = request.args.get('volume')
            if bgm_volume and type(bgm_volume) is float:
                playBGM(bgm_file, bgm_volume)
            else:
                playBGM(bgm_file)
            return render_template("message.html", message = 'Playing: ' + bgm_file )
        else:
            resString = '<a href="/bgmstop">Stop Music</a>'
            resString += '<h2>List of available background music files:</h2><ul>'
            for key, value in bgm.bgm.items():
                resString += '<li><a href="/bgm?file=' + key + '">' + key + '</a></li>'
            resString += '</ul> You can play them by using \'<b>/bgm?file=&lt;sound file name&gt;&volume=&lt;0.0 - 1.0&gt;\'</b>'
            resString += '<br><br>You can stop them by using \'<b>/bgmstop</b>\''
            return render_template("general.html", content = resString, style = '<style>ul {columns: 2; -webkit-columns: 2; -moz-columns: 2;}</style>')

@app.route('/bgmstop')
def endpoint_bgmstop():
    stopBGM()
    return render_template("message.html", message = 'Stopped music...' )

@app.route('/perc')
def endpoint_perc():
    if not request.remote_addr in studentList:
        # This will have to send along the current address as "forward" eventually
        return redirect('/login')
    '''
    if settingsBoolDict['locked'] == True:
        if not request.remote_addr in whiteList:
            return render_template("message.html", message = "You are not whitelisted. " )
    '''
    if studentList[request.remote_addr]['perms'] > settingsPerms['bar']:
        return render_template("message.html", message = "You do not have high enough permissions to do this right now. " )
    else:
        percAmount = request.args.get('amount')
        try:
            percAmount = int(percAmount)
            percFill(percAmount)
        except:
            return render_template("message.html", message = "<b>amount</b> must be an integer between 0 and 100 \'/perc?amount=<b>50</b>\'" )
        return render_template("message.html", message = "Set perecentage to: " + str(percAmount) + "" )

@app.route('/say')
def endpoint_say():
    if not request.remote_addr in studentList:
        # This will have to send along the current address as "forward" eventually
        return redirect('/login')
    '''
    if settingsBoolDict['locked'] == True:
        if not request.remote_addr in whiteList:
            return render_template("message.html", message = "You are not whitelisted. " )
    '''
    if studentList[request.remote_addr]['perms'] > settingsPerms['bar']:
        return render_template("message.html", message = "You do not have high enough permissions to do this right now. " )
    else:
        phrase = request.args.get('phrase')
        fgColor = request.args.get('fg')
        bgColor = request.args.get('bg')
        if phrase:
            if hex2dec(fgColor) and hex2dec(bgColor):
                clearString()
                showString(phrase, 0, hex2dec(fgColor), hex2dec(bgColor))
            else:
                clearString()
                showString(phrase)
            pixels.show()
            #engine.say(p)
            #engine.runAndWait()
        else:
            return render_template("message.html", message = "<b>phrase</b> must contain a string. \'/say?phrase=<b>\'hello\'</b>\'" )
        return render_template("message.html", message = "Set phrase to: " + str(phrase) + "" )

#Startup stuff
showString(ip)
pixels.show()
playSFX("sfx_bootup02")

'''
    Websocket Setup
    https://github.com/Pithikos/python-websocket-server

    A message to or from the server should be a stringified JSON object:
    {
        type: <alert|userlist|help|message>,
        to: <*username*|server|all>,
        from: <*username*|server>,
        content: <message>
    }

'''

def packMSG(type, rx, tx, content):
    msgOUT = {
        "type": type,
        "to": rx,
        "from": tx,
        "content": content
        }
    return msgOUT

# Called for every client connecting (after handshake)
def new_client(client, server):
    try:
        studentList[client['address'][0]]['wsID'] = client['id']
        logging.info(studentList[client['address'][0]]['name'] + " connected and was given id %d" % client['id'])
        server.send_message_to_all(json.dumps(packMSG('alert', 'all', 'server', studentList[client['address'][0]]['name'] + " has joined the server...")))
        server.send_message_to_all(json.dumps(packMSG('userlist', 'all', 'server', studentList)))
    except Exception as e:
        logging.error("Error finding user in list: " + str(e))

# Called for every client disconnecting
def client_left(client, server):
    logging.info(studentList[client['address'][0]]['name'] + " disconnected")
    del studentList[client['address'][0]]['wsID']
    server.send_message_to_all(json.dumps(packMSG('alert', 'all', 'server', studentList[client['address'][0]]['name'] + " has left the server...")))
    server.send_message_to_all(json.dumps(packMSG('userlist', 'all', 'server', studentList)))

# Called when a client sends a message
def message_received(client, server, message):
    try:
        message = json.loads(message)
        if message['type'] == 'userlist':
            server.send_message(client, json.dumps(packMSG('userlist', studentList[client['address'][0]]['name'], 'server', studentList)))
        if message['type'] == 'alert':
            server.send_message(client, json.dumps(packMSG('alert', studentList[client['address'][0]]['name'], 'server', 'Only the server can send alerts!')))
        if message['type'] == 'help':
            name = studentList[client['address'][0]]['name']
            name = name.replace(" ", "")
            helpList[name] = message['content']
            playSFX("sfx_up04")
            server.send_message(client, json.dumps(packMSG('alert', studentList[client['address'][0]]['name'], 'server', 'Your help ticket was sent. Keep working on the problem while you wait!')))
        else:
            #Check for permissions
            if studentList[client['address'][0]]['perms'] > settingsPerms['say']:
                messageOut = packMSG('alert', studentList[client['address'][0]]['name'], 'server', "You do not have permission to send text messages.")
                server.send_message(client, json.dumps(messageOut))
            else:
                #Checking max message length here
                if len(message['content']) > 252:
                    message['content'] = message['content'][:252]+'...'
                #Check recipients here
                if message['to'] == 'all':
                    messageOut =  packMSG('message', 'all', studentList[client['address'][0]]['name'], message['content'])
                    server.send_message_to_all(json.dumps(messageOut))
                else:
                    for student in studentList:
                        if studentList[student]['name'] == message['to']:
                            for toClient in server.clients:
                                if toClient['id'] == studentList[student]['wsID']:
                                    messageOut =  packMSG('message', message['to'], studentList[client['address'][0]]['name'], message['content'])
                                    server.send_message(toClient, json.dumps(messageOut))
                                    break
                logging.info(message['from'] + " said to " + message['to'] + ": " + message['content'])
    except Exception as e:
        logging.error('Error: ' + str(e))

def start_flask():
    app.run(host='0.0.0.0', use_reloader=False, debug = False)

def start_chat():
    server = WebsocketServer(WSPORT, host='0.0.0.0')
    server.set_fn_new_client(new_client)
    server.set_fn_client_left(client_left)
    server.set_fn_message_received(message_received)
    server.run_forever()

if __name__ == '__main__':
    chatApp = threading.Thread(target=start_chat, daemon=True)
    chatApp.start()
    # flaskApp = threading.Thread(target=start_flask)
    # flaskApp.start()
    # flaskApp.join()
    start_flask()
    chatApp.join()
