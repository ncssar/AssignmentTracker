############################################################################
#
#  main.py - main entry point for AssignmentTracker app
#
#  AssignmentTracker developed for Nevada County Sheriff's Search and Rescue
#    Copyright (c) 2020 Tom Grundy
#
#  http://github.com/ncssar/AssignmentTracker
#
#  Contact the author at nccaves@yahoo.com
#   Attribution, feedback, bug reports and feature requests are appreciated
#
#  REVISION HISTORY
#-----------------------------------------------------------------------------
#   DATE   | AUTHOR | VER |  NOTES
#-----------------------------------------------------------------------------
#
# #############################################################################

__version__ = '1.0'

# perform any calls to Config.set before importing any kivy modules!
# (https://kivy.org/docs/api-kivy.config.html)
from kivy.config import Config
Config.set('kivy','keyboard_mode','system')
Config.set('kivy','log_dir','log')
Config.set('kivy','log_enable',1)
Config.set('kivy','log_level','info')
Config.set('kivy','log_maxfiles',5)
Config.set('graphics','width','505')
Config.set('graphics','height','800')

import time
import csv
import os
import sys
import copy
import shutil
import sqlite3
import re
from datetime import datetime,timezone
# import requests
# from requests.exceptions import Timeout
import json
from functools import partial
import urllib.parse
import certifi # attempt to fix SSL shared-token problem on Android
# from plyer import wifi
# import pusher

# # database interface module shared by this app and the assignmentTracker_api
from assignmentTracker_db import *

import kivy
kivy.require('1.9.1')

from kivy.app import App
from kivy.lang import Builder
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.button import Button
from kivy.uix.recyclegridlayout import RecycleGridLayout
from kivy.uix.behaviors import FocusBehavior
from kivy.uix.recycleview.layout import LayoutSelectionBehavior
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition, SlideTransition
from kivy.uix.recyclegridlayout import RecycleGridLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.switch import Switch
from kivy.uix.checkbox import CheckBox
from kivy.uix.image import Image
from kivy.uix.popup import Popup
from kivy.uix.dropdown import DropDown
from kivy.uix.textinput import TextInput
from kivy.properties import BooleanProperty, ListProperty, StringProperty, ObjectProperty, NumericProperty
from kivy.clock import Clock
from kivy.utils import platform
from kivy.core.window import Window

# custom version of kivy/network/urlrequest.py to allow synchronous (blocking) requests
from urlrequest_tmg import UrlRequest

from kivy.logger import Logger

# if platform in ('android'):
#     from jnius import cast
#     from jnius import autoclass
    
#     # android pyjnius stuff, used for download and for FLAG_KEEP_SCREEN_ON
#     Environment=autoclass('android.os.Environment')
#     Activity=autoclass('android.app.Activity')
#     PythonActivity=autoclass('org.kivy.android.PythonActivity')
#     View = autoclass('android.view.View') # to avoid JVM exception re: original thread
#     Params = autoclass('android.view.WindowManager$LayoutParams')
#     mActivity=PythonActivity.mActivity
#     Context=autoclass('android.content.Context')
#     DownloadManager=autoclass('android.app.DownloadManager')
#     ConnectivityManager=autoclass('android.net.ConnectivityManager')
#     WifiInfo=autoclass('android.net.wifi.WifiInfo')
#     con_mgr=mActivity.getSystemService(Activity.CONNECTIVITY_SERVICE)
#     wifi_mgr=mActivity.getSystemService(Activity.WIFI_SERVICE)

#     # SSL fix https://github.com/kivy/python-for-android/issues/1827#issuecomment-500028459    
#     os.environ['SSL_CERT_FILE']=certifi.where()
    
if platform in ('win'):
    import subprocess

# def sortSecond(val):
#     return val[1]

# def utc_to_local(utc_dt,tz=None):
#     return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=tz)

# def toast(text):
#     if platform in ('android'):
#         PythonActivity.toastError(text)
#     else:
#         Logger.info("TOAST:"+text)

class assignmentTrackerApp(App):
    def build(self):
        Logger.info("build starting...")
        Logger.info("platform="+str(platform))
        # # from https://pastebin.com/5e7ymKTU
        # Window.bind(on_request_close=self.on_request_close)
        # Window.bind(on_keyboard=self.on_keyboard)
        self.defaultTextHeightMultiplier=0.7
        self.gui=Builder.load_file('main.kv')
        self.teamsList=[]
        self.assignentsList=[]
        self.sm=ScreenManager()
        self.pairingDetailBeingShown=[]
        self.pairingHistoryRVList=[1,2,3,4,5]
        self.apiOKText="<h1>AssignmentTracker Database API</h1>"

        self.lan=False
        self.cloud=False
        self.localhost=False

        self.device='SITUATION UNIT'
        self.callsignPool=list(map(str,range(101,200)))
        self.assignmentNamePool=[chr(a)+chr(b) for a in range(65,91) for b in range(65,91)] # AA..AZ,BA..BZ,..

        # for each screen, example myScreen1 as instance of class myScreen:
        # 1. define myScreen in .kv
        # 2. class myScreen(Screen) - define any needed properties
        # 3. self.sm.add_widget(myScreen(name='myScreen1'))
        # 4. self.myScreen1=self.sm.get_screen('myScreen1')
        self.sm.add_widget(TeamsScreen(name='teamsScreen'))
        self.teamsScreen=self.sm.get_screen('teamsScreen')

        self.teamsScreen.ids.deviceHeader.ids.deviceLabel.text=self.device

        self.sm.add_widget(AssignmentsScreen(name='assignmentsScreen'))
        self.assignmentsScreen=self.sm.get_screen('assignmentsScreen')

        self.assignmentsScreen.ids.deviceHeader.ids.deviceLabel.text=self.device

        self.sm.add_widget(NewTeamScreen(name='newTeamScreen'))
        self.newTeamScreen=self.sm.get_screen('newTeamScreen')

        self.sm.add_widget(NewAssignmentScreen(name='newAssignmentScreen'))
        self.newAssignmentScreen=self.sm.get_screen('newAssignmentScreen')

        self.sm.add_widget(NewPairingScreen(name='newPairingScreen'))
        self.newPairingScreen=self.sm.get_screen('newPairingScreen')

        self.sm.add_widget(PairingDetailScreen(name='pairingDetailScreen'))
        self.pairingDetailScreen=self.sm.get_screen('pairingDetailScreen')

        self.assignedTeamsCount=0
        self.unassignedTeamsCount=0
        self.assignedAssignmentsCount=0
        self.unassignedAssignmentsCount=0

        self.lanServer="https://192.168.1.20:5000"
        # self.cloudServer="http://127.0.0.1:5000" # localhost, for development
        self.cloudServer="https://nccaves.pythonanywhere.com"
        self.localhostServer="http://127.0.0.1:5000"
        
        self.container=BoxLayout(orientation='vertical')
        # self.container.add_widget(self.topbar)
        self.container.add_widget(self.sm)

        # do the rest of the startup after GUI is launched:
        #  (this method is recommended in some posts, and is more reliable
        #   than on_start which runs before the main loop starts, meaning
        #   code during on_start happens with a frozen white GUI; but it also
        #   has a race condition - if you call it too soon, you get a crazy GUI)
        Clock.schedule_once(self.startup,2)

        return self.container

    def startup(self,*args,allowRecoverIfNeeded=True):
        # perform startup tasks here that should take place after the GUI is alive:
        # - check for connections (cloud and LAN(s))
        Logger.info("startup called")
        self.initPopup=self.textpopup(title='Please Wait',text='Checking connections...',size_hint=(0.9,0.3))
        self.getAPIKeys()
        self.check_connectivity()
        # these are all asynchronous requests, so, wait until there is an answer (or timeout) from each
        # r=self.checkForLAN()
        # self.lan=str(r).startswith(self.apiOKText)
        # Logger.info("checkForLAN response: "+str(r))
        # if self.lan:
        #     self.cloud=False # if LAN is responding, don't use the cloud and don't bother checking
        # else:
        #     r=self.checkForCloud()
        #     Logger.info("checkForCloud response: "+str(r))
        #     self.cloud=str(r).startswith(self.apiOKText)
        r=self.checkForLocalhost()
        Logger.info("checkForLocalhost response: "+str(r))
        self.localhost=str(r).startswith(self.apiOKText)
        Logger.info("LAN:"+str(self.lan)+" cloud:"+str(self.cloud)+" localhost:"+str(self.localhost))
        self.initPopup.dismiss()

        if not (self.lan or self.cloud or self.localhost):
            Logger.error("ABORTING - no hosts were found.")
            sys.exit()

        tdbInit()
        # self.cloudInit()
        self.localhostJoin(init=True)

        # self.pusher_appid=None
        # self.pusher_key=None
        # self.pusher_secret=None
        # self.pusher_cluster=None
        # self.pusher_appid=os.getenv('TRACKER_PUSHER_APPID')
        # self.pusher_key=os.getenv('TRACKER_PUSHER_KEY')
        # self.pusher_secret=os.getenv('TRACKER_PUSHER_SECRET')
        # self.pusher_cluster=os.getenv('TRACKER_PUSHER_CLUSTER')

        # self.pusher_client = pusher.Pusher(
        #     app_id=self.pusher_appid,
        #     key=self.pusher_key,
        #     secret=self.pusher_secret,
        #     cluster=self.pusher_cluster,
        #     ssl=True)

        # some hardcoded initial data for development
        self.newTeam('101','Ground Type 1')
        # self.newTeam('102','K9 (HRD)')
        # self.newAssignment('AA','Ground Type 1')
        # self.newAssignment('AB','K9 (HBD)')
        # self.newAssignment('AG','K9 (HRD)')
        # self.newAssignment('AK','Ground Type 1')
        # self.newAssignment('AL','Ground Type 2')
        # self.newAssignment('ZZ','Ground Type 2')
        # self.pair('AA','101')
        # self.pair('AB','102')

        self.showTeams()

        # websockets: the first client to join will determine what http
        #  server should send websockets, and where those websockets should
        #  be sent (i.e. the reflector server).

        # try LAN http first.  If LAN server responds, it should be the one to
        #  send websockets, to reflector on the same LAN server.

        # if no LAN, try cloud http (pythonanywhere).  If cloud server responds,
        #  it should be the one to send websockets, to pusher.com.

        # if no LAN and no cloud, use localhost http.  If localhost http responds,
        #  it should be the one to send websockets, to localhost reflector.
        # (may change this in the future to always use localhost as the second
        #  server regardless of first server, in which case only the first
        #  server should send websockets)

        # the only time that websockets will be sent to localhost is when
        #  neither LAN nor cloud web hosts are responding.

    def cloudInit(self):
        if self.cloud:
            self.cloudRequest('api/v1/init','POST')

    def localhostJoin(self,init=False):
        if self.localhost:
            d={'NodeName':'RESOURCE UNIT'}
            if init:
                d['Init']=True
            self.localhostRequest('api/v1/join','POST',d,timeout=5) # make this a blocking call

# generic host-agnostic request and handlers

# if timeout (seconds) is specified, this will be a synchronous/blocking request:
#  - the event loop will be put on hold until there is a response or
#     the specified number of seconds has passed, whichever comes first
#  - the return value of this function will be the request response

# if timeout is not specified, this will be an asynchronous/non-blocking request: 
#  - the return value of this function will be the request object
#  - you will probably want to specify one or more custom callbacks
#     with the on_success/failure/response arguments; default callbacks
#     will be used for whichever callback arguments are not specified
    def request(self,host="",urlEnd="",method="GET",body=None,
            timeout=None,
            on_success=None,
            on_failure=None,
            on_error=None):
        on_success=on_success or self.request_callback
        on_failure=on_failure or self.request_callback
        on_error=on_error or self.request_callback
        if timeout: # don't use callbacks if this a synchronous request
            on_success=None
            on_failure=None
            on_error=None
        if not urlEnd.startswith('/'):
            urlEnd='/'+urlEnd
        url=host+urlEnd
        if type(body) is dict:
            body=json.dumps(body)
        Logger.info("request: "+str(url)+" "+str(method)+" body="+str(body)+" timeout="+str(timeout))
        headers={}
        headers['Authorization']='Bearer '+self.tracker_api_key
        if body:
            headers['Content-type']='application/json'
            headers['Accept']='text/plain'
        req=UrlRequest(url,
                # on_success=self.on_request_success,
                # on_failure=self.on_request_failure,
                # on_error=self.on_request_error,
                on_success=on_success,
                on_failure=on_failure,
                on_error=on_error,
                req_headers=headers,
                req_body=body,
                timeout=timeout,
                method=method,
                debug=True)
        if timeout: # synchronous request; return the response
            return req.result
        else: # asynchronous request; return the request
            return 'Asynchronous request has been sent.'

    # def on_request_success(self,request,result):
    def request_callback(self,request,result):
        headerStr=str(request.req_headers)
        headerStr=re.sub("Bearer [a-zA-Z0-9-_]+","Bearer <hidden>",headerStr)
        # Logger.info("on_cloudRequest_success called:")
        Logger.info("request_response_handler called: "+str(request.resp_status))
        Logger.info("  request was sent to "+str(request.url))
        Logger.info("    request body="+str(request.req_body))
        Logger.info("    request headers="+headerStr)
        Logger.info("  result="+str(result))

    def cloudRequest(self,urlEnd="",method="GET",body=None,**kwargs):
        return self.request(self.cloudServer,urlEnd,method,body,**kwargs)

    def lanRequest(self,urlEnd="",method="GET",body=None,**kwargs):
        return self.request(self.lanServer,urlEnd,method,body,**kwargs)

    def localhostRequest(self,urlEnd="",method="GET",body=None,**kwargs):
        return self.request(self.localhostServer,urlEnd,method,body,**kwargs)

    # this is the function that will be used most often:
    # if GET, send request only to primary server;
    # otherwise, send request to all servers in use
    def sendRequest(self,urlEnd="",method="GET",body=None,**kwargs):
        r=None
        if self.lan:
            r=self.lanRequest(urlEnd,method,body,**kwargs)
        if self.cloud:
            r=self.cloudRequest(urlEnd,method,body,**kwargs)
        if self.localhost:
            r=self.localhostRequest(urlEnd,method,body,**kwargs)
        return r

    def getAPIKeys(self):
        self.tracker_api_key="NONE"
        if platform in ('windows'):
            self.tracker_api_key=os.getenv('TRACKER_API_KEY')
            if self.tracker_api_key==None:
                self.tracker_api_key="NONE"
                Logger.info("TRACKER API key not found.")
                self.textpopup('TRACKER API Key was not found.\nThis session will not have access to the Tracker cloud account.')
            else:
                # security: don't write the key to the log file which can be copied to a different machine
                Logger.info("TRACKER API key read successfully.")

        elif platform in ('android'):
            # don't send keys.json with the apk; install it separately by some means
            with open('./keys.json','r',errors='ignore') as keyFile:
                data=json.load(keyFile)
                self.tracker_api_key=data["tracker_api_key"]

    def checkForLAN(self):
        print("calling checkForLAN")
        r=self.lanRequest("","GET",timeout=3)
        return r

    def checkForCloud(self):
        self.cloud=False
        print("calling checkForCloud")
        r=self.cloudRequest("","GET",timeout=5) # timeout 4 has actually been too short for initial wakeup
        return r

    def checkForLocalhost(self):
        print("calling checkForLocalhost")
        r=self.localhostRequest("","GET",timeout=2)
        return r

    def check_connectivity(self):
        self.ssid="None"
        if platform=='android':
            # in order to get the SSID, in Android 9+, ACCESS_COARSE_LOCATION
            #  permission in needed, and in Android 10, ACCESS_FILE_LOCATION
            #  is needed; they need to be in buildozer.spec, and until/unless
            #  the app is made to request permission through the GUI, location
            #  permission will have to be added through the android settings GUI
            #  after each install; but, it's not strictly critical to show the SSID.
            self.ssid=wifi_mgr.getConnectionInfo().getSSID()
            if self.ssid=="<unknown ssid>":
                self.ssid="None" # should probably check to see if mobile data or other connection
                # exists before telling the user that there is no connection, i.e.
                #  wifi is just a possible means of connection
            Logger.info("Active network:"+self.ssid)
        elif platform=='win':
            out=subprocess.check_output(['netsh','wlan','show','interfaces'])
            for line in str(out).replace('\\r','').split('\\n'):
                if ' SSID' in line:
                    Logger.info("SSID line found:"+line)
                    self.ssid=line.split(': ')[1]
    
    
# connection issues: we want to see this type of transcript:    
# [INFO   ] calling checkForCloud
# [INFO   ] ComboEdit.on_text called:<__main__.ComboEdit object at 0xc964e490>:
# [INFO   ] ComboEdit.on_options called:<__main__.ComboEdit object at 0xc964e490>:[]
# [INFO   ] options:[]
# [INFO   ] on_checkForCloud_success called: response=<h1>Tracker Database API</h1>
# <p>API for interacting with the sign-in databases</p>
# [INFO   ]   valid response detected; cloud connection established.
# [INFO   ] Requesting roster from cloud server...
# [INFO   ] on_roster_success called
# [INFO   ]   roster saved to ./roster.json
# [INFO   ] reading json roster file:./roster.json
# [INFO   ] opened...

# apparently, without Clock.tick() at the end of the success handler,
#  the roster loader doesn't think self.cloud is True yet, therefore it doesn't
#  request the latest roster from the cloud

    # def on_checkForCloud_success(self,request,result):
    #     Logger.info("on_checkForCloud_success called: response="+str(result))
    #     if 'AssignmentTracker Database API' in str(result):
    #         Logger.info("  valid response detected; cloud connection established.")
    #         self.cloud=True
    #         Clock.tick() # to make sure the status is immediately available
    
    # def on_checkForCloud_error(self,request,result):
    #     Logger.info("on_checkForCloud_error called:")
    #     Logger.info("  request was sent to "+str(request.url))
    #     Logger.info("    request body="+str(request.req_body))
    #     Logger.info("    request headers="+str(request.req_headers))
    #     Logger.info("  result="+str(result))

    def newTeam(self,name=None,resource=None):
        name=name or self.callsignPool.pop(0)
        if name in self.callsignPool:
            self.callsignPool.remove(name)
        resource=resource or self.newTeamScreen.ids.resourceSpinner.text
        r=tdbNewTeam(name,resource)
        # Logger.info('return from newTeam:')
        # Logger.info(r)
        self.sendRequest("api/v1/teams/new","POST",{'TeamName':name,'Resource':resource})
        self.updateNewTeamNameSpinner()
        self.buildLists()

    def newAssignment(self,name=None,intendedResource=None):
        name=name or self.assignmentNamePool.pop(0)
        if name in self.assignmentNamePool:
            self.assignmentNamePool.remove(name)
        intendedResource=intendedResource or self.newAssignmentScreen.ids.resourceSpinner.text
        r=tdbNewAssignment(name,intendedResource)
        # Logger.info('return from newAssignment:')
        # Logger.info(r)
        self.sendRequest("api/v1/assignments/new","POST",{'AssignmentName':name,'IntendedResource':intendedResource})
        self.updateNewAssignmentNameSpinner()
        self.buildLists()

    def updateNewTeamNameSpinner(self):
        self.newTeamScreen.ids.nameSpinner.values=self.callsignPool[0:8]
        self.newTeamScreen.ids.nameSpinner.text=self.callsignPool[0]
    
    def updateNewAssignmentNameSpinner(self):
        self.newAssignmentScreen.ids.nameSpinner.values=self.assignmentNamePool[0:8]
        self.newAssignmentScreen.ids.nameSpinner.text=self.assignmentNamePool[0]

    def buildLists(self):
        self.teamsList=tdbGetTeamsView()
        # self.teamsList=self.sendRequest("api/v1/teams/view",timeout=5)
        self.assignmentsList=tdbGetAssignmentsView()
        # self.assignmentsList=self.sendRequest("api/v1/assignments/view",timeout=5)
        Logger.info("teamsList:"+str(self.teamsList))
        Logger.info("assignmentsList:"+str(self.assignmentsList))
        self.updateCounts()
        # when to push tables over websockets?  Should the client be doing this at all?
        #  probably not - let the server do it on every change
        # tdbPushTables(self.teamsList,self.assignmentsList,self.teamsCountText,self.assignmentsCountText)

    # def pushAssignmentsTable(self):
    #     cols=["Assignment","Team","Status","Resource"]
    #     d=self.assignmentsList
    #     table='<table>\n<tr>{}</tr>'.format('\n'.join('<th>{}</th>'.format(i) for i in cols))
    #     table+='\n'.join(['<tr>{}</tr>'.format('\n'.join(['<td>{}</td>'.format(b) for b in i])) for i in d])
    #     table+='\n</table>'
    #     self.pusher_client.trigger('my-channel', 'assignmentsViewUpdate', table)

    def showTeams(self,*args):
        Logger.info('showTeams called')
        self.buildLists()                
        # recycleview needs a single list of strings; it divides into rows every nth element
        self.teamsScreen.teamsRVList=[]
        for entry in self.teamsList:
            row=copy.deepcopy(entry)
            # Logger.info('adding row to teamsRVList:'+str(row))
            self.teamsScreen.teamsRVList=self.teamsScreen.teamsRVList+row
        # Logger.info('built teamsRVList:'+str(self.teamsScreen.teamsRVList))
        self.sm.transition=NoTransition()
        self.sm.current='teamsScreen'

    def showAssignments(self,*args):
        Logger.info("showAssignments called")
        self.buildLists()             
        # recycleview needs a single list of strings; it divides into rows every nth element
        self.assignmentsScreen.assignmentsRVList=[]
        for entry in self.assignmentsList:
            row=copy.deepcopy(entry)
            self.assignmentsScreen.assignmentsRVList=self.assignmentsScreen.assignmentsRVList+row
        self.sm.transition=NoTransition()
        self.sm.current='assignmentsScreen'

    def updateCounts(self):
        Logger.info('updateCounts called')
        self.unassignedTeamsCount=len([x for x in self.teamsList if x[1]=='UNASSIGNED'])
        self.assignedTeamsCount=len(self.teamsList)-self.unassignedTeamsCount
        self.unassignedAssignmentsCount=len([x for x in self.assignmentsList if x[2]=='UNASSIGNED'])
        self.assignedAssignmentsCount=len(self.assignmentsList)-self.unassignedAssignmentsCount
        self.teamsCountText=str(self.assignedTeamsCount)+' Assigned,     '+str(self.unassignedTeamsCount)+' Unassigned'
        self.assignmentsCountText=str(self.assignedAssignmentsCount)+' Assigned,     '+str(self.unassignedAssignmentsCount)+' Unassigned'

        self.teamsScreen.ids.viewSwitcher.ids.teamsViewButton.text='[size=35]Teams\n[size=12]'+self.teamsCountText
        self.teamsScreen.ids.viewSwitcher.ids.teamsViewButton.line_height=0.7
        self.teamsScreen.ids.viewSwitcher.ids.assignmentsViewButton.text='[size=20]Assignments\n[size=12]'+self.assignmentsCountText
        self.teamsScreen.ids.viewSwitcher.ids.assignmentsViewButton.line_height=0.95
        
        self.assignmentsScreen.ids.viewSwitcher.ids.teamsViewButton.text='[size=20]Teams\n[size=12]'+self.teamsCountText
        self.assignmentsScreen.ids.viewSwitcher.ids.teamsViewButton.line_height=0.95
        self.assignmentsScreen.ids.viewSwitcher.ids.assignmentsViewButton.text='[size=35]Assignments\n[size=12]'+self.assignmentsCountText
        self.assignmentsScreen.ids.viewSwitcher.ids.assignmentsViewButton.line_height=0.7

    def showPairingDetail(self,assignmentName,teamName=None):
        Logger.info('showPairingDetail called:'+str(assignmentName)+' : '+str(teamName))
        if teamName:
            status=tdbGetTeamStatusByName(teamName)
        else:
            teamName='--'
            status='UNASSIGNED'
        self.pairingDetailScreen.ids.assignmentNameLabel.text=assignmentName
        self.pairingDetailScreen.ids.teamNameLabel.text=teamName
        self.pairingDetailScreen.ids.statusLabel.text=status
        self.pairingDetailBeingShown=[assignmentName,teamName]
        self.pairingDetailStatusUpdate()
        self.pairingDetailHistoryUpdate()
        self.sm.current='pairingDetailScreen'

    def pairingDetailStatusUpdate(self):
        teamName=self.pairingDetailBeingShown[1]
        if teamName=='--':
            return
        status=tdbGetTeamStatusByName(teamName)
        statusList=copy.copy(TEAM_STATUSES)
        statusList.remove(status)
        statusList.append('DONE')
        self.pairingDetailScreen.ids.statusSpinner.values=statusList
        currentIndex=TEAM_STATUSES.index(status)-1
        newIndex=currentIndex+1
        self.pairingDetailScreen.ids.statusSpinner.text=statusList[newIndex] # go to the next logical status by default

    def pairingDetailHistoryUpdate(self):
        [assignmentName,teamName]=self.pairingDetailBeingShown
        # get history from tdb, regardless of connections
        if teamName:
            history=[[x['Entry'],x['RecordedBy'],time.strftime('%H:%M',time.localtime(x['Epoch']))] for x in
                    tdbGetHistory(assignmentID=tdbGetAssignmentIDByName(assignmentName),teamID=tdbGetTeamIDByName(teamName))[::-1]]
        else:
            history=[[x['Entry'],x['RecordedBy'],time.strftime('%H:%M',time.localtime(x['Epoch']))] for x in
                    tdbGetHistory(assignmentID=tdbGetAssignmentIDByName(assignmentName))[::-1]]
        history=[y for x in history for y in x] # flattened list, needed by RecycleGridLayout
        self.pairingDetailScreen.ids.historyRV.data=[{'text': str(x)} for x in history]
      
    def showNewTeam(self,*args):
        Logger.info('showNewTeam called')
        self.updateNewTeamNameSpinner()
        self.sm.current='newTeamScreen'

    def showNewAssignment(self,*args):
        Logger.info('showNewAssignment called')
        self.updateNewAssignmentNameSpinner()
        self.sm.current='newAssignmentScreen'

    def showNewPairing(self,assignmentName):
        Logger.info('showPairing called: '+str(assignmentName))
        intendedResource=tdbGetAssignmentIntendedResourceByName(assignmentName)
        label=assignmentName+' : '+intendedResource
        status=tdbGetAssignmentStatusByName(assignmentName)
        if status=='UNASSIGNED':
            label=label+'\n'+status
        else:
            label=label+'\nASSIGNED TO team(s)'
        self.newPairingScreen.ids.changePairingLabel.text=label
        part1=[] # unassigned teams, same resource type as intended resource
        part2=[] # unassigned teams, other resource types
        part3=[] # assigned teams, same resource type as intended resource
        part4=[] # assigned teams, other resource types
        for team in self.teamsList:
            if team[1]=='UNASSIGNED':
                entryText=team[0]+' : '+team[2]+'   '+team[1]
                if team[2]==intendedResource:
                    part1.append(entryText)
                else:
                    part2.append(entryText)
            else:
                entryText=team[0]+' : '+team[2]+'  ASSIGNED to '+team[3]
                if team[2]==intendedResource:
                    part3.append(entryText)
                else:
                    part4.append(entryText)
        theList=part1+part2+part3+part4
        self.newPairingScreen.ids.teamSpinner.values=theList
        if theList:
            self.newPairingScreen.ids.teamSpinner.text=theList[0]
        else:
            # could show a warning here and disallow pairing before the screen raises
            self.newPairingScreen.ids.teamSpinner.text='No teams defined'
        self.sm.current='newPairingScreen'

    def pair(self,assignmentName=None,teamName=None):
        if not assignmentName:
            assignmentName=self.pairingDetailBeingShown[0]
        if not teamName:
            teamName=self.newPairingScreen.ids.teamSpinner.text.split()[0]
        Logger.info("pairing assignment "+str(assignmentName)+" with team "+str(teamName))
        aid=tdbGetAssignmentIDByName(assignmentName)
        tid=tdbGetTeamIDByName(teamName)
        tdbPair(aid,tid)
        tdbSetTeamStatusByName(teamName,'ASSIGNED')
        tdbSetAssignmentStatusByName(assignmentName,'ASSIGNED')
        self.sendRequest("api/v1/pairings/new","POST",{"AssignmentID":aid,"TeamID":tid})
        # avoid sending multiple requests back to back, since this can create race conditions
        #  and html flickers with clients receiving multiple different websocket messages
        #  in rapid succession; instead, make the new pairings API handler set the team
        #  and assignment statuses and then just do one websocket send 
        # self.sendRequest("api/v1/teams/"+str(tid)+"/status","PUT",{"NewStatus":"ASSIGNED"})
        # self.sendRequest("api/v1/assignments/"+str(aid)+"/status","PUT",{"NewStatus":"ASSIGNED"})

    def changeTeamStatus(self,teamName=None,status=None):
        if not teamName:
            teamName=self.pairingDetailBeingShown[1]
        if not status:
            status=self.pairingDetailScreen.ids.statusSpinner.text
        if status=='DONE': # changing to DONE from pairing detail screen will 'close out' the current pairing
            [assignmentName,teamName]=self.pairingDetailBeingShown
            # 1. set pairing status to PREVIOUS
            pairingID=tdbGetPairingIDByNames(assignmentName,teamName)
            tdbSetPairingStatusByID(pairingID,'PREVIOUS')
            self.sendRequest("api/v1/pairings/"+str(pairingID)+"/status","PUT",{"NewStatus":"PREVIOUS"})
            # 2. set team status to UNASSIGNED
            teamID=tdbGetTeamIDByName(teamName)
            tdbSetTeamStatusByID(teamID,'UNASSIGNED')
            self.sendRequest("api/v1/teams/"+str(teamID)+"/status","PUT",{"NewStatus":"UNASSIGNED"})
            # 3. if this was the only current pairing involving the paired assignment,
            #  set that assignment's status to UNASSIGNED
            others=tdbGetPairingsByAssignment(tdbGetAssignmentIDByName(assignmentName),currentOnly=True)
            Logger.info('others:'+str(others))
            if not others:
                assignmentID=tdbGetAssignmentIDByName(assignmentName)
                tdbSetAssignmentStatusByID(assignmentID,'UNASSIGNED')
                self.sendRequest("api/v1/assignments/"+str(assignmentID)+"/status","PUT",{"NewStatus":"UNASSIGNED"})
            self.showAssignments()
        else:
            Logger.info('changing status for team '+str(teamName)+' to '+str(status))
            teamID=tdbGetTeamIDByName(teamName)
            tdbSetTeamStatusByID(teamID,status)
            self.sendRequest("api/v1/teams/"+str(teamID)+"/status","PUT",{"NewStatus":str(status)})
            self.pairingDetailScreen.ids.statusLabel.text=status
            self.pairingDetailStatusUpdate()
            self.pairingDetailHistoryUpdate()

    def textpopup(self, title='', text='', buttonText='OK', on_release=None, size_hint=(0.8,0.25)):
        Logger.info("textpopup called; on_release="+str(on_release))
        box = BoxLayout(orientation='vertical')
        box.add_widget(Label(text=text))
        if buttonText is not None:
            mybutton = Button(text=buttonText, size_hint=(1, 0.3))
            box.add_widget(mybutton)
#         popup = Popup(title=title, content=box, size_hint=(None, None), size=(600, 300))
        popup = Popup(title=title, content=box, size_hint=size_hint)
#         if not on_release:
#             on_release=self.stop
        if buttonText is not None:
            mybutton.bind(on_release=popup.dismiss)
            if on_release:
                mybutton.bind(on_release=on_release)
        popup.open()
        return popup # so that the calling code can close the popup
        
            

# from https://kivy.org/doc/stable/api-kivy.uix.recycleview.htm and http://danlec.com/st4k#questions/47309983


# prevent keyboard on selection by getting rid of FocusBehavior from inheritance list
class SelectableRecycleGridLayout(LayoutSelectionBehavior,
                                  RecycleGridLayout):
    ''' Adds selection and focus behaviour to the view. '''


class SelectableLabel(RecycleDataViewBehavior, Label):
    ''' Add selection support to the Label '''
    index = None
    selected = BooleanProperty(False)
    selectable = BooleanProperty(True)
    bg=ListProperty([0,0,0,0])

    def refresh_view_attrs(self, rv, index, data):
        ''' Catch and handle the view changes '''
        self.index = index
        return super(SelectableLabel, self).refresh_view_attrs(
            rv, index, data)

    def on_touch_down(self, touch):
        if super(SelectableLabel, self).on_touch_down(touch):
            return True
        if self.collide_point(*touch.pos) and self.selectable:
            if theApp.sm.current=='assignmentsScreen':
                colCount=theApp.assignmentsScreen.ids.assignmentsLayout.cols
                Logger.info("Assignments list item tapped: index="+str(self.index)+":"+str(theApp.assignmentsScreen.ids.assignmentsRV.data[self.index]))
                rowNum=int(self.index/colCount)
                row=theApp.assignmentsScreen.ids.assignmentsRV.data[rowNum*colCount:(rowNum+1)*colCount]
                Logger.info("   selected row:"+str(row))
                assignmentName=str(row[0]["text"])
                teamName=str(row[1]["text"])
                if teamName=='--':
                    teamName=None
                # bg=theApp.assignmentsScreen.ids.assignmentsRV.data[self.index]['bg']
                # if bg[1]==0:
                #     newBg=(0,0.8,0.1,0.7)
                # else:
                #     newBg=(0,0,0,0)
                # for i in list(range(rowNum*colCount,(rowNum+1)*colCount)):
                #     theApp.assignmentsScreen.ids.assignmentsRV.data[i]['bg']=newBg
                # theApp.assignmentsScreen.ids.assignmentsRV.refresh_from_data()
                theApp.showPairingDetail(assignmentName,teamName)
                return True
        #     else:
        #         return self.parent.select_with_touch(self.index, touch)

    def apply_selection(self, rv, index, is_selected):
        ''' Respond to the selection of items in the view. '''
        self.selected = is_selected
        if is_selected:
            Logger.info("selection changed to {0}".format(rv.data[index]))
            [name,id]=rv.data[index]['text'].split(" : ")
            theApp.keyDown(id[-1]) # mimic the final character of the ID, to trigger the lookup
            theApp.typed=id
            theApp.keyDown(name,fromLookup=True) # mimic the name being tapped from the keypad screen
            Clock.schedule_once(self.clear_selection,0.5) # aesthetic - to prepare for the next lookup
    
    def clear_selection(self,*args):
        self.parent.clear_selection()


class TeamsScreen(Screen):
    teamsRVList=ListProperty([])


class AssignmentsScreen(Screen):
    assignmentsRVList=ListProperty([])


class PairingDetailScreen(Screen):
    pairingDetailCurrentRVList=ListProperty([])
    pairingDetailPreviousRVList=ListProperty([])


class NewTeamScreen(Screen):
    pass


class NewAssignmentScreen(Screen):
    pass


class NewPairingScreen(Screen):
    pass


if __name__ == '__main__':
    theApp=assignmentTrackerApp()
    theApp.run()
    