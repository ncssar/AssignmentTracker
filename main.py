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
import configparser
import urllib.parse
import certifi # attempt to fix SSL shared-token problem on Android
# from plyer import wifi
# import pusher
from sartopo_python import SartopoSession

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
from kivy.uix.spinner import Spinner
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

def toast(text):
    if platform in ('android'):
        PythonActivity.toastError(text)
    else:
        Logger.info("TOAST:"+text)

# SITU_DEPLOYMENT_CHECKLIST='''
#     one-liner
#     two-liner'''

NEW_PAIRING_POPUP_TEXT='''
    SITU should take the following actions:

    1. Edit the SARTopo Assignment object:
      1a. Set 'Number' to Team #
      1b. Set or update 'Resource Type'
      1c. Set or update 'Team Size'
      1d. Set 'Status' to INPROGRESS
    2. Add a medical marker if needed:
      2a. Use the correct Style
      2b. Set 'Comments' to Team # (leave 'Label' blank)
      2c. Set 'Folder' to 'Medical' (Add Folder if needed)
    3. Keep the paper 104 in a 'processed' stack'''

COMPLETED_PAIRING_POPUP_TEXT='''
    SITU should take the following actions:
    
    1. Edit the SARTopo Assignment object:
      1a. Set 'Number' to blank
      1b. Set 'Status' to COMPLETED
    2. Delete related medical marker, if any
    3. Deliver paper 104 to RESU'''

ROLES=[
    'SITUATION UNIT',
    'RESOURCE UNIT',
    'OPERATIONS CHIEF',
    'PLANNING CHIEF',
    'OBSERVER']

# NOTE regarding ID values:
# tid = team ID; aid = assignment ID; pid = pairing ID
# these values are set to -1 when created on a client, or a positive integer when
#  created on the host.  The positive integer id is sent to all clients
#  as part of the new object http request response, whether the request was made
#  by the creating client, or by sync.  So, if id is -1 in steady state, either host
#  communication has been lost, or the host had an error, or there is no host.

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
        self.lastSyncTimeStamp=0
        self.syncInterval=5
        self.resourceTypes=[ # matches sartopo assignment resource choices
            'GROUND',
            'GROUND-1',
            'GROUND-2',
            'GROUND-3',
            'DOG',
            'DOG-TRAIL',
            'DOG-AREA',
            'DOG-HRD',
            'OHV',
            'WATER',
            'MOUNTED',
            'AIR']
        self.lan=False
        self.cloud=False
        self.localhost=False
        self.stsConfigpath=('C:\\Users\\caver\\Documents\\GitHub\\sts_caver456.ini')
        self.stsUrl=None
        self.sts=None
        self.newTeamCreatedFromNewPairing=None
        self.screenStack=['start']
        self.lastPairingDetailTeamName=None
        self.lastPairingDetailAssignmentName=None

        self.nodeName='OBSERVER'
        self.teamNamePool=list(map(str,range(101,200)))
        self.assignmentNamePool=[chr(a)+chr(b) for a in range(65,91) for b in range(65,91)] # AA..AZ,BA..BZ,..
        self.medicalIconSrc='./img/medical-icon-31.png'

        # for each screen, example myScreen1 as instance of class myScreen:
        # 1. define myScreen in .kv
        # 2. class myScreen(Screen) - define any needed properties
        # 3. self.sm.add_widget(myScreen(name='myScreen1'))
        # 4. self.myScreen1=self.sm.get_screen('myScreen1')
        self.sm.add_widget(TeamsScreen(name='teamsScreen'))
        self.teamsScreen=self.sm.get_screen('teamsScreen')

        self.teamsScreen.ids.deviceHeader.ids.deviceLabel.text=self.nodeName

        self.sm.add_widget(AssignmentsScreen(name='assignmentsScreen'))
        self.assignmentsScreen=self.sm.get_screen('assignmentsScreen')

        self.assignmentsScreen.ids.deviceHeader.ids.deviceLabel.text=self.nodeName

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

        self.lanServer="http://192.168.1.20:5000"
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
        
        self.initPopup=self.textpopup(title='Please Wait',text='Initializing - please wait...',buttonText=None,size_hint=(0.9,0.3))
        Clock.schedule_once(self.startup,1) # 0.5 was not enough, resulting in white GUI until startup completes

        return self.container

    def startup(self,*args,allowRecoverIfNeeded=True):
        # perform startup tasks here that should take place after the GUI is alive:
        # - check for connections (cloud and LAN(s))
        Logger.info("startup called")
        self.getAPIKeys()
        self.check_connectivity()
        r=self.checkForLAN()
        self.lan=str(r).startswith(self.apiOKText)
        Logger.info("checkForLAN response: "+str(r))
        if self.lan:
            self.cloud=False # if LAN is responding, don't use the cloud and don't bother checking
        else:
            # sometimes pythonanywhere won't wake up for the first request even after a 5 second timeout
            #  so, try a first request with shorter timeout; if that times out, try another request
            r=self.checkForCloud(2)
            Logger.info("checkForCloud response: "+str(r))
            self.cloud=str(r).startswith(self.apiOKText)
            if not self.cloud:
                r=self.checkForCloud(5)
                Logger.info("checkForCloud response: "+str(r))
                self.cloud=str(r).startswith(self.apiOKText)
                if not self.cloud:
                    r=self.checkForLocalhost()
                    Logger.info("checkForLocalhost response: "+str(r))
                    self.localhost=str(r).startswith(self.apiOKText)
        Logger.info("LAN:"+str(self.lan)+" cloud:"+str(self.cloud)+" localhost:"+str(self.localhost))
        self.initPopup.dismiss()

        if self.lan:
            self.connIconSrc='./img/lan-letters-icon-16.png'
        elif self.cloud:
            self.connIconSrc='./img/www-letters-icon-16.png'
        elif self.localhost:
            self.connIconSrc='./img/localhost.png'
        
        self.teamsScreen.ids.deviceHeader.ids.connButton.background_normal=self.connIconSrc
        self.assignmentsScreen.ids.deviceHeader.ids.connButton.background_normal=self.connIconSrc

        if not (self.lan or self.cloud or self.localhost):
            Logger.error("ABORTING - no hosts were found.")
            sys.exit()

        tdbInit() # initialize the local database regardless of join type

        self.joinPopup()
        # self.cloudJoin(init=True)
        # self.localhostJoin(init=True)

        # some hardcoded initial data for development
        # self.newTeam('101','Ground Type 1')

        # self.showTeams()

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

    def joinPopup(self):
        box=BoxLayout(orientation='vertical')
        self.joinPopup_=PopupWithIcons(
                title='Join or Initialize',
                content=box,
                size_hint=(0.8,0.2),
                background_color=(0,0,0,0.5))
        self.joinPopup_.ids.iconBox.add_widget(Image(source=self.connIconSrc,width=30,size_hint_x=None))
        button=Button(text='Join existing incident')
        box.add_widget(button)
        button.bind(on_release=partial(self.join,False))
        button.bind(on_release=self.joinPopup_.dismiss)
        button=Button(text='Start a new incident')
        box.add_widget(button)
        button.bind(on_release=self.newIncidentConfirmPopup)
        self.joinPopup_.open()

    def newIncidentConfirmPopup(self,*args):
        okButton=Button(text='OK')
        okButton.disabled=True
        def okButtonDisabledUpdate(self,text):
            okButton.disabled=text==''
        box=BoxLayout(orientation='vertical')
        popup=PopupWithIcons(
                title='New incident - confirm',
                content=box,
                size_hint=(0.8,None), # relative to screen, not to joinPopup
                background_color=(0,0,0,0.5))
        label=WrappedLabel(text='Starting a new incident will reset the database for all connected users.\n\nIf you really want to start a new incident, enter the new incident name below:')
        box.add_widget(label)
        # popup.ids.theLabel.text='Starting a new incident will reset the database for all connected users.\n\nIf you really want to start a new incident, enter the new incident name below:'
        incidentName=TextInput(multiline=False,size_hint_y=None,height=30)
        incidentName.bind(text=okButtonDisabledUpdate)
        box.add_widget(incidentName)
        stsUrlBox=BoxLayout(orientation='horizontal',size_hint_y=None,height=35)
        stsUrlLabel=Label(text='SARTopo URL:',size_hint_x=0.4)
        stsUrlBox.add_widget(stsUrlLabel)
        stsUrlField=TextInput(multiline=False,size_hint_y=None,height=30)
        stsUrlBox.add_widget(stsUrlField)
        box.add_widget(stsUrlBox)
        okCancelBox=BoxLayout(orientation='horizontal',size_hint_y=None,height=50)
        def newIncidentAccept(*args):
            self.stsUrl=stsUrlField.text
            self.join(True)
        okButton.bind(on_release=newIncidentAccept)
        okButton.bind(on_release=popup.dismiss)
        okButton.bind(on_release=self.joinPopup_.dismiss)
        cancelButton=Button(text='Cancel')
        cancelButton.bind(on_release=popup.dismiss)
        okCancelBox.add_widget(okButton)
        okCancelBox.add_widget(cancelButton)
        box.add_widget(okCancelBox)
        popup.height=box.height+160
        popup.open()

    def joinAsPopup(self,*args):
        box=BoxLayout(orientation='vertical')
        self.joinAsPopup_=PopupWithIcons(
                title='Select a Role',
                content=box,
                size_hint=(0.8,0.2),
                background_color=(0,0,0,1))
        label=Label(text='This device is assigned to:')
        box.add_widget(label)
        spinner=Spinner(text=ROLES[0],values=ROLES)
        spinner.bind(text=self.setNodeName)
        self.setNodeName(spinner)
        box.add_widget(spinner)
        button=Button(text='OK')
        box.add_widget(button)
        button.bind(on_release=self.joinAsPopup_.dismiss)
        self.joinAsPopup_.open()

    def setNodeName(self,spinner,*args):
        Logger.info("setNodeName called:"+str(spinner.text))
        self.nodeName=spinner.text
        self.teamsScreen.ids.deviceHeader.ids.deviceLabel.text=self.nodeName
        self.assignmentsScreen.ids.deviceHeader.ids.deviceLabel.text=self.nodeName

    def optionsPopup(self):
        box=BoxLayout(orientation='vertical')
        popup=PopupWithIcons(
                title='Options',
                content=box,
                size_hint=(0.8,None),
                background_color=(0,0,0,0.5))
        stsUrlBox=BoxLayout(orientation='horizontal')
        stsUrlLabel=Label(text='SARTopo URL:',size_hint_x=0.4,size_hint_y=None,height=30)
        stsUrlBox.add_widget(stsUrlLabel)
        stsUrlField=TextInput(multiline=False,size_hint_y=None,height=30)
        stsUrlBox.add_widget(stsUrlField)
        box.add_widget(stsUrlBox)
        okCancelBox=BoxLayout(orientation='horizontal',size_hint_y=None,height=50)
        okButton=Button(text='OK')
        def optionsAccept(*args):
            self.stsUrl=stsUrlField.text
            self.setSts()
            self.stsSync()
        okButton.bind(on_release=optionsAccept)
        okButton.bind(on_release=popup.dismiss)
        cancelButton=Button(text='Cancel')
        cancelButton.bind(on_release=popup.dismiss)
        okCancelBox.add_widget(okButton)
        okCancelBox.add_widget(cancelButton)
        box.add_widget(okCancelBox)
        popup.height=popup.content.height+35
        popup.open()

    def newPairingPopup(self,assignmentName,teamName):
        self.textpopup(text='A new pairing has been created:\n  Assignment='+str(assignmentName)+'  Team='+str(teamName)+'\n\n'+NEW_PAIRING_POPUP_TEXT)

    def join(self,init=False,*args):
        Logger.info("called join; init="+str(init))
        if self.lan:
            self.lanJoin(init=init)
        elif self.cloud:
            self.cloudJoin(init=init)
        elif self.localhost:
            self.localhostJoin(init=init)
        else:
            Logger.error("neither LAN nor cloud nor localhost responded; cannot join.")

    def cloudJoin(self,init=False,*args):
        Logger.info("called cloudJoin; init="+str(init))
        if self.cloud:
            self.joinAsPopup()
            d={'NodeName':self.nodeName}
            if init:
                d['Init']=True
            self.cloudRequest('api/v1/join','POST',d,timeout=5) # make this a blocking call
            # if not init: # do an initial sync if we are not initializing
            # self.updateCounts()
            self.buildLists()
            if self.stsUrl:
                self.setSts()
                self.stsSync()
            self.sync(since=0)
            self.syncTimer=Clock.schedule_interval(self.sync,self.syncInterval) # start syncing every 5 seconds

    def lanJoin(self,init=False):
        if self.lan:
            d={'NodeName':self.nodeName}
            if init:
                d['Init']=True
            self.lanRequest('api/v1/join','POST',d,timeout=5) # make this a blocking call

    def localhostJoin(self,init=False):
        if self.localhost:
            d={'NodeName':self.nodeName}
            if init:
                d['Init']=True
            self.localhostRequest('api/v1/join','POST',d,timeout=5) # make this a blocking call

    def setSts(self):
        url=self.stsUrl
        id=None
        key=None
        if 'sartopo.com' in url:
            if self.stsConfigpath is not None:
                if os.path.isfile(self.stsConfigpath):
                    # if self.stsAccount is None:
                    #     print("config file '"+self.stsConfigpath+"' is specified, but no account name is specified.")
                    #     return -1
                    config=configparser.ConfigParser()
                    config.read(self.stsConfigpath)
                    account=config.sections()[0]  # just use the first section for now
                    section=config[account]
                    id=section.get("id",None)
                    key=section.get("key",None)
                    if id is None or key is None:
                        print("account entry '"+account+"' in config file '"+self.stsConfigpath+"' is not complete:\n  it must specify id and key.")
                        return -1
                else:
                    print("specified config file '"+self.stsConfigpath+"' does not exist.")
                    return -1
            else:
                print("Sartopo session config file name was not specified.")
                return -1
        if url.endswith("#"): # pound sign at end of URL causes crash; brute force fix it here
            url=url[:-1]
        parse=url.replace("http://","").replace("https://","").split("/")
        domainAndPort=parse[0]
        mapID=parse[-1]
        print("tdbCreateSts: creating instance of SartopoSession: domainAndPort="+domainAndPort+" mapID="+mapID)
        self.sts=SartopoSession(domainAndPort=domainAndPort,mapID=mapID,id=id,key=key)
        print("sts return value:"+str(self.sts))

    # SARTopo sync rules:
    # - unnamed assignments in sartopo: show a warning dialog and do not import the assignment
    # - named sartopo assignment that doesn't yet exist in tracker: add the assignment to tracker
    # - named sartopo assignment that exists (by the same name) in tracker:
    #    - if intended resource and status are the same as tracker, take no action
    #    - if intended resource is different than tracker: update tracker to match sartopo
    #    - if status is different than tracker: show a warning dialog
    def stsSync(self):
        if self.sts:
            j=self.sts.getFeatures('Assignment')
            print("sartopo assignments json:"+json.dumps(j,indent=2))
            self.sartopoAssignments=[]
            for a in j:
                d={}
                ap=a['properties']
                ag=a['geometry']
                d['letter']=ap['letter']
                d['id']=a['id']
                d['type']=ag['type'] # LineString or Polygon
                d['resource']=ap.get('resourceType','GROUND')
                d['status']=ap['status']
                self.sartopoAssignments.append(d)
            print("assignments from sartopo: "+str(self.sartopoAssignments))
            print("assignmentsList: "+str(self.assignmentsList))
            if '' in [x['letter'] for x in self.sartopoAssignments]:
                self.textpopup('WARNING: Unnamed (unlettered) SARTopo Assignments exist on the map.  Only named assignments will be imported to AssignmentTracker.')
            for a in self.sartopoAssignments:
                if a['letter']!='':
                    if a['letter'] not in [x[0] for x in self.assignmentsList]:
                        self.newAssignment(name=a['letter'],intendedResource=a['resource'],sid=a['id'])
                    else:
                        if a['resource']!=tdbGetAssignmentIntendedResourceByName(a['letter']):
                            tdbSetAssignmentIntendedResourceByName(a['letter'],a['resource'])
                        status=tdbGetAssignmentStatusByName(a['letter'])
                        if ((a['status']=='INPROGRESS' and status in ['UNASSIGNED','ASSIGNED','COMPLETED']) or
                                (a['status'] in ['DRAFT','PREPARED'] and status in ['WORKING','ENROUTE TO IC','DEBRIEFING','COMPLETED']) or
                                (a['status'] in ['COMPLETED'] and status not in ['COMPLETED'])):
                            self.textpopup('WARNING: SARTopo assignment '+a['letter']+' status mismatch:\nSARTopo status = '+a['status']+'\nAssignmentTracker status = '+status+'\n\nPlease change status setting(s) as needed.')
            self.redraw()

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
        if 'since' not in url: # don't show sync requests - too verbose
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

    def checkForCloud(self,timeout):
        self.cloud=False
        print("calling checkForCloud")
        r=self.cloudRequest("","GET",timeout=timeout)
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
    
    def sync(self,*args,since=None):
        since=since or self.lastSyncTimeStamp
        # Logger.info("sync called: lastSyncTimeStamp="+str(since))
        self.sendRequest("api/v1/since/"+str(int(since)),on_success=self.on_sync_success,on_failure=self.on_sync_failure,on_error=self.on_sync_failure)

    def on_sync_success(self,request,result):
        # Logger.info("  on_sync_success called:"+str(result))
        self.lastSyncTimeStamp=float(result['timestamp'])
        # Logger.info("  lastSyncTimeStamp is now "+str(self.lastSyncTimeStamp))
        requiredKeys=['Teams','Assignments','Pairings','History']
        if not all(key in result.keys() for key in requiredKeys):
            Logger.info("ERROR: sync result does not contain all required keys:"+str(requiredKeys))
            return None
        # if the new/updated host entry already exists local entry,
        #  update the values of the local entry (e.g. status, resource, timestamp);
        # otherwise, add it as a new local entry (a different client created it)
        for e in result['Teams']:
            # fields to update: TeamStatus, Resource, LastEditEpoch
            #  (TeamName can never be changed)
            setString="TeamStatus='"+str(e['TeamStatus'])+"'"
            setString+=", Resource='"+str(e['Resource'])+"'"
            setString+=", Medical='"+str(e['Medical'])+"'"
            setString+=', LastEditEpoch='+str(e['LastEditEpoch'])
            query='UPDATE Teams SET '+setString+' WHERE tid='+str(e['tid'])+';'
            Logger.info('Teams sync query:'+query)
            r=q(query) # return value is number of rows affected
            Logger.info('  response='+str(r))
            if r==0:
                r=tdbNewTeam(
                        e['TeamName'],
                        e['Resource'],
                        status=e['TeamStatus'],
                        medical=e['Medical'],
                        tid=e['tid'],
                        lastEditEpoch=e['LastEditEpoch'])
                Logger.info('   creating a new team.  response:'+str(r))
            if e['TeamName'] in self.teamNamePool:
                self.teamNamePool.remove(e['TeamName'])
        for e in result['Assignments']:
            # fields to update: AssignmentStatus, IntendedResource, LastEditEpoch
            #  (AssignmentName can never be changed)
            setString="AssignmentStatus='"+str(e['AssignmentStatus'])+"'"
            setString+=", IntendedResource='"+str(e['IntendedResource'])+"'"
            setString+=", sid='"+str(e['sid'])+"'"
            setString+=', LastEditEpoch='+str(e['LastEditEpoch'])
            query='UPDATE Assignments SET '+setString+' WHERE aid='+str(e['aid'])+';'
            Logger.info('Assignment sync query:'+query)
            r=q(query) # return value is number of rows affected
            Logger.info('  response='+str(r))
            if r==0:
                r=tdbNewAssignment(
                        e['AssignmentName'],
                        e['IntendedResource'],
                        status=e['AssignmentStatus'],
                        aid=e['aid'],
                        sid=e['sid'],
                        lastEditEpoch=e['LastEditEpoch'])
                Logger.info('   creating a new assignment.  response:'+str(r))
            if e['AssignmentName'] in self.assignmentNamePool:
                self.assignmentNamePool.remove(e['AssignmentName'])
        for e in result['Pairings']:
            # fields to update: PairingStatus, LastEditEpoch
            #  (tid, aid can never be changed)
            setString="PairingStatus='"+str(e['PairingStatus'])+"'"
            setString+=', LastEditEpoch='+str(e['LastEditEpoch'])
            query='UPDATE Pairings SET '+setString+' WHERE pid='+str(e['pid'])+';'
            Logger.info('Pairing sync query:'+query)
            r=q(query) # return value is number of rows affected
            Logger.info('  response='+str(r))
            if r==0:
                # tdbNewPairing will normally set the team and assignment
                #  statuses to 'ASSIGNED' but if this is joining an already-in-progress
                #  pairing then the team status (WORKING, ENROUTE TO IC, DEBRIEFING)
                #  should be preserved
                r=tdbNewPairing(
                        e['aid'],
                        e['tid'],
                        status=e['PairingStatus'],
                        pid=e['pid'],
                        # teamStatus=tdbGetTeamStatusByName(tdbGetTeamNameByID(tid)),
                        lastEditEpoch=e['LastEditEpoch'])
                Logger.info('   creating a new pairing.  response:'+str(r))
        for e in result['History']:
            # fields to update: Epoch
            #  (tid, aid, Entry can never be changed)
            setString="Epoch='"+str(e['Epoch'])+"'"
            query='UPDATE History SET '+setString+' WHERE hid='+str(e['hid'])+';'
            Logger.info('History sync query:'+query)
            r=q(query) # return value is number of rows affected
            Logger.info('  response='+str(r))
            if r==0:
                r=tdbAddHistoryEntry(
                        entry=e['Entry'],
                        hid=e['hid'],
                        aid=e['aid'],
                        tid=e['tid'],
                        recordedBy=e['RecordedBy'],
                        epoch=e['Epoch'])
                Logger.info('   adding a history entry.  response:'+str(r))
        if self.sm.current=='teamsScreen' and len(result['Teams'])>0:
            self.showTeams()
        elif self.sm.current=='assignmentsScreen' and len(result['Assignments'])>0:
            self.showAssignments()
        elif self.sm.current=='pairingDetailScreen' and len(result['History'])>0:
            self.pairingDetailHistoryUpdate()

    def on_sync_failure(self,request,result):
        Logger.info("sync failure:"+str(result))
        self.syncTimer.cancel()
        self.textpopup("SYNC FAILURE","Sync failure.  The server is not responding to sync requests.  This node is no longer part of the AssignmentTracker incident.\n\nAborting. You can try to restart and join after the issue is remedied.",on_release=sys.exit)

    def newTeam(self,name=None,resource=None,doToast=True):
        name=name or self.newTeamScreen.ids.nameSpinner.text
        if name in self.teamNamePool:
            self.teamNamePool.remove(name)
        resource=resource or self.newTeamScreen.ids.resourceSpinner.text
        r=tdbNewTeam(name,resource)
        n=r['validate']['n']
        # send n (local db index) with the request payload, so that the response handler will have access to it;
        #   that way this specific n will be kept with this specific request, which prevents
        #   race conditions that would result from setting a class variable to keep track of n then unsetting it
        #   in the response handler (i.e. when multiple local objects are created before the first response)
        self.sendRequest("api/v1/teams/new","POST",{'TeamName':name,'Resource':resource,'n':n},on_success=self.on_newTeam_success)
        self.updateNewTeamNameSpinner()
        self.buildLists()
        if self.screenStack[-1]=='newPairingScreen':
            self.newTeamCreatedFromNewPairing=name+' : '+resource+' : UNASSIGNED'
            Logger.info('setting newTeamCreatedFromNewPairing to '+str(self.newTeamCreatedFromNewPairing))
            self.showPrevious() # only go to the previous screen if this was nested
        if doToast:
            toast('Team '+str(name)+' ['+str(resource)+'] created')

    def on_newTeam_success(self,request,response):
        rb=request.req_body
        rbj=json.loads(rb)
        n=rbj.get('n',None) # local db index
        v=response['validate']
        tdbNewTeamFinalize(n,v['tid'],v['LastEditEpoch'])

    def newAssignment(self,name=None,intendedResource=None,sid=None,doToast=True):
        name=name or self.newAssignmentScreen.ids.nameSpinner.text
        if name in self.assignmentNamePool:
            self.assignmentNamePool.remove(name)
        intendedResource=intendedResource or self.newAssignmentScreen.ids.resourceSpinner.text
        r=tdbNewAssignment(name,intendedResource,sid)
        n=r['validate']['n']
        # send n (local db index) with the request payload, so that the response handler will have access to it;
        #   that way this specific n will be kept with this specific request, which prevents
        #   race conditions that would result from setting a class variable to keep track of n then unsetting it
        #   in the response handler (i.e. when multiple local objects are created before the first response)
        self.sendRequest("api/v1/assignments/new","POST",{'AssignmentName':name,'IntendedResource':intendedResource,'n':n,'sid':sid},on_success=self.on_newAssignment_success)
        self.updateNewAssignmentNameSpinner()
        self.buildLists()
        if doToast:
            toast('Assignment '+str(name)+' ['+str(intendedResource)+'] created')

    def on_newAssignment_success(self,request,response):
        rb=request.req_body
        rbj=json.loads(rb)
        n=rbj.get('n',None) # local db index
        v=response['validate']
        tdbNewAssignmentFinalize(n,v['aid'],v['LastEditEpoch'])

    def newPairing(self):
        # if this is a repeat (same assignmentName and teamName as
        #  a previous pairing), don't make a new pairing, but instead
        #  change the status of the existing pairing from COMPLETED to
        #  CURRENT.  This will remove the completed pairing from the
        #  completed section of the assignment / pairing view.  This
        #  is hopefully less confusing than seeing the same names
        #  in two different rows (once in each section), and it should
        #  reflect reality just as well as keeping both rows.  Either
        #  option would be a bit confusing; hopefully this option is
        #  slightly less confusing.
        if 'Assignment' in self.newPairingScreen.ids.knownLabel.text:
            assignmentName=self.newPairingScreen.ids.knownNameLabel.text
            teamName=self.newPairingScreen.ids.unknownSpinner.text.split()[0]
        else:
            teamName=self.newPairingScreen.ids.knownNameLabel.text
            assignmentName=self.newPairingScreen.ids.unknownSpinner.text.split()[0]
        Logger.info("pairing assignment "+str(assignmentName)+" with team "+str(teamName))
        aid=tdbGetAssignmentIDByName(assignmentName)
        tid=tdbGetTeamIDByName(teamName)
        if aid<0 or tid<0:
            self.textpopup(
                    title='Database Error',
                    text='Database IDs were never updated; this may be due to a server communication error.  Cannot create a pairing.\n'+assignmentName+':'+str(aid)+'  '+teamName+':'+str(tid))
            return -1
        prevID=tdbGetPairingIDByNames(assignmentName,teamName,previousOnly=True)
        Logger.info("Checking for previous pairings with same assignment and same team: "+str(prevID))
        if prevID: # this is a repeat; reuse the existing ID rather than making a new pairing
            tdbSetPairingStatusByID(prevID,'CURRENT')
            self.sendRequest('api/v1/pairings/'+str(prevID)+'/status','PUT',{'NewStatus':'CURRENT'})
            tdbSetTeamStatusByName(teamName,'ASSIGNED')
            tdbSetAssignmentStatusByName(assignmentName,'ASSIGNED')                
            # api call for a new pairing takes care of setting the team and assignment status
            #  on the host, but we purposely are not making that call here, so we need to do
            #  those api calls separately
            self.sendRequest('api/v1/teams/'+str(tid)+'/status','PUT',{'NewStatus':'ASSIGNED'})
            self.sendRequest('api/v1/assignments/'+str(aid)+'/status','PUT',{'NewStatus':'ASSIGNED','PushTables':'True'})
        else:
            r=tdbNewPairing(aid,tid) # also sets team and assignment to ASSIGNED
            n=r['validate']['n']
            self.sendRequest('api/v1/pairings/new','POST',{'aid':aid,'tid':tid,'n':n},on_success=self.on_newPairing_success)
        # self.newPairingPopup(assignmentName,teamName)
        self.textpopup(
                title='New Pairing',
                text='A new pairing has been created:\n  Assignment='+str(assignmentName)+'  Team='+str(teamName)+'\n\n'+NEW_PAIRING_POPUP_TEXT)
        self.showPrevious() # close the new pairing dialog after creating the pairing; not likely to need to pair another team
        # avoid sending multiple requests back to back, since this can create race conditions
        #  and html flickers with clients receiving multiple different websocket messages
        #  in rapid succession; instead, make the new pairings API handler set the team
        #  and assignment statuses and then just do one websocket send 
        # self.sendRequest("api/v1/teams/"+str(tid)+"/status","PUT",{"NewStatus":"ASSIGNED"})
        # self.sendRequest("api/v1/assignments/"+str(aid)+"/status","PUT",{"NewStatus":"ASSIGNED"})

    def on_newPairing_success(self,request,response):
        rb=request.req_body
        rbj=json.loads(rb)
        n=rbj.get('n',None) # local db index
        v=response['validate']
        tdbNewPairingFinalize(n,v['pid'],v['LastEditEpoch'])

    def updateNewTeamNameSpinner(self):
        self.newTeamScreen.ids.nameSpinner.values=self.teamNamePool[0:8]
        self.newTeamScreen.ids.nameSpinner.text=self.teamNamePool[0]
    
    def updateNewAssignmentNameSpinner(self):
        self.newAssignmentScreen.ids.nameSpinner.values=self.assignmentNamePool[0:8]
        self.newAssignmentScreen.ids.nameSpinner.text=self.assignmentNamePool[0]

    def buildLists(self):
        self.teamsList=tdbGetTeamsView()
        self.assignmentsList=tdbGetAssignmentsView()
        self.updateCounts()
        self.medicalTeams=tdbGetMedicalTeams()

    def redraw(self):
        if self.sm.current=='teamsScreen':
            self.showTeams()
        elif self.sm.current=='assignmentsScreen':
            self.showAssignments()

    def showTeams(self,*args):
        Logger.info('showTeams called')
        Logger.info("screenStack: "+str(self.screenStack))
        self.buildLists()
        # recycleview needs a list of dictionaries; the view divides into rows every nth element
        self.teamsScreen.teamsRVData=[]
        for entry in self.teamsList:
            row=copy.deepcopy(entry)
            for cell in row:
                d={}
                d['text']=str(cell)
                d['bg']=(0,0,0,0)
                d['src']=''
                if cell in self.medicalTeams:
                    d['src']=self.medicalIconSrc
                self.teamsScreen.teamsRVData.append(d)
        self.sm.transition=NoTransition()
        self.sm.current='teamsScreen'
        # if previous screen was assignments, just replace it in the stack; otherwise, append
        if self.screenStack[-1]=='assignmentsScreen':
            self.screenStack[-1]='teamsScreen'
        else:
            self.screenStack.append('teamsScreen')

    def showAssignments(self,*args):
        Logger.info("showAssignments called")
        Logger.info("screenStack: "+str(self.screenStack))
        self.buildLists()
        # recycleview needs a list of dictionaries; the view divides into rows every nth element
        self.assignmentsScreen.assignmentsRVData=[]
        for entry in self.assignmentsList:
            row=copy.deepcopy(entry)
            for cell in row:
                d={}
                d['text']=str(cell)
                d['bg']=(0,0,0,0)
                d['src']=''
                if cell in self.medicalTeams:
                    d['src']=self.medicalIconSrc
                self.assignmentsScreen.assignmentsRVData.append(d)
        self.sm.transition=NoTransition()
        self.sm.current='assignmentsScreen'
        # if previous screen was teams, just replace it in the stack; otherwise, append
        if self.screenStack[-1]=='teamsScreen':
            self.screenStack[-1]='assignmentsScreen'
        else:
            self.screenStack.append('assignmentsScreen')

    def updateCounts(self):
        Logger.info('updateCounts called')
        d=tdbPushTables() # clients won't actually push websockets, but the return value has the counts
        # self.unassignedTeamsCount=len([x for x in self.teamsList if x[1]=='UNASSIGNED'])
        # self.assignedTeamsCount=len(self.teamsList)-self.unassignedTeamsCount
        # self.unassignedAssignmentsCount=len([x for x in self.assignmentsList if x[2]=='UNASSIGNED'])
        # self.assignedAssignmentsCount=len(self.assignmentsList)-self.unassignedAssignmentsCount
        teamsCountText='A:'+str(d['assignedTeamsCount'])+'     U:'+str(d['unassignedTeamsCount'])
        assignmentsCountText='A:'+str(d['assignedAssignmentsCount'])+'     U:'+str(d['unassignedAssignmentsCount'])+'     C:'+str(d['completedAssignmentsCount'])

        self.teamsScreen.ids.viewSwitcher.ids.teamsViewButton.text='[size=35]Teams\n[size=12]'+teamsCountText
        self.teamsScreen.ids.viewSwitcher.ids.teamsViewButton.line_height=0.7
        self.teamsScreen.ids.viewSwitcher.ids.assignmentsViewButton.text='[size=20]Assignments\n[size=12]'+assignmentsCountText
        self.teamsScreen.ids.viewSwitcher.ids.assignmentsViewButton.line_height=0.95
        
        self.assignmentsScreen.ids.viewSwitcher.ids.teamsViewButton.text='[size=20]Teams\n[size=12]'+teamsCountText
        self.assignmentsScreen.ids.viewSwitcher.ids.teamsViewButton.line_height=0.95
        self.assignmentsScreen.ids.viewSwitcher.ids.assignmentsViewButton.text='[size=35]Assignments\n[size=12]'+assignmentsCountText
        self.assignmentsScreen.ids.viewSwitcher.ids.assignmentsViewButton.line_height=0.7

    def showPairingDetail(self,assignmentName=None,teamName=None):
        Logger.info('showPairingDetail called:'+str(assignmentName)+' : '+str(teamName))
        self.lastPairingDetailAssignmentName=assignmentName
        self.lastPairingDetailTeamName=teamName
        Logger.info("screenStack: "+str(self.screenStack))
        if assignmentName:
            if teamName: # assignment and team specified - it's a pairing
                pid=tdbGetPairingIDByNames(assignmentName,teamName)
                status=tdbGetPairings(pid)[0].get('PairingStatus',None)
                teamResource=tdbGetTeamResourceByName(teamName)
                if status=='CURRENT':
                    status=tdbGetTeamStatusByName(teamName)
                    self.pairingDetailScreen.ids.statusBox.visible=True
                else:
                    status='COMPLETED'
                    self.pairingDetailScreen.ids.statusBox.visible=False
                self.pairingDetailScreen.ids.intendedResourceLabel.text=''
                if self.screenStack[-1]=='assignmentsScreen':
                    self.pairingDetailScreen.ids.pairButton.text='Assign another team to this assignment'
                else:
                    self.pairingDetailScreen.ids.pairButton.text='Assign this team to another assignment'
                self.pairingDetailScreen.ids.assignmentEditButton.disabled=True
                self.pairingDetailScreen.ids.assignmentDeleteButton.disabled=True
                self.pairingDetailScreen.ids.teamEditButton.disabled=False
                self.pairingDetailScreen.ids.teamDeleteButton.disabled=True
            else: # assignment specified, but not team
                teamName='--'
                teamResource=''
                status='UNASSIGNED'
                intendedResource=tdbGetAssignmentIntendedResourceByName(assignmentName)
                self.pairingDetailScreen.ids.intendedResourceLabel.text='Intended for: '+intendedResource
                self.pairingDetailScreen.ids.statusBox.visible=False
                self.pairingDetailScreen.ids.pairButton.text='Assign a team to this assignment'
                self.pairingDetailScreen.ids.assignmentEditButton.disabled=False
                self.pairingDetailScreen.ids.assignmentDeleteButton.disabled=False
                self.pairingDetailScreen.ids.teamEditButton.disabled=True
                self.pairingDetailScreen.ids.teamDeleteButton.disabled=True
        elif teamName: # team specified, but not assignment
            assignmentName='--'
            intendedResource=''
            status='UNASSIGNED'
            teamResource=tdbGetTeamResourceByName(teamName)
            self.pairingDetailScreen.ids.statusBox.visible=False
            self.pairingDetailScreen.ids.pairButton.text='Assign this team to an assignment'
            self.pairingDetailScreen.ids.intendedResourceLabel.text=''
            self.pairingDetailScreen.ids.assignmentEditButton.disabled=True
            self.pairingDetailScreen.ids.assignmentDeleteButton.disabled=True
            self.pairingDetailScreen.ids.teamEditButton.disabled=False
            self.pairingDetailScreen.ids.teamDeleteButton.disabled=False
        self.pairingDetailScreen.ids.assignmentNameLabel.text=assignmentName
        self.pairingDetailScreen.ids.teamNameLabel.text=teamName
        self.pairingDetailScreen.ids.teamResourceLabel.text=teamResource
        self.pairingDetailScreen.ids.statusLabel.text=status
        self.pairingDetailBeingShown=[assignmentName,teamName]
        self.pairingDetailStatusUpdate()
        self.pairingDetailHistoryUpdate()
        self.sm.current='pairingDetailScreen'
        self.screenStack.append('pairingDetailScreen')

    def showPrevious(self):
        Logger.info('showPrevious called: screenStack at start:'+str(self.screenStack))
        prev=self.screenStack.pop()
        prev=self.screenStack.pop() # pop twice to get the previous screen
        if prev=='teamsScreen':
            self.showTeams()
        elif prev=='assignmentsScreen':
            self.showAssignments()
        elif prev=='newPairingScreen':
            self.showNewPairing()
        elif prev=='pairingDetailScreen':
            self.showPairingDetail(self.lastPairingDetailAssignmentName,self.lastPairingDetailTeamName)
        Logger.info('showPrevious called: screenStack at end:'+str(self.screenStack))

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
                    tdbGetHistory(aid=tdbGetAssignmentIDByName(assignmentName),tid=tdbGetTeamIDByName(teamName))[::-1]]
        else:
            history=[[x['Entry'],x['RecordedBy'],time.strftime('%H:%M',time.localtime(x['Epoch']))] for x in
                    tdbGetHistory(aid=tdbGetAssignmentIDByName(assignmentName))[::-1]]
        history=[y for x in history for y in x] # flattened list, needed by RecycleGridLayout
        self.pairingDetailScreen.ids.historyRV.data=[{'text': str(x)} for x in history]
      
    def showNewTeam(self,*args):
        Logger.info('showNewTeam called')
        Logger.info("screenStack: "+str(self.screenStack))
        self.updateNewTeamNameSpinner()
        self.sm.current='newTeamScreen'
        self.screenStack.append('newTeamScreen')

    def showNewTeamScreenFromNewPairingScreen(self,*args):
        Logger.info('showNewTeamScreenFromNewPairingScreen called')
        Logger.info("screenStack: "+str(self.screenStack))
        self.updateNewTeamNameSpinner()
        self.newTeamScreen.ids.resourceSpinner.text=self.newPairingScreen.ids.resourceNameLabel.text
        self.sm.current='newTeamScreen'
        self.screenStack.append('newPairingScreen')

    def showNewAssignment(self,*args):
        Logger.info('showNewAssignment called')
        Logger.info("screenStack: "+str(self.screenStack))
        self.updateNewAssignmentNameSpinner()
        self.sm.current='newAssignmentScreen'
        self.screenStack.append('newAssignmentScreen')

    def showNewPairing(self):
        Logger.info("showNewPairing called")
        Logger.info("screenStack: "+str(self.screenStack))
        if self.screenStack[-2]=='teamsScreen': # team=fixed, assignment=selectable
            teamName=self.pairingDetailScreen.ids.teamNameLabel.text
            self.newPairingScreen.ids.knownLabel.text='Team:'
            self.newPairingScreen.ids.knownNameLabel.text=teamName
            self.newPairingScreen.ids.resourceLabel.text='Resource:'
            resource=tdbGetTeamResourceByName(teamName)
            self.newPairingScreen.ids.resourceNameLabel.text=resource
            status=tdbGetTeamStatusByName(teamName)
            assignmentNames=[]
            if status not in ['UNASSIGNED','COMPLETED']:
                status='ASSIGNED to:\n'
                pairings=tdbGetPairingsByTeam(tdbGetTeamIDByName(teamName),currentOnly=True)
                # Logger.info('  pairings:'+str(pairings))
                aids=[pairing.get('aid',None) for pairing in pairings]
                # Logger.info('  aids:'+str(aids))
                assignmentNames=[tdbGetAssignments(aid)[0]['AssignmentName'] for aid in aids]
                # Logger.info('  assignmentNames:'+str(assignmentNames))
                status+=','.join(assignmentNames)
            self.newPairingScreen.ids.currentlyLabel.text=status
            # keep in mind that self.assignmentsList is really a list of pairings
            #  that also includes unassigned assignments; so the same assignment could
            #  appear in multiple entries
            # Logger.info("assignmentsList:"+str(self.assignmentsList))
            part1=[] # unassigned assignments, same resource type
            part2=[] # unassigned assignments, other resource types
            part3=[] # assigned assignments, same resource type
            part4=[] # assigned assignments, other resource types
            for assignment in self.assignmentsList:
                [aName,tName,aStat,aRes]=assignment
                if aStat!='COMPLETED':
                    entryText=aName+' : '+aRes
                    if aStat=='UNASSIGNED':
                        entryText+=' : UNASSIGNED'
                        if aRes==resource:
                            part1.append(entryText)
                        else:
                            part2.append(entryText)
                    elif aName not in assignmentNames: # don't list assignment(s) already paired to this team!
                        # also, assignments already paired to multiple teams should only be one entry
                        pairings=tdbGetPairingsByAssignment(tdbGetAssignmentIDByName(aName),currentOnly=True)
                        tids=[pairing.get('tid',None) for pairing in pairings]
                        tNames=[tdbGetTeams(tid)[0]['TeamName'] for tid in tids]
                        tNameText=','.join(tNames)
                        entryText+=' : ASSIGNED to '+tNameText
                        assignmentNames.append(aName) # don't process it again
                        if aRes==resource:
                            part3.append(entryText)
                        else:
                            part4.append(entryText)
            theList=part1+part2+part3+part4
            self.newPairingScreen.ids.unknownSpinner.values=theList
            if theList:
                self.newPairingScreen.ids.unknownSpinner.text=theList[0]
                self.newPairingScreen.ids.pairButton.disabled=False
            else:
                # could show a warning here and disallow pairing before the screen raises
                self.newPairingScreen.ids.unknownSpinner.text='No assignments available'
                self.newPairingScreen.ids.pairButton.disabled=True
        else: # previous screen was either the assignments screen or teams-from-new-pairing:
            # assignment=fixed, team=selectable, but pre-select the new team if previous screen was teams-from-new-pairing
            assignmentName=self.pairingDetailScreen.ids.assignmentNameLabel.text
            self.newPairingScreen.ids.knownLabel.text='Assignment:'
            self.newPairingScreen.ids.knownNameLabel.text=assignmentName
            self.newPairingScreen.ids.resourceLabel.text='Intended For:'
            intendedResource=tdbGetAssignmentIntendedResourceByName(assignmentName)
            self.newPairingScreen.ids.resourceNameLabel.text=intendedResource
            status=tdbGetAssignmentStatusByName(assignmentName)
            if status not in ['UNASSIGNED','COMPLETED']:
                status='ASSIGNED to:\n'
                pairings=tdbGetPairingsByAssignment(tdbGetAssignmentIDByName(assignmentName),currentOnly=True)
                # Logger.info('  pairings:'+str(pairings))
                tids=[pairing.get('tid',None) for pairing in pairings]
                # Logger.info('  tids:'+str(tids))
                teamNames=[tdbGetTeams(tid)[0]['TeamName'] for tid in tids]
                # Logger.info('  teamNames:'+str(teamNames))
                status+=','.join(teamNames)
            self.newPairingScreen.ids.currentlyLabel.text=status
            # Logger.info("teamsList:"+str(self.teamsList))
            part1=[] # unassigned teams, same resource type as intended resource
            part2=[] # unassigned teams, other resource types
            part3=[] # assigned teams, same resource type as intended resource
            part4=[] # assigned teams, other resource types
            for team in self.teamsList:
                entryText=team[0]+' : '+team[3]
                if team[2]=='UNASSIGNED':
                    entryText+=' : UNASSIGNED'
                    if team[3]==intendedResource:
                        part1.append(entryText)
                    else:
                        part2.append(entryText)
                elif assignmentName not in team[1].split(','): # don't list team(s) already paired to this assignment!
                    entryText+=' : ASSIGNED to '+team[1]
                    if team[3]==intendedResource:
                        part3.append(entryText)
                    else:
                        part4.append(entryText)
            theList=part1+part2+part3+part4
            self.newPairingScreen.ids.unknownSpinner.values=theList
            if theList:
                self.newPairingScreen.ids.unknownSpinner.text=theList[0]
                self.newPairingScreen.ids.pairButton.disabled=False
                if self.newTeamCreatedFromNewPairing is not None:
                    self.newPairingScreen.ids.unknownSpinner.text=self.newTeamCreatedFromNewPairing
            else:
                # could show a warning here and disallow pairing before the screen raises
                self.newPairingScreen.ids.unknownSpinner.text='No teams available'
                self.newPairingScreen.ids.pairButton.disabled=True
        self.sm.current='newPairingScreen'
        self.newTeamCreatedFromNewPairing=None
        self.screenStack.append('newPairingScreen')

    def assignmentEdit(self):
        box=BoxLayout(orientation='vertical')
        popup=PopupWithIcons(
                title='Edit Assignment',
                content=box,
                size_hint=(0.8,None),
                background_color=(0,0,0,0.5))
        assignmentName=self.pairingDetailScreen.ids.assignmentNameLabel.text
        aid=tdbGetAssignmentIDByName(assignmentName)
        intendedResource=tdbGetAssignmentIntendedResourceByName(assignmentName)
        assignmentNameLabel=Label(text=assignmentName)
        box.add_widget(assignmentNameLabel)
        intendedResourceBox=BoxLayout(orientation='horizontal')
        intendedResourceLabel=Label(text='Intended for:',size_hint_x=0.4)
        intendedResourceBox.add_widget(intendedResourceLabel)
        intendedResourceSpinner=Spinner(text=intendedResource,values=self.resourceTypes)
        intendedResourceBox.add_widget(intendedResourceSpinner)
        box.add_widget(intendedResourceBox)
        okCancelBox=BoxLayout(orientation='horizontal',size_hint_y=None,height=50)
        okButton=Button(text='OK')
        def assignmentEditAccept(*args):
            newIR=intendedResourceSpinner.text
            tdbSetAssignmentIntendedResourceByID(aid,newIR)
            self.sendRequest("api/v1/assignments/"+str(aid)+"/intendedResource","PUT",{"IntendedResource":str(newIR)})
            self.pairingDetailScreen.ids.intendedResourceLabel.text='Intended for: '+str(newIR)
            self.pairingDetailHistoryUpdate()
        okButton.bind(on_release=assignmentEditAccept)
        okButton.bind(on_release=popup.dismiss)
        cancelButton=Button(text='Cancel')
        cancelButton.bind(on_release=popup.dismiss)
        okCancelBox.add_widget(okButton)
        okCancelBox.add_widget(cancelButton)
        box.add_widget(okCancelBox)
        popup.height=popup.content.height+130
        popup.open()

    def assignmentDelete(self):
        box=BoxLayout(orientation='vertical')
        popup=PopupWithIcons(
                title='Delete Assignment',
                content=box,
                size_hint=(0.8,None),
                background_color=(0,0,0,0.5))
        assignmentName=self.pairingDetailScreen.ids.assignmentNameLabel.text
        aid=tdbGetAssignmentIDByName(assignmentName)
        confirmLabel=Label(text='Really delete assignment '+assignmentName+'?')
        box.add_widget(confirmLabel)
        yesNoBox=BoxLayout(orientation='horizontal',size_hint_y=None,height=50)
        yesButton=Button(text='Yes')
        def assignmentDeleteAccept(*args):
            tdbDeleteAssignment(aid=aid)
            self.assignmentNamePool.append(assignmentName)
            self.assignmentNamePool.sort()
            self.sendRequest("api/v1/assignments/"+str(aid)+"/delete","PUT")
            self.showPrevious()
        yesButton.bind(on_release=assignmentDeleteAccept)
        yesButton.bind(on_release=popup.dismiss)
        noButton=Button(text='No')
        noButton.bind(on_release=popup.dismiss)
        yesNoBox.add_widget(yesButton)
        yesNoBox.add_widget(noButton)
        box.add_widget(yesNoBox)
        popup.height=popup.content.height+130
        popup.open()

    def teamEdit(self):
        box=BoxLayout(orientation='vertical')
        popup=PopupWithIcons(
                title='Edit Team',
                content=box,
                size_hint=(0.8,None),
                background_color=(0,0,0,0.5))
        teamName=self.pairingDetailScreen.ids.teamNameLabel.text
        tid=tdbGetTeamIDByName(teamName)
        resource=tdbGetTeamResourceByName(teamName)
        medical=tdbGetTeamMedicalByName(teamName)
        teamNameLabel=Label(text=teamName)
        box.add_widget(teamNameLabel)
        resourceBox=BoxLayout(orientation='horizontal')
        resourceLabel=Label(text='Resource:',size_hint_x=0.4)
        resourceBox.add_widget(resourceLabel)
        resourceSpinner=Spinner(text=resource,values=self.resourceTypes)
        resourceBox.add_widget(resourceSpinner)
        box.add_widget(resourceBox)
        medicalBox=BoxLayout(orientation='horizontal')
        medicalLabel=Label(text='Medical:',size_hint_x=0.4)
        medicalBox.add_widget(medicalLabel)
        medicalSpinner=Spinner(text=medical,values=['NO','YES'])
        medicalBox.add_widget(medicalSpinner)
        box.add_widget(medicalBox)
        okCancelBox=BoxLayout(orientation='horizontal',size_hint_y=None,height=50)
        okButton=Button(text='OK')
        def teamEditAccept(*args):
            newR=resourceSpinner.text
            newM=medicalSpinner.text
            tdbSetTeamResourceByID(tid,newR)
            self.sendRequest("api/v1/teams/"+str(tid)+"/resource","PUT",{"Resource":str(newR)})
            tdbSetTeamMedicalByID(tid,newM)
            self.sendRequest("api/v1/teams/"+str(tid)+"/medical","PUT",{"Medical":str(newM)})
            self.pairingDetailScreen.ids.teamResourceLabel.text=str(newR)
            self.pairingDetailHistoryUpdate()
        okButton.bind(on_release=teamEditAccept)
        okButton.bind(on_release=popup.dismiss)
        cancelButton=Button(text='Cancel')
        cancelButton.bind(on_release=popup.dismiss)
        okCancelBox.add_widget(okButton)
        okCancelBox.add_widget(cancelButton)
        box.add_widget(okCancelBox)
        popup.height=popup.content.height+130
        popup.open()

    def teamDelete(self):
        box=BoxLayout(orientation='vertical')
        popup=PopupWithIcons(
                title='Delete Team',
                content=box,
                size_hint=(0.8,None),
                background_color=(0,0,0,0.5))
        teamName=self.pairingDetailScreen.ids.teamNameLabel.text
        tid=tdbGetTeamIDByName(teamName)
        confirmLabel=Label(text='Really delete team '+teamName+'?')
        box.add_widget(confirmLabel)
        yesNoBox=BoxLayout(orientation='horizontal',size_hint_y=None,height=50)
        yesButton=Button(text='Yes')
        def teamDeleteAccept(*args):
            tdbDeleteTeam(tid=tid)
            self.teamNamePool.append(teamName)
            self.teamNamePool.sort()
            self.sendRequest("api/v1/teams/"+str(tid)+"/delete","PUT")
            self.showPrevious()
        yesButton.bind(on_release=teamDeleteAccept)
        yesButton.bind(on_release=popup.dismiss)
        noButton=Button(text='No')
        noButton.bind(on_release=popup.dismiss)
        yesNoBox.add_widget(yesButton)
        yesNoBox.add_widget(noButton)
        box.add_widget(yesNoBox)
        popup.height=popup.content.height+130
        popup.open()

    def changeTeamStatus(self,teamName=None,status=None):
        if not teamName:
            teamName=self.pairingDetailBeingShown[1]
        if not status:
            status=self.pairingDetailScreen.ids.statusSpinner.text
        if status=='DONE': # changing to DONE from pairing detail screen will 'close out' the current pairing
            # note, when an pairing changes to COMPLETED, its team name and (team) resource
            #  fields should be saved as strings, in case the team is later deleted
            [assignmentName,teamName]=self.pairingDetailBeingShown
            # 1. set pairing status to PREVIOUS
            pid=tdbGetPairingIDByNames(assignmentName,teamName)
            tdbSetPairingStatusByID(pid,'PREVIOUS')
            self.sendRequest("api/v1/pairings/"+str(pid)+"/status","PUT",{"NewStatus":"PREVIOUS"})
            # 2. set team status to UNASSIGNED if it is not in any current pairings
            tid=tdbGetTeamIDByName(teamName)
            others=tdbGetPairingsByTeam(tid,currentOnly=True)
            if not others:
                tdbSetTeamStatusByID(tid,'UNASSIGNED')
                self.sendRequest("api/v1/teams/"+str(tid)+"/status","PUT",{"NewStatus":"UNASSIGNED"})
            # 3. set assignment status to COMPLETED if it is not in any current pairings
            aid=tdbGetAssignmentIDByName(assignmentName)
            others=tdbGetPairingsByAssignment(aid,currentOnly=True)
            if not others:
                tdbSetAssignmentStatusByID(aid,'COMPLETED')
                self.sendRequest("api/v1/assignments/"+str(aid)+"/status","PUT",{"NewStatus":"COMPLETED"})
            self.textpopup(
                    title='Pairing completed',
                    text='A pairing has been completed:\n  Assignment='+assignmentName+'  Team='+teamName+'\n\n'+COMPLETED_PAIRING_POPUP_TEXT)
            self.showAssignments()
        else:
            Logger.info('changing status for team '+str(teamName)+' to '+str(status))
            tid=tdbGetTeamIDByName(teamName)
            tdbSetTeamStatusByID(tid,status)
            self.sendRequest("api/v1/teams/"+str(tid)+"/status","PUT",{"NewStatus":str(status)})
            self.pairingDetailScreen.ids.statusLabel.text=status
            self.pairingDetailStatusUpdate()
            self.pairingDetailHistoryUpdate()

    def textpopup(self, title='', text='', buttonText='OK', on_release=None, size_hint=(0.8,None)):
        popup=ExpandingPopup(title=title)
        popup.text=text
        if buttonText is not None:
            button = Button(text=buttonText, size_hint=(1, None))
            popup.ids.theBox.add_widget(button)
            button.bind(on_release=popup.dismiss)
            if on_release:
                button.bind(on_release=on_release)
        popup.open()
        return popup

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
    # src=StringProperty('')

    def refresh_view_attrs(self, rv, index, data):
        ''' Catch and handle the view changes '''
        self.index = index
        return super(SelectableLabel, self).refresh_view_attrs(
            rv, index, data)

    def on_touch_down(self, touch):
        if super(SelectableLabel, self).on_touch_down(touch):
            return True
        if self.collide_point(*touch.pos) and self.selectable:
            # theApp.screenStack.append(theApp.sm.current)
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
                theApp.showPairingDetail(assignmentName,teamName)
                return True
            elif theApp.sm.current=='teamsScreen':
                colCount=theApp.teamsScreen.ids.teamsLayout.cols
                Logger.info("Teams list item tapped: index="+str(self.index)+":"+str(theApp.teamsScreen.ids.teamsRV.data[self.index]))
                rowNum=int(self.index/colCount)
                row=theApp.teamsScreen.ids.teamsRV.data[rowNum*colCount:(rowNum+1)*colCount]
                Logger.info("   selected row:"+str(row))
                teamName=str(row[0]["text"])
                assignmentName=str(row[1]["text"])
                if assignmentName=='--':
                    assignmentName=None
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
    teamsRVData=ListProperty([])


class AssignmentsScreen(Screen):
    assignmentsRVData=ListProperty([])


class PairingDetailScreen(Screen):
    pairingDetailCurrentRVList=ListProperty([])
    pairingDetailPreviousRVList=ListProperty([])


class NewTeamScreen(Screen):
    pass


class NewAssignmentScreen(Screen):
    pass


class NewPairingScreen(Screen):
    pass


class PopupWithIcons(Popup):
    pass


class WrappedLabel(Label):
    pass


class ExpandingPopup(Popup):
    pass


if __name__ == '__main__':
    theApp=assignmentTrackerApp()
    theApp.run()
    