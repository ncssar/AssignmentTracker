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

# # custom version of kivy/network/urlrequest.py to allow synchronous (blocking) requests
# from urlrequest_tmg import UrlRequest

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
    
# if platform in ('win'):
#     import subprocess

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
        self.assignmentDetailBeingShown="N/A"

        self.device='SITUATION UNIT'
        self.nextCallsign='103'
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

        self.sm.add_widget(PairingScreen(name='pairingScreen'))
        self.pairingScreen=self.sm.get_screen('pairingScreen')

        self.sm.add_widget(AssignmentDetailScreen(name='assignmentDetailScreen'))
        self.assignmentDetailScreen=self.sm.get_screen('assignmentDetailScreen')

        tdbInit()
        # some hardcoded initial data for development
        self.newTeam('101','Ground Type 1')
        self.newTeam('102','K9 (HRD)')
        self.newAssignment('AA','Ground Type 1')
        self.newAssignment('AB','K9 (HBD)')
        self.newAssignment('AG','K9 (HRD)')
        self.newAssignment('AK','Ground Type 1')
        self.newAssignment('AL','Ground Type 2')
        self.newAssignment('ZZ','Ground Type 2')
        self.pair('AA','101')
        self.pair('AB','102')

        self.showTeams()
        
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

    def newTeam(self,name=None,resource=None):
        if not name:
            name=self.nextCallsign
            self.incrementNextCallsign()
        resource=resource or 'Ground Type 2'
        r=tdbNewTeam(name,resource)
        Logger.info('return from newTeam:')
        Logger.info(r)

    def incrementNextCallsign(self):
        if self.nextCallsign.isnumeric():
            self.nextCallsign=str(int(self.nextCallsign)+1)

    # def assign(self,assignmentName,teamName):
    #     tdbAssign(assignmentName,teamName)

    def newAssignment(self,name=None,intendedResource=None):
        name=name or self.assignmentNamePool.pop(0)
        if name in self.assignmentNamePool:
            self.assignmentNamePool.remove(name)
        intendedResource=intendedResource or 'Ground Type 2'
        r=tdbNewAssignment(name,intendedResource)
        Logger.info('return from newAssignment:')
        Logger.info(r)

    def startup(self,*args,allowRecoverIfNeeded=True):
        # perform startup tasks here that should take place after the GUI is alive:
        # - check for connections (cloud and LAN(s))
        Logger.info("startup called")
        # createAssignmentsTableIfNeeded()
        # createTeamsTableIfNeeded()

    # def setKeepScreenOn(self):
    #     toast("setKeepScreenOn called")
    #     pass
#         View = autoclass('android.view.View') # to avoid JVM exception re: original thread
#         Params = autoclass('android.view.WindowManager$LayoutParams')
#         PythonActivity.mActivity.getWindow().addFlags(Params.FLAG_KEEP_SCREEN_ON)
        
    # def clearKeepScreenOn(self):
    #     toast("clearKeepScreenOn called")
    #     pass
#         View = autoclass('android.view.View') # to avoid JVM exception re: original thread
#         Params = autoclass('android.view.WindowManager$LayoutParams')
#         PythonActivity.mActivity.getWindow().clearFlags(Params.FLAG_KEEP_SCREEN_ON)

    def buildTeamsList(self):
        Logger.info('****************** buildTeamsList called')
        self.teamsList=[]
        tdbTeams=tdbGetTeams()
        tdbPairings=tdbGetPairings()
        for entry in tdbTeams:
            id=entry['TeamID']
            pairings=[x for x in tdbPairings if x['TeamID']==id] # pairings that include this team
            assignments=[tdbGetAssignmentNameByID(x["AssignmentID"]) for x in pairings]
            # Logger.info('Assignments for '+str(entry['TeamName'])+':'+str(assignments))
            self.teamsList.append([
                entry['TeamName'],
                entry['TeamStatus'],
                entry['Resource'],
                ','.join(assignments),
                '--'])
        Logger.info('teamsList at end of buildTeamsList:'+str(self.teamsList))

    def buildAssignmentsList(self):
        Logger.info('******************** buildAssignmentsList called')
        self.assignmentsList=[]
        self.previousAssignments=[]
        tdbAssignments=tdbGetAssignments()
        tdbPairings=tdbGetPairings()
        for entry in tdbAssignments:
            id=entry['AssignmentID']
            assignmentName=entry['AssignmentName']
            assignmentStatus=entry['AssignmentStatus']
            previous=[]
            current=[]
            pairings=[x for x in tdbPairings if x['AssignmentID']==id] # pairings that include this assignment
            if pairings:
                for pairing in pairings:
                    if pairing["PreviousFlag"]==1:
                        previous.append(tdbGetTeamNameByID(pairing["TeamID"]))
                    else:
                        current.append(tdbGetTeamNameByID(pairing["TeamID"]))
            else:
                self.assignmentsList.append([assignmentName,'--',assignmentStatus,tdbGetAssignmentIntendedResourceByName(assignmentName)])
            for teamName in current:
                self.assignmentsList.append([assignmentName,teamName,tdbGetTeamStatusByName(teamName),tdbGetTeamResourceByName(teamName)])
            for teamName in previous:
                self.previousAssignments.append([assignmentName,teamName,'COMPLETED',tdbGetTeamResourceByName(teamName)])
        self.assignmentsList+=self.previousAssignments # list completed assignments at the end, until a separate list display is arranged

    def showTeams(self,*args):
        Logger.info('showTeams called')                    
        self.teamsScreen.ids.viewSwitcher.ids.teamsViewButton.font_size='40sp'
        self.teamsScreen.ids.viewSwitcher.ids.assignmentsViewButton.font_size='20sp'
        self.buildTeamsList()
        # recycleview needs a single list of strings; it divides into rows every nth element
        self.teamsScreen.teamsRVList=[]
        for entry in self.teamsList:
            row=copy.deepcopy(entry)
            self.teamsScreen.teamsRVList=self.teamsScreen.teamsRVList+row
        self.sm.transition=NoTransition()
        self.sm.current='teamsScreen'

    def showAssignments(self,*args):
        Logger.info("showAssignments called")
        self.assignmentsScreen.ids.viewSwitcher.ids.teamsViewButton.font_size='20sp'
        self.assignmentsScreen.ids.viewSwitcher.ids.assignmentsViewButton.font_size='40sp'
        self.buildAssignmentsList()
        # recycleview needs a single list of strings; it divides into rows every nth element
        self.assignmentsScreen.assignmentsRVList=[]
        for entry in self.assignmentsList:
            row=copy.deepcopy(entry)
            self.assignmentsScreen.assignmentsRVList=self.assignmentsScreen.assignmentsRVList+row
        self.sm.transition=NoTransition()
        self.sm.current='assignmentsScreen'

    def showAssignmentDetail(self,assignmentName):
        Logger.info("showAssignmentDetail called:"+str(assignmentName))
        self.assignmentDetailScreen.ids.assignmentNameLabel.text=assignmentName
        self.assignmentDetailBeingShown=assignmentName
        self.sm.current='assignmentDetailScreen'

    def showNewTeam(self,*args):
        Logger.info('showNewTeam called')
        self.sm.current='newTeamScreen'

    def showNewAssignment(self,*args):
        Logger.info('showNewAssignment called')
        self.sm.current='newAssignmentScreen'

    def showPairing(self,assignmentName):
        Logger.info("showPairing called: "+str(assignmentName))
        self.pairingScreen.ids.changePairingLabel.text=assignmentName
        self.pairingScreen.ids.pairingBox.clear_widgets() # potential memory hole if widgets aren't gc'ed?
        unassignedTeamNameList=[x[0] for x in self.teamsList if x[1]=='UNASSIGNED']
        # self.pairingScreen.add_widget(BoxLayout(id='pairingBox',orientation='vertical'))
        if unassignedTeamNameList:
            for unassignedTeam in unassignedTeamNameList:
                btn=Button(text=unassignedTeam,size_hint_y=None,height=44)
                btn.bind(on_release=lambda btn: theApp.pair(assignmentName,btn.text))
                self.pairingScreen.ids.pairingBox.add_widget(btn)
        else:
            label=Label(text='No unassigned teams',size_hint_y=None,height=88)
            self.pairingScreen.ids.pairingBox.add_widget(label)
        self.sm.current='pairingScreen'

    def pair(self,assignmentName,teamName):
        Logger.info("pairing assignment "+str(assignmentName)+" with team "+str(teamName))
        tdbPair(tdbGetAssignmentIDByName(assignmentName),tdbGetTeamIDByName(teamName))
        tdbSetTeamStatusByName(teamName,'ASSIGNED')
        tdbSetAssignmentStatusByName(assignmentName,'ASSIGNED')

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
                assignmentName=str(theApp.assignmentsScreen.ids.assignmentsRV.data[rowNum*colCount]["text"])
                bg=theApp.assignmentsScreen.ids.assignmentsRV.data[self.index]['bg']
                if bg[1]==0:
                    newBg=(0,0.8,0.1,0.7)
                else:
                    newBg=(0,0,0,0)
                for i in list(range(rowNum*colCount,(rowNum+1)*colCount)):
                    theApp.assignmentsScreen.ids.assignmentsRV.data[i]['bg']=newBg
                theApp.assignmentsScreen.ids.assignmentsRV.refresh_from_data()
                theApp.showAssignmentDetail(assignmentName)
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


class AssignmentDetailScreen(Screen):
    assignmentDetailCurrentRVList=ListProperty([])
    assignmentDetailPreviousRVList=ListProperty([])


class NewTeamScreen(Screen):
    pass


class NewAssignmentScreen(Screen):
    pass


class PairingScreen(Screen):
    pass


if __name__ == '__main__':
    theApp=assignmentTrackerApp()
    theApp.run()
    