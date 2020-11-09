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

        # start with a clean database every time the app is started
        #  (need to implement auto-recover)
        os.remove('tracker.db')

        # for each screen, example myScreen1 as instance of class myScreen:
        # 1. define myScreen in .kv
        # 2. class myScreen(Screen) - define any needed properties
        # 3. self.sm.add_widget(myScreen(name='myScreen1'))
        # 4. self.myScreen1=self.sm.get_screen('myScreen1')
        self.sm.add_widget(TeamsScreen(name='teams'))
        self.teams=self.sm.get_screen('teams')

        self.sm.add_widget(AssignmentsScreen(name='assignments'))
        self.assignments=self.sm.get_screen('assignments')

        self.newTeam(['101','Working','Ground Type 1','AA','AK'])
        self.newTeam(['102','Enroute to CP','K9 (HRD)','AB','AG'])

        self.newAssignment(['AA','INPROGRESS','Ground Type 1'])
        self.newAssignment(['AB','INPROGRESS','K9 (HBD)'])
        self.newAssignment(['AG','COMPLETED','K9 (HRD)'])
        self.newAssignment(['AK','COMPLETED','Ground Type 1'])
        self.newAssignment(['AL','PREPARED','Ground Type 2'])
        self.newAssignment(['ZZ','PREPARED','Ground Type 2'])
            
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

    def newTeam(self,theList):
        r=tdbNewTeam(dict(zip([x[0] for x in TEAM_COLS],theList)))
        Logger.info("return from newTeam:")
        Logger.info(r)

    def newAssignment(self,theList):
        r=tdbNewAssignment(dict(zip([x[0] for x in ASSIGNMENT_COLS],theList)))
        Logger.info("return from newAssignment:")
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
        Logger.info("buildTeamsList called")
        self.teamsList=[]
        tdbTeams=tdbGetTeams()
        Logger.info(json.dumps(tdbTeams))
        for entry in tdbTeams:
            self.teamsList.append(list(entry.values())[1:])
        Logger.info("teamsList at end of buildTeamsList:"+str(self.teamsList))

    def buildAssignmentsList(self):
        Logger.info("buildAssignmentsList called")
        self.assignmentsList=[]
        self.completedAssignments=[]
        tdbTeams=tdbGetTeams()
        tdbAssignments=tdbGetAssignments()
        Logger.info(json.dumps(tdbAssignments))
        for entry in tdbAssignments:
            assignmentName=entry["AssignmentName"]
            if entry["AssignmentStatus"]=='COMPLETED':
                completedTeams=[x for x in tdbTeams if assignmentName in x['CompletedAssignments']]
                for team in completedTeams:
                    self.completedAssignments.append([assignmentName,team['TeamName'],'COMPLETED',team['Resource']])
            else:
                currentTeams=[x for x in tdbTeams if assignmentName in x['CurrentAssignments']]
                Logger.info("currentTeams:")
                Logger.info(currentTeams)
                if currentTeams:
                    for team in currentTeams:
                        self.assignmentsList.append([assignmentName,team['TeamName'],team['TeamStatus'],team['Resource']])
                else:
                    self.assignmentsList.append([assignmentName,'---','UNASSIGNED',entry['IntendedResource']])
        self.assignmentsList+=self.completedAssignments # until a separate list display is arranged

    def showTeams(self,*args):
        Logger.info("showTeams called")                    
        self.teams.ids.viewSwitcher.ids.teamsViewButton.font_size='40sp'
        self.teams.ids.viewSwitcher.ids.assignmentsViewButton.font_size='20sp'
        self.buildTeamsList()
        # recycleview needs a single list of strings; it divides into rows every nth element
        self.teams.teamsRVList=[]
        for entry in self.teamsList:
            row=copy.deepcopy(entry)
            self.teams.teamsRVList=self.teams.teamsRVList+row
        self.sm.transition=NoTransition()
        self.sm.current='teams'

    def showAssignments(self,*args):
        Logger.info("showAssignments called")
        self.assignments.ids.viewSwitcher.ids.teamsViewButton.font_size='20sp'
        self.assignments.ids.viewSwitcher.ids.assignmentsViewButton.font_size='40sp'
        self.buildAssignmentsList()
        # recycleview needs a single list of strings; it divides into rows every nth element
        self.assignments.assignmentsRVList=[]
        for entry in self.assignmentsList:
            row=copy.deepcopy(entry)
            self.assignments.assignmentsRVList=self.assignments.assignmentsRVList+row
        self.sm.transition=NoTransition()
        self.sm.current='assignments'

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
        ''' Add selection on touch down '''
        if super(SelectableLabel, self).on_touch_down(touch):
            return True
        if self.collide_point(*touch.pos) and self.selectable:
            if theApp.sm.current=='theList':
                colCount=theApp.theList.ids.theGridLayout.cols
                Logger.info("List item tapped: index="+str(self.index)+":"+str(theApp.theList.ids.theGrid.data[self.index]))
                rowNum=int(self.index/colCount)
                bg=theApp.theList.ids.theGrid.data[self.index]['bg']
                if bg[1]==0:
                    newBg=(0,0.8,0.1,0.7)
                else:
                    newBg=(0,0,0,0)
                for i in list(range(rowNum*colCount,(rowNum+1)*colCount)):
                    theApp.theList.ids.theGrid.data[i]['bg']=newBg
                theApp.theList.ids.theGrid.refresh_from_data()
                return True
            else:
                return self.parent.select_with_touch(self.index, touch)

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


if __name__ == '__main__':
    theApp=assignmentTrackerApp()
    theApp.run()
    