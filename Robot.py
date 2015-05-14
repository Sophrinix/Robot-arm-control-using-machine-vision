__author__ = 'AlexThiel'
import serial
import math
import Variables as V
import inspect
from Video import Common
from ast import literal_eval
from time import sleep

ser1 = serial.Serial('COM4', 9600, timeout=0)

#Position Variables. Decides the robots initial position
""" CARTESIAN COORDINATES:
Not intuitivie at first. The y +- is flipped, relative to the direction of the rotation, and the axis are flipped the conventional way:
What this really means is that the axis look like this:

y- ========= ROBOT ========= +y
               |
               |
               |arm
               |
               |
               x+

The reason for this is because the camera is oriented so that on screen, the arm starts on the left and faces right.
    This means that the y+ (pixels) direction is the counterclockwise movement of a servo, and y- (pixels) direction is the clockwise movement.
    The x+ movement (pixels) is the forward movement of the arm, and vice versa

    Thus, this translates to: x+ direction (pixels) correlates to the x+ direction of the arm (cartesian)
                      and the y+ direction (pixels) correlates to the y+ direction of the arm (cartesian)

Now, since the y+ direction moves the robot counterclockwise, and the servo is in a negative angle when moving counterclockwise, you will see sign changes in some cartesian calculations.
This is the reason for that sign change. It is all to make moving more intuitive, and has everything to do with camera positioning and hardware silliness.
"""
pos  = {'rotation': 0.0, 'stretch': 0.0, 'height': 0.0, 'wrist': 0.0, 'grabber': 0.0, 'touch': 0, 'x': 0.0, 'y': 0.0}  #Everything about the robot. X and Y are derived cartesian coordinates.
home = {'rotation': 0.0, 'stretch': V.stretchMax / 2, 'height': V.heightMax, 'wrist': 0}                     #A preset position, used with the moveTo() function
stretchMin      = 0.0
stretchMax      = 210.0
heightMin       = -180.0
heightMax       = 150.0
rotationMin     = -90.0
rotationMax     = 90.0
handRotMin      = -90.0
handRotMax      = 90.0
handAngleOpen   = 25.0
handAngleClose  = 70.0




def setPosition(toRotation, toStretch, toHeight, toWrist):
    pos['rotation'] = toRotation
    pos['stretch'] = toStretch
    pos['height'] = toHeight
    pos['wrist'] = toWrist
    moveTo()


def setGrabber(value):
    sleep(.1)
    pos['grabber'] = value
    sendVariable('c', int(value))
    sleep(.03)
    #print "setGrabber(", locals().get("args"), ") Robot returned ", getOutput("grabber"), "about the grabber."


def setPolarPosition(x, y):
    """

    :param x: does stuff
    :param y: oes other stuff
    Polar equations:
        R = sqrt(x^2+y^2)
        theta = tan^-1(abs(y/x))
    """
    radius = (x ** 2.0 + y ** 2.0) ** .5  #R = sqrt(x^2+y^2)
    theta  = math.degrees(math.atan2(y  , x ))

    pos['rotation'] = -theta
    pos['stretch']  = radius

    moveTo()


def sendVariable(name, value):
    sleep(.03)
    #ser1.write('%s:%s' % (name, int(round(value)) ) )
    ser1.write('%s:%s' % (name, round(value, 2) ))


def moveTo(**kwargs):
    """General command for moving robot
    ALL THIS FUNCTION DOES IS TELL THE ROBOT TO MOVE TO THE CURRENT POS POSITION.
    The inputs are simply a fast way to change the pos position, THEN have it move there. Using the setPosition then moveTo will still work.
    inputs:
        Any pos argument will be sent automaticall to robot
            rotation
            stretch
            height
            wrist
            grabber
        Settings:
            relative (defaults to True, has to do with whether this movement is RELATIVE to the robots current position)
            waitForRobot (doesn't work yet. Will eventually wait for the robot to complete its movements by querying the robot. Defaults to false)
        Cartesian: IF THERE ARE CARTESIAN COORDINATES, IT WILL IGNORE ANY STRETCH AND ROTATION ARGUMENTS! Also, Cartesian coordinates are coordinate and placed in the pos command.
                   If only an x or y is in the arguments, it will set the position to the new x and y with the old (other) coordinate, moving it horizontally or vertically only.
            x
            y
    """
    #ser1.write(chr(0xFF) + chr(0xAA) + chr(pos['rotation'] >> 8 & 0xff) + chr(pos['rotation'] & 0xff) + chr(pos['stretch'] >> 8 & 0xff) + chr(pos['stretch'] & 0xff) + chr(pos['height'] >> 8 & 0xff) + chr(pos['height'] & 0xff) + chr(pos['wrist'] >> 8 & 0xff) + chr(pos['wrist'] & 0xff) + chr(pos['grabber']))
    relative = kwargs.get('relative', True)             #A 'relative' is when I send moveTo(rotation = 3) and the robot moves 3, instead of moving to POSITION 3. DEFAULTS TRUE
    waitFor  = kwargs.get('waitForRobot', False)    #A variable meant to wait for the robot to respond to a message before continuing anything else.

    #HANDLE ANY CARTESIAN COORDINATE COMMANDS
    if any(coords in kwargs for coords in ('x', 'y')):  #If either x or y are in kwargs, then do cartesian coordinate calculations on pos
        if relative:
            setPolarPosition(kwargs.get('x', 0) + pos['x'], kwargs.get('y', 0) - pos['y'])
        else:  #For things that are not relative, it is expected for there to be both an X and a Y value
            setPolarPosition(kwargs['x'], kwargs['y'])

    #HANDLE ANY OTHER COMMANDS, INCLUDING POLAR COMMANDS
    for name, value in kwargs.items():  #Cycles through any variable that might have been in the kwargs. This is any position command!

        if name in pos:  #If it is a position statement.
            if relative:
                pos[name] += value
            else:
                pos[name] = value

    constrainPos(pos)  #Make sure the robot is not exceeding it's limits.

    #SEND INFORMATION TO ROBOT AND UPDATE CARTESIAN COORDINATES TO MATCH
    try:
        sendVariable('r', pos['rotation'])
        sendVariable('s', pos['stretch' ])
        sendVariable('h', pos['height'  ])
        sendVariable('w', pos['wrist'   ])

        pos['x'] = pos['stretch'] * math.cos(math.radians(pos['rotation']))
        pos['y'] = -pos['stretch'] * math.sin(math.radians(pos['rotation']))
        #print "moveTo(XXX): Position: ", pos
    except:
        print "moveTo(", locals().values(), "): Failed to send moveTo command to Robot!"

    #EITHER WAIT TILL ROBOT STOPS MOVING, OR DO A TINY SLEEP COMMAND. THIS IS DEPENDENT ON THE KWARGS.
    if waitFor:
        #sleep(.075)  #Give the robot time to process the inputs (not proven to be necessary...)
        waitForRobot()
    else:
        sleep(.1)


def waitForRobot():
    """
        Checks if the robot is currently moving,
        by sending Serial 'gets' to see what position
        the robot is currently at.
        If it gets 2 that are within a certain tolerance,
        it stops.
    """
    stillMoving  = True
    initialPos   = getOutput('all')
    if initialPos is None:      #IF ROBOT NOT CONNECTED
        print "waitForRobot(", locals().get("args"), "): NoneType was returned from getOutput() while obtaining initialPos. Continuing."
        return
    timer = Common.Timer(3)  #Wait 3 seconds for a response

    while stillMoving:
        finalPos   = getOutput('all')
        if finalPos is None:    #IF ROBOT NOT CONNECTED
            print "waitForRobot(", locals().get("args"), "): NoneType was returned from getOutput() while obtaining finalPos. Continuing."
            return

        #Timer Functions: Shouldn't actually be necessary, since the only part to fail would be getOutput(). Remove?
        if timer.timeIsUp():
            print "waitForRobot(", locals().get("args"), "): Robot still moving after ", timer.currentTime, "seconds. Continuing."
            return

        #ACTUALLY DO THE MOVEMENT DETECTION...
        stillMoving = False
        for name, value in initialPos.items():  #If any of the values have a difference larger than tolerance, then this will make stillMoving True and check once more.
            if not (abs(initialPos[name] - finalPos[name]) <= V.stationaryTolerance or abs(finalPos[name] - initialPos[name]) <= V.stationaryTolerance):
                stillMoving = True
        initialPos = finalPos


def constrainPos(position):  #Make sure that the pos function is within all limits, and constrain it if it is not
    global pos
    clamp = lambda n, minn, maxn: max(min(maxn, n), minn)  #clamp(number, min, max)
    pos         = {'rotation': 0.0, 'stretch': 0.0, 'height': 0.0, 'wrist': 0.0, 'grabber': 0.0, 'touch': 0, 'x': 0.0, 'y': 0.0}
    rotation    = position.get("rotation", -.1)
    stretch     = position.get("stretch", -.1)
    height      = position.get("height", -.1)
    wrist       = position.get("wrist", -.1)

    rotation    = clamp(rotation, V.rotationMin, V.rotationMax)
    stretch     = clamp(stretch, V.stretchMin, stretchMax)
    height      = clamp(height, V.heightMin, V.heightMax)
    wrist       = clamp(wrist, V.handRotMin, V.handRotMax)

    if not rotation == position["rotation"] and not position["rotation"] == -.1:
        print "constrainPos(", locals().get("args"), "): Constrained rotation to", rotation, "from ", position["rotation"]
        
    if not stretch == position["stretch"] and not position["stretch"] == -.1:
        print "constrainPos(", locals().get("args"), "): Constrained stretch to", stretch, "from ", position["stretch"]
    
    if not height == position["height"] and not position["height"] == -.1:
        print "constrainPos(", locals().get("args"), "): Constrained height to", height, "from ", position["height"]
    
    if not wrist == position["wrist"] and not position["wrist"] == -.1:
        print "constrainPos(", locals().get("args"), "): Constrained wrist to", wrist, "from ", position["wrist"]


    pos         = {'rotation': rotation, 'stretch': stretch, 'height': height, 'wrist': wrist, 'grabber': position["grabber"], 'touch': position["touch"], 'x': position["x"], 'y': position["y"]}


def getOutput(outputType):
    """
        Type is an integer, which sends for certain information from the arduino.
        0: returns 'Arduino r:? s:? w:? and so on for each individual server.
        1: Rotation
        2: stretch
        3: height
        4: wrist
        5: grabber
    """
    sendFor = {'all': 0, 'rotation': 1, 'stretch': 2, 'height': 3, 'wrist': 4, 'grabber': 5, 'touch': 6}
    sendVariable('g', sendFor[outputType])
    read = ''

    timer = Common.Timer(3)  #Wait 3 seconds for a response

    while True:
        #TIMER/ERROR HANDLING FUNCTIONS:
        timer.wait(.1)
        if timer.timeIsUp():
            print "getOutput(", locals().get("args"), "): No response heard from robot in", timer.currentTime, "seconds. Continuing."
            return None

        #RUN ACTUAL CODE
        read += ser1.readall()
        if '\n' in read and '}' in read:
            read = read[read.index('{'): read.index('}')+1]
            break
    try:
        return literal_eval(read)  #when it works put ser1.inWaiting() in () of readline
    except Exception:
        print "ERROR: getOutput(", locals().get("args"), "): Could not perform literal_eval() on value ", read, ". Continuing."
        return None


def getPosArgsCopy(**kwargs):
    currentPosition = {}
    #If no kwargs sent over, then record all positional arguments.
    dontRecord = kwargs.get("dontRecord", [])
    onlyRecord = kwargs.get("onlyRecord", pos.copy())  #If there is no onlyRecord, then you want to record everything (except dont record)

    for key in pos.keys():  #Go over every key in position, and see if it is mentioned in the **args. If it is, remove it.
        if key in onlyRecord and not key in dontRecord:
            currentPosition[key] = pos[key]


    return currentPosition

