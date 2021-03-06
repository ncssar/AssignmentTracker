# #############################################################################
#
#  assignmentTracker_db.py - sqlite3 database layer code for assignmentTracker app
#     this code is meant to be called from the app running on a local node,
#     and also by the API code running on the server
#
#  assignmentTracker is developed for Nevada County Sheriff's Search and Rescue
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
#  11-3-20    TMG            First commit; initially copied from signin_db.py
# #############################################################################

import sqlite3
import json
import time
import os
import re
import logging
from websocket import create_connection # not websockets; websocket (singular) allows simple synchronous send

# use one table for teams, one table for assignments, and reduce duplication of data;
#  store the pairing data in a separete table

# NOTE regarding ID values:
# tid = team ID; aid = assignment ID; pid = pairing ID
# these values are set to -1 when created on a client, or a positive integer when
#  created on the host.  The positive integer id is sent to all clients
#  as part of the new object http request response, whether the request was made
#  by the creating client, or by sync.  So, if id is -1 in steady state, either host
#  communication has been lost, or the host had an error, or there is no host.

TEAM_COLS=[
    # n is hardcoded as the primary key
    ["tid","INTEGER"],
    ["TeamName","TEXT"],
    ["TeamStatus","TEXT DEFAULT 'UNASSIGNED'"],
    ["Resource","TEXT DEFAULT 'GROUND'"],
    ["Medical","TEXT DEFAULT 'NO'"],
    ["LastEditEpoch","REAL"]]

ASSIGNMENT_COLS=[
    # n is hardcoded as the primary key
    ["aid","INTEGER"],
    ["AssignmentName","TEXT"],
    ["AssignmentStatus","TEXT DEFAULT 'UNASSIGNED'"], # either UNASSIGNED or ASSIGNED
    ["IntendedResource","TEXT DEFAULT 'GROUND'"],
    ["sid","TEXT DEFAULT ''"], # sartopo assignment id
    ["LastEditEpoch","REAL"]]

PAIRING_COLS=[
    # n is hardcoded as the primary key
    ["pid","INTEGER"],
    ["aid","INTEGER"],
    ["tid","INTEGER"],
    ["PairingStatus","TEXT DEFAULT 'CURRENT'"],  # CURRENT or PREVIOUS
    ["NameSave","TEXT"],
    ["ResourceSave","TEXT"],
    ["LastEditEpoch","REAL"]]

# History table: all activities are recorded in one table; each entry
#   has columns for aid, tid, Entry, RecordedBy, Epoch;
#   viewing the history can then be filtered by assignment, by team, 
#   or by pairing (assignment/team combination)

HISTORY_COLS=[
    # n is hardcoded as the primary key
    ["hid","INTEGER"],
    ["aid","INTEGER"],
    ["tid","INTEGER"],
    ["Entry","TEXT"],
    ["RecordedBy","TEXT"],
    ["Epoch","INTEGER"]]

TEAM_STATUSES=["UNASSIGNED","ASSIGNED","WORKING","ENROUTE TO IC","DEBRIEFING"]

host=False # is this running on a web server host?
nextAid=1 # only used if this is the host
nextTid=1 # only used if this is the host
nextPid=1 # only used if this is the host
nextHid=1 # only used if this is the host

# websockets default values
url=""
wsOk=False

# pythonanywhere.com does not provide the websockets module, so, it cannot
#  act as the websockets repeater.  Intranet or localhost can run the
#  websockets repeater server.  If this code is running on pythonanywhere,
#  use pusher to send websockets instead.  (Pythonanywhere might be able
#  to send synchronous websockets using the 'websocket' module, but, we
#  would not have an actual URL of a repeater to send to.)

# Web (http) servers could be running on pythonanywhere, on a LAN server, and/or
#  on localhost.
# No individual web server will know, when it starts, what other web server(s)
#  are in use.  Only one web server should send websockets (by whatever method).
#  Only the first client to start will know which http server should send websockets.

wsUseURL=True # use URL for websockets by default
if 'PYTHONANYWHERE_DOMAIN' in os.environ:
    wsUseURL=False # use pusher.com instead
    import pusher
    pusher_client = pusher.Pusher(
        app_id = os.getenv('TRACKER_PUSHER_APPID'),
        key = os.getenv('TRACKER_PUSHER_KEY'),
        secret = os.getenv('TRACKER_PUSHER_SECRET'),
        cluster = os.getenv('TRACKER_PUSHER_CLUSTER'),
        ssl=True)

# needed to make query return values dictionaries instead of lists of tuples
def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

# each machine running this code will have its own local database file tracker.db;
#  they are kept separate by the fact that only one separate instance of this code
#  is running on each machine involved (one on each server, one on each client)
def q(query,params=None):
    # logging.info("q called logger: "+query)
    conn = sqlite3.connect('tracker.db')
    conn.row_factory = dict_factory # so that return value is a dict instead of tuples
    cur = conn.cursor()
    # fetchall if params is blank seems to only return a tuple, not a dict
    
    try:
        if params is not None:
            r=cur.execute(query,params).fetchall()
        else:
            r=cur.execute(query).fetchall()
        conn.commit()
    except:
        logging.warning("ERROR during SQL query:")
        logging.warning("  query='"+str(query)+"'")
        logging.warning("  params='"+str(params)+"'")
        return None
    # for update requests, return the number of rows affected
    if query.lower().startswith('update'):
        return cur.rowcount
    # logging.info("  result:" +str(r))
    return r

def wsCheck(url):
    if wsUseURL:
        try:
            ws=create_connection(url,1) # 1 second timeout
        except:
            return False
        else:
            ws.close()
            return True
    else:
        return True

def wsSend(msg,wsUrl=None):
    wsUrl=wsUrl or url # use the global url normally
    # logging.info("sending - wsUseURL="+str(wsUseURL))
    if wsUseURL:
        try:
            ws=create_connection(wsUrl,1) # 1 second timeout
            ws.send(json.dumps({'msg':msg}))
            ws.close()
            logging.info("websocket send to "+wsUrl+" successful")
        except:
            logging.info("websocket send to "+wsUrl+" failed")
    else: # use pusher.com
        try:
            pusher_client.trigger('my-channel', 'my-event', {'msg': msg})
        except Exception as e:
            logging.info("pusher send failed: "+str(e))

def createTeamsTableIfNeeded():
    colString="'n' INTEGER PRIMARY KEY AUTOINCREMENT,"
    colString+=', '.join([str(x[0])+" "+str(x[1]) for x in TEAM_COLS])
    query='CREATE TABLE IF NOT EXISTS "Teams" ('+colString+');'
    return q(query)

def createAssignmentsTableIfNeeded():
    colString="'n' INTEGER PRIMARY KEY AUTOINCREMENT,"
    colString+=', '.join([str(x[0])+" "+str(x[1]) for x in ASSIGNMENT_COLS])
    query='CREATE TABLE IF NOT EXISTS "Assignments" ('+colString+');'
    return q(query)

def createPairingsTableIfNeeded():
    colString="'n' INTEGER PRIMARY KEY AUTOINCREMENT,"
    colString+=', '.join([str(x[0])+" "+str(x[1]) for x in PAIRING_COLS])
    query='CREATE TABLE IF NOT EXISTS "Pairings" ('+colString+');'
    return q(query)

def createHistoryTableIfNeeded():
    colString="'n' INTEGER PRIMARY KEY AUTOINCREMENT,"
    colString+=', '.join([str(x[0])+" "+str(x[1]) for x in HISTORY_COLS])
    query='CREATE TABLE IF NOT EXISTS "History" ('+colString+');'
    return q(query)

# tdbInit will only be called once, when the first node joins
def tdbInit(server=None):
    logging.info('tdbInit called: server='+str(server))
    if os.path.exists('tracker.db'):
        os.remove('tracker.db')
    createTeamsTableIfNeeded()
    createAssignmentsTableIfNeeded()
    createPairingsTableIfNeeded()
    createHistoryTableIfNeeded()
    if server:
        wsUrl='ws://'+re.sub(':.*$','',server)+':80'
        global wsOk
        global url
        global host
        global nextTid
        global nextAid
        global nextPid
        nextTid=1 # only used if this is the host
        nextAid=1 # only used if this is the host
        nextPid=1 # only used if this is the host
        host=True
        wsOk=wsCheck(wsUrl)
        url=wsUrl
        tdbPushTables()
        logging.info("wsCheck "+url+" : "+str(wsOk))

# insert using db parameters to avoid SQL injection attack and to correctly handle None
def qInsert(tableName,d):
    # logging.info("qInsert called: tableName="+str(tableName)+"  d="+str(d))
    colList="({columns})".format(
            columns=', '.join(d.keys()))
    valList="({columns})".format(
            columns=", ".join([":"+str(x) for x in d.keys()]))
    query="INSERT INTO '{tablename}' {colList} VALUES {valList};".format(
            tablename=tableName,
            colList=colList,
            valList=valList)
    return q(query,d)
    
#####################################
## BEGIN SDB FUNCTIONS
#####################################
## tdb = 'tracker database'
## these functions are called directly from kivy / python code running locally
##   on client nodes, and also from API handlers running on the server(s)
## return values from these functions do not need to be jsonified, since this
##   code is called from other python code in one way or another; the API
##   handlers that call this code should perform jsonification, while client
##   nodes do not need to do any jsonification

def tdbNewTeam(name,resource,status=None,medical='NO',tid=None,lastEditEpoch=None):
    # status, tid, and lastEditEpoch arguments will only exist if this is being called from sync handler
    if host: # this clause will only run on the host
        global nextTid
        tid=nextTid
        nextTid+=1
    else:
        tid=tid or -1
    lee=lastEditEpoch or round(time.time(),2)
    d={}
    d['tid']=tid
    d['TeamName']=name
    d['Resource']=resource
    d['Medical']=medical
    d['LastEditEpoch']=lee
    if status: # use the default status unless specified
        d['TeamStatus']=status
        logging.info("  inserting d:"+str(d))
    qInsert('Teams',d)
    r=q('SELECT * FROM Teams ORDER BY n DESC LIMIT 1;')
    # when called from sync handler: don't write a history entry
    if not status: # status arg will only exist when called from sync handler
        if host:
            tdbAddHistoryEntry('New Team: '+name,tid=r[0]['tid'],recordedBy='SYSTEM')
    validate=r[0]
    tdbPushTables()
    return {'validate':validate}

def tdbNewAssignment(name,intendedResource,status=None,aid=None,sid=None,lastEditEpoch=None):
    # status, aid, and lastEditEpoch arguments will only exist if this is being called from sync handler
    if host:
        global nextAid
        aid=nextAid
        nextAid+=1
    else:
        aid=aid or -1
    lee=lastEditEpoch or round(time.time(),2)
    d={}
    d['aid']=aid
    d['AssignmentName']=name
    d['IntendedResource']=intendedResource
    d['LastEditEpoch']=lee
    if status: # use the default status unless specified
        d['AssignmentStatus']=status
    if sid:
        d['sid']=sid
    qInsert('Assignments',d)
    r=q('SELECT * FROM Assignments ORDER BY n DESC LIMIT 1;')
    # when called from sync handler: don't write a history entry
    if not status: # status arg will only exist when called from sync handler
        if host:
            tdbAddHistoryEntry('New Assignment: '+name,aid=r[0]['aid'],recordedBy='SYSTEM')
    validate=r[0]
    tdbPushTables()
    return {'validate':validate}

def tdbNewPairing(aid,tid,status=None,pid=None,lastEditEpoch=None):
    if host:
        global nextPid
        pid=nextPid
        nextPid+=1
    else:
        pid=pid or -1
    lee=lastEditEpoch or round(time.time(),2)
    d={}
    d['pid']=pid
    d['aid']=aid
    d['tid']=tid
    d['LastEditEpoch']=lee
    if status: # use the default status unless specified
        d['PairingStatus']=status
    assignmentName=tdbGetAssignmentNameByID(aid)
    teamName=tdbGetTeamNameByID(tid)
    # when called from sync handler: leave team and assignment status as they are,
    #  and don't write a history entry
    if not status: # status arg will only exist when called from sync handler
        tdbSetTeamStatusByID(tid,'ASSIGNED',push=False) # don't push tables yet
        tdbSetAssignmentStatusByID(aid,'ASSIGNED',push=False) # don't push tables yet
        if host:
            tdbAddHistoryEntry('New Pairing: '+assignmentName+'+'+teamName,aid=aid,tid=tid,recordedBy='SYSTEM')
    qInsert('Pairings',d)
    r=q('SELECT * FROM Pairings ORDER BY n DESC LIMIT 1;')
    validate=r[0]
    tdbPushTables()
    return {'validate':validate}

def tdbNewTeamFinalize(n,tid,lastEditEpoch):
    # logging.info("New team finalize:"+str(n)+"="+str(tid))
    q("UPDATE 'Teams' SET tid = '"+str(tid)+"', LastEditEpoch = '"+str(lastEditEpoch)+"' WHERE n = '"+str(n)+"';")

def tdbNewAssignmentFinalize(n,aid,lastEditEpoch):
    # logging.info("New assignment finalize:"+str(n)+"="+str(aid))
    q("UPDATE 'Assignments' SET aid = '"+str(aid)+"', LastEditEpoch = '"+str(lastEditEpoch)+"' WHERE n = '"+str(n)+"';")

def tdbNewPairingFinalize(n,pid,lastEditEpoch):
    # logging.info("New pairing finalize:"+str(n)+"="+str(pid))
    q("UPDATE 'Pairings' SET pid = '"+str(pid)+"', LastEditEpoch = '"+str(lastEditEpoch)+"' WHERE n = '"+str(n)+"';")

# no need to finalize history entries:
#  all history entries are initially created on the server anyway;
#  a client will never need to push a new history entry to the server;
#  all the interactive calls are done by API request, and the API
#  request handler on the server will make the new history entry.

# def tdbNewHistoryEntryFinalize(n,hid,epoch):
#     # logging.info("New pairing finalize:"+str(n)+"="+str(pid))
#     q("UPDATE 'History' SET hid = '"+str(hid)+"', Epoch = '"+str(epoch)+"' WHERE n = '"+str(n)+"';")

# tdbHome - return a welcome message to verify that this code is running
def tdbHome():
    return '''<h1>AssignmentTracker Database API</h1>
            <p>API for interacting with the Assignment Tracker databases</p>'''


# team getters
def tdbGetTeamIDByName(teamName):
    query="SELECT tid FROM 'Teams' WHERE TeamName='"+str(teamName)+"';"
    # logging.info("query:"+query)
    r=q(query)
    # logging.info("response:"+str(r))
    if type(r) is list and len(r)>0 and type(r[0]) is dict:
        return r[0].get("tid",None)
    else:
        return None

def tdbGetTeamNameByID(tid):
    query="SELECT TeamName FROM 'Teams' WHERE tid='"+str(tid)+"';"
    # logging.info("query:"+query)
    r=q(query)
    # logging.info("response:"+str(r))
    if type(r) is list and len(r)>0 and type(r[0]) is dict:
        return r[0].get("TeamName",None)
    else:
        return None

def tdbGetTeamStatusByName(teamName):
    query="SELECT TeamStatus FROM 'Teams' WHERE TeamName='"+str(teamName)+"';"
    # logging.info("query:"+query)
    r=q(query)
    # logging.info("response:"+str(r))
    if type(r) is list and len(r)>0 and type(r[0]) is dict:
        return r[0].get("TeamStatus",None)
    else:
        return None

def tdbGetTeamResourceByName(teamName):
    query="SELECT Resource FROM 'Teams' WHERE TeamName='"+str(teamName)+"';"
    # logging.info("query:"+query)
    r=q(query)
    # logging.info("response:"+str(r))
    if type(r) is list and len(r)>0 and type(r[0]) is dict:
        return r[0].get("Resource",None)
    else:
        return None

def tdbGetTeamMedicalByName(teamName):
    query="SELECT Medical FROM 'Teams' WHERE TeamName='"+str(teamName)+"';"
    # logging.info("query:"+query)
    r=q(query)
    # logging.info("response:"+str(r))
    if type(r) is list and len(r)>0 and type(r[0]) is dict:
        return r[0].get("Medical",None)
    else:
        return None

# assignment getters
def tdbGetAssignmentNameByID(aid):
    query="SELECT AssignmentName FROM 'Assignments' WHERE aid='"+str(aid)+"';"
    # logging.info("query:"+query)
    r=q(query)
    # logging.info("response:"+str(r))
    if type(r) is list and len(r)>0 and type(r[0]) is dict:
        return r[0].get("AssignmentName",None)
    else:
        return None

def tdbGetAssignmentIDByName(assignmentName):
    query="SELECT aid FROM 'Assignments' WHERE AssignmentName='"+str(assignmentName)+"';"
    # logging.info("query:"+query)
    r=q(query)
    # logging.info("response:"+str(r))
    if type(r) is list and len(r)>0 and type(r[0]) is dict:
        return r[0].get("aid",None)
    else:
        return None

def tdbGetAssignmentStatusByName(assignmentName):
    query="SELECT AssignmentStatus FROM 'Assignments' WHERE AssignmentName='"+str(assignmentName)+"';"
    # logging.info("query:"+query)
    r=q(query)
    # logging.info("response:"+str(r))
    if type(r) is list and len(r)>0 and type(r[0]) is dict:
        return r[0].get("AssignmentStatus",None)
    else:
        return None

def tdbGetAssignmentIntendedResourceByName(assignmentName):
    query="SELECT IntendedResource FROM 'Assignments' WHERE AssignmentName='"+str(assignmentName)+"';"
    # logging.info("query:"+query)
    r=q(query)
    # logging.info("response:"+str(r))
    if type(r) is list and len(r)>0 and type(r[0]) is dict:
        return r[0].get("IntendedResource",None)
    else:
        return None


def tdbGetTeams(tid=None,since=None):
    if tid:
        condition='tid='+str(tid)
        if since:
            condition+=' AND LastEditEpoch > '+str(since)
    elif since:
        condition='LastEditEpoch > '+str(since)
    else:
        condition='1'
    return q("SELECT * FROM 'Teams' WHERE {condition};".format(
            condition=condition))

# tdbGetTeamsView - return a list of rows, which can be used directly by kivy
#    to create the teams view RecycleView data, or, to generate the html table
#    for downstream html views i.e. pushed using websockets
def tdbGetTeamsView():
    # logging.info('****************** tdbGetTeamsView called')
    teamsList=[]
    tdbTeams=tdbGetTeams()
    tdbPairings=tdbGetPairings()
    for entry in tdbTeams:
        tid=entry['tid']
        pairings=[x for x in tdbPairings if x['tid']==tid] # pairings that include this team
        currentPairings=[x for x in pairings if x['PairingStatus']=='CURRENT']
        previousPairings=[x for x in pairings if x['PairingStatus']=='PREVIOUS']
        currentAssignments=[tdbGetAssignmentNameByID(x['aid']) for x in currentPairings]
        previousAssignments=[tdbGetAssignmentNameByID(x['aid']) for x in previousPairings]
        # Logger.info('Assignments for '+str(entry['TeamName'])+':'+str(assignments))
        teamsList.append([
            entry['TeamName'],
            ','.join(currentAssignments) or '--',
            entry['TeamStatus'],
            entry['Resource'],
            ','.join(previousAssignments) or '--'])
    # logging.info('teamsList at end of tdbGetTeamsView:'+str(teamsList))
    return teamsList

def tdbGetMedicalTeams():
    r=q("SELECT TeamName FROM 'Teams' WHERE Medical == 'YES'")
    return [x['TeamName'] for x in r]

# tdbUpdateTables can also be used to get the team and assignment counts
#  but, can't use the assignments view since it's actually a list of
#  pairings, and there may be more than one entry per assignment, so, 
#  use other db functions to get the accurate count of assigned assignments
def tdbPushTables(teamsViewList=None,assignmentsViewList=None):
    if not teamsViewList:
        teamsViewList=tdbGetTeamsView()
    if not assignmentsViewList: # completed assignments should be part of assignmentsViewList
        assignmentsViewList=tdbGetAssignmentsView()
    teamsViewAssignedList=[x for x in teamsViewList if x[2]!='UNASSIGNED']
    teamsViewUnassignedList=[x for x in teamsViewList if x[2]=='UNASSIGNED']
    assignmentsViewAssignedList=[x for x in assignmentsViewList if x[2] not in ['UNASSIGNED','COMPLETED']]
    assignmentsViewUnassignedList=[x for x in assignmentsViewList if x[2]=='UNASSIGNED']
    assignmentsViewCompletedList=[x for x in assignmentsViewList if x[2]=='COMPLETED']
    medicalTeamsList=tdbGetMedicalTeams()
    d={
        "teamsViewAssigned":teamsViewAssignedList,
        "teamsViewUnassigned":teamsViewUnassignedList,
        "assignmentsViewAssigned":assignmentsViewAssignedList,
        "assignmentsViewUnassigned":assignmentsViewUnassignedList,
        "assignmentsViewCompleted":assignmentsViewCompletedList,
        "assignedTeamsCount":len(teamsViewAssignedList),
        "unassignedTeamsCount":len(teamsViewUnassignedList),
        "assignedAssignmentsCount":len(assignmentsViewAssignedList),
        "unassignedAssignmentsCount":len(assignmentsViewUnassignedList),
        "completedAssignmentsCount":len(assignmentsViewCompletedList),
        "medicalTeams":medicalTeamsList}
    if wsOk: # wsSend will send over URL or over pusher.com as appropriate
        wsSend(json.dumps(d))
    return(d)

def tdbGetAssignments(aid=None,since=None):
    if aid:
        condition='aid='+str(aid)
        if since:
            condition+=' AND LastEditEpoch > '+str(since)
    elif since:
        condition='LastEditEpoch > '+str(since)
    else:
        condition='1'
    return q("SELECT * FROM 'Assignments' WHERE {condition};".format(
            condition=condition))

def tdbGetAssignmentsView():
    # note that this is really a list of pairings (one pairing per row), unpaired assignments, and completed assignments
    assignmentsList=[]
    previousAssignments=[]
    tdbAssignments=tdbGetAssignments()
    tdbPairings=tdbGetPairings()
    for entry in tdbAssignments:
        aid=entry['aid']
        assignmentName=entry['AssignmentName']
        assignmentStatus=entry['AssignmentStatus']
        current=[]
        pairings=[x for x in tdbPairings if x['aid']==aid] # pairings that include this assignment
        if pairings:
            logging.info("  pairings:"+str(pairings))
            for pairing in pairings:
                if pairing['PairingStatus']=='PREVIOUS':
                    previousAssignments.append([assignmentName,pairing['NameSave'],'COMPLETED',pairing['ResourceSave']])
                else:
                    current.append(tdbGetTeamNameByID(pairing['tid']))
        else:
            assignmentsList.append([assignmentName,'--',assignmentStatus,tdbGetAssignmentIntendedResourceByName(assignmentName)])
        for teamName in current:
            assignmentsList.append([assignmentName,teamName,tdbGetTeamStatusByName(teamName),tdbGetTeamResourceByName(teamName)])
    assignmentsList+=previousAssignments # list completed assignments at the end, until a separate list display is arranged
    return assignmentsList
    
def tdbGetPairings(pid=None,since=None):
    if pid:
        condition='pid='+str(pid)
        if since:
            condition+=' AND LastEditEpoch > '+str(since)
    elif since:
        condition='LastEditEpoch > '+str(since)
    else:
        condition='1'
    return q("SELECT * FROM 'Pairings' WHERE {condition};".format(
            condition=condition))

def tdbGetPairingsByTeam(tid,currentOnly=False):
    condition='tid='+str(tid)
    if currentOnly:
        condition+=" AND PairingStatus='CURRENT'"
    return q("SELECT * FROM 'Pairings' WHERE {condition};".format(condition=condition))

def tdbGetPairingsByAssignment(aid,currentOnly=False):
    condition='aid='+str(aid)
    if currentOnly:
        condition+=" AND PairingStatus='CURRENT'"
    return q("SELECT * FROM 'Pairings' WHERE {condition};".format(condition=condition))

def tdbGetPairingIDByNames(assignmentName,teamName,currentOnly=False,previousOnly=False):
    aid=tdbGetAssignmentIDByName(assignmentName)
    tid=tdbGetTeamIDByName(teamName)
    condition='aid='+str(aid)+' AND tid='+str(tid)
    if currentOnly:
        condition+=" AND PairingStatus='CURRENT'"
    elif previousOnly:
        condition+=" AND PairingStatus='PREVIOUS'"
    query="SELECT pid FROM 'Pairings' WHERE {condition};".format(condition=condition)
    r=q(query)
    if type(r) is list and len(r)>0:
        return q(query)[0].get('pid',None)
    else:
        return None

def tdbSetPairingStatusByID(pid,status):
    # logging.info("tdbSetPairingStatusByID called: pid="+str(pid)+" status="+str(status))
    [assignmentName,teamName]=tdbGetPairingNamesByID(pid)
    [aid,tid]=tdbGetPairingIDsByID(pid)
    if host:
        tdbAddHistoryEntry(assignmentName+'+'+teamName+' -> '+status,tid=tid,aid=aid)
    # what history entries if any should happen here?
    q("UPDATE 'Pairings' SET PairingStatus = '"+str(status)+"' WHERE pid = '"+str(pid)+"';")
    if status=='PREVIOUS':
        resource=tdbGetTeamResourceByName(teamName)
        q("UPDATE 'Pairings' SET NameSave = '"+str(teamName)+"', ResourceSave = '"+str(resource)+"' WHERE pid = '"+str(pid)+"';")
    r=q("SELECT * FROM 'Pairings' WHERE pid = "+str(pid)+";")
    if r:
        tdbUpdateLastEditEpoch(pid=pid)
        validate=r[0]
        tdbPushTables()
        # logging.info("response in tdbSetPairingStatusByID:"+str(r))
        return {'validate':validate}
    else:
        return {'error':'Query did not return a value'}
    
def tdbSetTeamStatusByID(tid,status,push=True):
    if host:
        tdbAddHistoryEntry(tdbGetTeamNameByID(tid)+' -> '+status,tid=tid,recordedBy='SYSTEM')
    q("UPDATE 'Teams' SET TeamStatus = '"+str(status)+"' WHERE tid = '"+str(tid)+"';")
    r=q("SELECT * FROM 'Teams' WHERE tid = "+str(tid)+";")
    if r:
        tdbUpdateLastEditEpoch(tid=tid)
        validate=r[0]
        if push:
            tdbPushTables()
        return {'validate':validate}
    else:
        return {'error':'Query did not return a value'}

def tdbSetTeamStatusByName(teamName,status,push=True):
    tid=tdbGetTeamIDByName(teamName)
    tdbSetTeamStatusByID(tid,status,push)

def tdbSetAssignmentStatusByID(aid,status,push=True):
    if host:
        tdbAddHistoryEntry(tdbGetAssignmentNameByID(aid)+' -> '+status,aid=aid,recordedBy='SYSTEM')
    q("UPDATE 'Assignments' SET AssignmentStatus = '"+str(status)+"' WHERE aid = '"+str(aid)+"';")
    r=q("SELECT * FROM 'Assignments' WHERE aid = "+str(aid)+";")
    if r:
        tdbUpdateLastEditEpoch(aid=aid)
        validate=r[0]
        if push:
            tdbPushTables()
        return {'validate':validate}
    else:
        return {'error':'Query did not return a value'}

def tdbSetAssignmentStatusByName(assignmentName,status,push=True):
    aid=tdbGetAssignmentIDByName(assignmentName)
    tdbSetAssignmentStatusByID(aid,status,push)

def tdbSetAssignmentIntendedResourceByID(aid,intendedResource,push=True):
    if host:
        tdbAddHistoryEntry(tdbGetAssignmentNameByID(aid)+' -> '+intendedResource,aid=aid,recordedBy='SYSTEM')
    q("UPDATE 'Assignments' SET IntendedResource = '"+str(intendedResource)+"' WHERE aid = '"+str(aid)+"';")
    r=q("SELECT * FROM 'Assignments' WHERE aid = "+str(aid)+";")
    if r:
        tdbUpdateLastEditEpoch(aid=aid)
        validate=r[0]
        if push:
            tdbPushTables()
        return {'validate':validate}
    else:
        return {'error':'Query did not return a value'}

def tdbSetAssignmentIntendedResourceByName(assignmentName,intendedResource,push=True):
    aid=tdbGetAssignmentIDByName(assignmentName)
    tdbSetAssignmentIntendedResourceByID(aid,intendedResource,push)

def tdbSetTeamResourceByID(tid,resource,push=True):
    if host:
        tdbAddHistoryEntry(tdbGetTeamNameByID(tid)+' -> '+resource,tid=tid,recordedBy='SYSTEM')
    q("UPDATE 'Teams' SET Resource = '"+str(resource)+"' WHERE tid = '"+str(tid)+"';")
    r=q("SELECT * FROM 'Teams' WHERE tid = "+str(tid)+";")
    if r:
        tdbUpdateLastEditEpoch(tid=tid)
        validate=r[0]
        if push:
            tdbPushTables()
        return {'validate':validate}
    else:
        return {'error':'Query did not return a value'}

def tdbSetTeamResourceByName(teamName,resource,push=True):
    tid=tdbGetTeamIDByName(teamName)
    tdbSetTeamResourceByID(tid,resource,push)

def tdbSetTeamMedicalByID(tid,medical,push=True):
    if host:
        tdbAddHistoryEntry(tdbGetTeamNameByID(tid)+' Medical -> '+medical,tid=tid,recordedBy='SYSTEM')
    q("UPDATE 'Teams' SET Medical = '"+str(medical)+"' WHERE tid = '"+str(tid)+"';")
    r=q("SELECT * FROM 'Teams' WHERE tid = "+str(tid)+";")
    if r:
        tdbUpdateLastEditEpoch(tid=tid)
        validate=r[0]
        if push:
            tdbPushTables()
        return {'validate':validate}
    else:
        return {'error':'Query did not return a value'}

def tdbSetTeamMedicalByName(teamName,medical,push=True):
    tid=tdbGetTeamIDByName(teamName)
    tdbSetTeamMedicalByID(tid,medical,push)

def tdbDeleteAssignment(aid,push=True):
    if host:
        tdbAddHistoryEntry(tdbGetAssignmentNameByID(aid)+' DELETED',aid=aid,recordedBy='SYSTEM')
    q("DELETE FROM 'Assignments' WHERE aid = '"+str(aid)+"';")
    r=q("SELECT * FROM 'Assignments' WHERE aid = "+str(aid)+";") # should be empty
    if r:
        validate=r[0]
        return {'validate':validate}
    else:
        if push:
            tdbPushTables()
        return {'validate':'assignment deleted'}    

def tdbDeleteTeam(tid,push=True):
    if host:
        tdbAddHistoryEntry(tdbGetTeamNameByID(tid)+' DELETED',tid=tid,recordedBy='SYSTEM')
    q("DELETE FROM 'Teams' WHERE tid = '"+str(tid)+"';")
    r=q("SELECT * FROM 'Teams' WHERE tid = "+str(tid)+";") # should be empty
    if r:
        validate=r[0]
        return {'validate':validate}
    else:
        if push:
            tdbPushTables()
        return {'validate':'assignment deleted'}   

def tdbUpdateLastEditEpoch(tid=None,aid=None,pid=None):
    if not tid and not aid and not pid:
        logging.info("tdbUpdateLastEditEpoch called with no arguments; nothing to do")
        return
    t=round(time.time(),2)
    if tid:
        query="UPDATE 'Teams' SET LastEditEpoch = "+str(t)+" WHERE tid="+str(tid)+";"
        q(query)
    if aid:
        query="UPDATE 'Assignments' SET LastEditEpoch = "+str(t)+" WHERE aid="+str(aid)+";"
        q(query)
    if pid:
        query="UPDATE 'Pairings' SET LastEditEpoch = "+str(t)+" WHERE pid="+str(pid)+";"
        q(query)

def tdbAddHistoryEntry(entry,hid=-1,aid=-1,tid=-1,recordedBy='N/A',epoch=None):
    # only the server can create original history entries; clients can only
    #  create local history entries during sync; hid and epoch arguments will
    #  only exist if this is being called from sync handler
    if host:
        global nextHid
        hid=nextHid
        nextHid+=1
    else:
        hid=hid or -1
    epoch=epoch or round(time.time(),2)
    r=qInsert('History',{
        'hid':hid,
        'aid':aid,
        'tid':tid,
        'Entry':entry,
        'RecordedBy':recordedBy,
        'Epoch':epoch})
    return r

def tdbGetPairingIDsByID(pid=None):
    r=tdbGetPairings(pid)[0]
    return [r['aid'],r['pid']]

def tdbGetPairingNamesByID(pid=None):
    r=tdbGetPairings(pid)[0]
    return [tdbGetAssignmentNameByID(r['aid']),tdbGetTeamNameByID(r['tid'])]

# tdbGetHistory with no arguments will return the entire history table
# tdbGetHistory(since=123) will return all entries with Epoch greater than 123
def tdbGetHistory(aid=None,tid=None,pid=None,useAnd=None,since=0):
    op='OR' # by default, return history entries that involve either the team or the assignment
    if useAnd:
        op='AND' # optionally return history entries that only affect the status of both team and assignment
    if not aid and not tid and not pid:
        if since:
            condition='Epoch > '+str(since)
        else:
            condition='1'
    else:
        if pid:
            [aid,tid]=tdbGetPairingIDsByID(pid)
            op='AND'
        if aid:
            conditionA='aid='+str(aid)
        if tid:
            conditionT='tid='+str(tid)
        if aid and tid:
            condition=conditionA+' '+op+' '+conditionT
        elif aid:
            condition=conditionA
        else:
            condition=conditionT
        if since:
            condition+=' AND Epoch > '+str(since)
    query="SELECT * FROM 'History' WHERE {condition};".format(
            condition=condition)
    return q(query)

