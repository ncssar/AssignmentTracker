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
    ["Resource","TEXT DEFAULT 'Ground Type 2'"],
    ["LastEditEpoch","REAL"]]

ASSIGNMENT_COLS=[
    # n is hardcoded as the primary key
    ["aid","INTEGER"],
    ["AssignmentName","TEXT"],
    ["AssignmentStatus","TEXT DEFAULT 'UNASSIGNED'"], # either UNASSIGNED or ASSIGNED
    ["IntendedResource","TEXT DEFAULT 'Ground Type 2'"],
    ["LastEditEpoch","REAL"]]

PAIRING_COLS=[
    # n is hardcoded as the primary key
    ["pid","INTEGER"],
    ["aid","INTEGER"],
    ["tid","INTEGER"],
    ["PairingStatus","TEXT DEFAULT 'CURRENT'"],  # CURRENT or PREVIOUS
    ["LastEditEpoch","REAL"]]

# History table: all activities are recorded in one table; each entry
#   has columns for aid, tid, Entry, RecordedBy, Epoch;
#   viewing the history can then be filtered by assignment, by team, 
#   or by pairing (assignment/team combination)

HISTORY_COLS=[
    # n is hardcoded as the primary key
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
    # print("q called: "+query)
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
        print("ERROR during SQL query:")
        print("  query='"+str(query)+"'")
        print("  params='"+str(params)+"'")
        return None
    # for update requests, return the number of rows affected
    if query.lower().startswith('update'):
        return cur.rowcount
    # print("  result:" +str(r))
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
    # print("sending - wsUseURL="+str(wsUseURL))
    if wsUseURL:
        try:
            ws=create_connection(wsUrl,1) # 1 second timeout
            ws.send(json.dumps({'msg':msg}))
            ws.close()
            print("websocket send to "+wsUrl+" successful")
        except:
            print("websocket send to "+wsUrl+" failed")
    else: # use pusher.com
        try:
            pusher_client.trigger('my-channel', 'my-event', {'msg': msg})
            print("pusher send successful")
        except Exception as e:
            print("pusher send failed: "+str(e))

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
    print('tdbInit called: server='+str(server))
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
        print("wsCheck "+url+" : "+str(wsOk))

# insert using db parameters to avoid SQL injection attack and to correctly handle None
def qInsert(tableName,d):
    # print("qInsert called: tableName="+str(tableName)+"  d="+str(d))
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

def tdbNewTeam(name,resource,status=None,tid=None,lastEditEpoch=None):
    # status, tid, and lastEditEpoch arguments will only exist if this is being called from tdbProcessSync
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
    d['LastEditEpoch']=lee
    if status: # use the default status unless specified
        d['TeamStatus']=status
    qInsert('Teams',d)
    r=q('SELECT * FROM Teams ORDER BY n DESC LIMIT 1;')
    if not status: # don't add local history entry if called from tdbProcessSync; history is synced
        tdbAddHistoryEntry("Team "+name+" Created",tid=r[0]["tid"],recordedBy='SYSTEM')
    validate=r[0]
    tdbPushTables()
    return {'validate':validate}

def tdbNewAssignment(name,intendedResource,status=None,aid=None,lastEditEpoch=None):
    # status, aid, and lastEditEpoch arguments will only exist if this is being called from tdbProcessSync
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
    qInsert('Assignments',d)
    r=q('SELECT * FROM Assignments ORDER BY n DESC LIMIT 1;')
    if not status: # don't add local history entry if called from tdbProcessSync; history is synced
        tdbAddHistoryEntry("Assignment "+name+" Created",aid=r[0]["aid"],recordedBy='SYSTEM')
    validate=r[0]
    tdbPushTables()
    return {'validate':validate}

def tdbNewPairing(aid,tid):
    if host:
        global nextPid
        pid=nextPid
        nextPid+=1
    else:
        pid=-1
    tdbSetTeamStatusByID(tid,'ASSIGNED',push=False) # don't push tables yet
    tdbSetAssignmentStatusByID(aid,'ASSIGNED',push=False) # don't push tables yet
    assignmentName=tdbGetAssignmentNameByID(aid)
    teamName=tdbGetTeamNameByID(tid)
    tdbAddHistoryEntry("Pairing Created: Assignment "+assignmentName+" <=> Team "+teamName,aid=aid,tid=tid,recordedBy='SYSTEM')
    qInsert('Pairings',{'pid':pid,'aid':aid,'tid':tid,'LastEditEpoch':round(time.time(),2)})
    r=q('SELECT * FROM Pairings ORDER BY n DESC LIMIT 1;')
    validate=r[0]
    tdbPushTables()
    return {'validate':validate}

def tdbNewTeamFinalize(n,tid,lastEditEpoch):
    # print("New team finalize:"+str(n)+"="+str(tid))
    q("UPDATE 'Teams' SET tid = '"+str(tid)+"', LastEditEpoch = '"+str(lastEditEpoch)+"' WHERE n = '"+str(n)+"';")

def tdbNewAssignmentFinalize(n,aid,lastEditEpoch):
    # print("New assignment finalize:"+str(n)+"="+str(aid))
    q("UPDATE 'Assignments' SET aid = '"+str(aid)+"', LastEditEpoch = '"+str(lastEditEpoch)+"' WHERE n = '"+str(n)+"';")

def tdbNewPairingFinalize(n,pid,lastEditEpoch):
    # print("New pairing finalize:"+str(n)+"="+str(pid))
    q("UPDATE 'Pairings' SET pid = '"+str(pid)+"', LastEditEpoch = '"+str(lastEditEpoch)+"' WHERE n = '"+str(n)+"';")

# tdbHome - return a welcome message to verify that this code is running
def tdbHome():
    return '''<h1>AssignmentTracker Database API</h1>
            <p>API for interacting with the Assignment Tracker databases</p>'''


# team getters
def tdbGetTeamIDByName(teamName):
    query="SELECT tid FROM 'Teams' WHERE TeamName='"+str(teamName)+"';"
    # print("query:"+query)
    r=q(query)
    # print("response:"+str(r))
    if type(r) is list and len(r)>0 and type(r[0]) is dict:
        return r[0].get("tid",None)
    else:
        return None

def tdbGetTeamNameByID(tid):
    query="SELECT TeamName FROM 'Teams' WHERE tid='"+str(tid)+"';"
    # print("query:"+query)
    r=q(query)
    # print("response:"+str(r))
    if type(r) is list and len(r)>0 and type(r[0]) is dict:
        return r[0].get("TeamName",None)
    else:
        return None

def tdbGetTeamStatusByName(teamName):
    query="SELECT TeamStatus FROM 'Teams' WHERE TeamName='"+str(teamName)+"';"
    # print("query:"+query)
    r=q(query)
    # print("response:"+str(r))
    if type(r) is list and len(r)>0 and type(r[0]) is dict:
        return r[0].get("TeamStatus",None)
    else:
        return None

def tdbGetTeamResourceByName(teamName):
    query="SELECT Resource FROM 'Teams' WHERE TeamName='"+str(teamName)+"';"
    # print("query:"+query)
    r=q(query)
    # print("response:"+str(r))
    if type(r) is list and len(r)>0 and type(r[0]) is dict:
        return r[0].get("Resource",None)
    else:
        return None


# assignment getters
def tdbGetAssignmentNameByID(aid):
    query="SELECT AssignmentName FROM 'Assignments' WHERE aid='"+str(aid)+"';"
    # print("query:"+query)
    r=q(query)
    # print("response:"+str(r))
    if type(r) is list and len(r)>0 and type(r[0]) is dict:
        return r[0].get("AssignmentName",None)
    else:
        return None

def tdbGetAssignmentIDByName(assignmentName):
    query="SELECT aid FROM 'Assignments' WHERE AssignmentName='"+str(assignmentName)+"';"
    # print("query:"+query)
    r=q(query)
    # print("response:"+str(r))
    if type(r) is list and len(r)>0 and type(r[0]) is dict:
        return r[0].get("aid",None)
    else:
        return None

def tdbGetAssignmentStatusByName(assignmentName):
    query="SELECT AssignmentStatus FROM 'Assignments' WHERE AssignmentName='"+str(assignmentName)+"';"
    # print("query:"+query)
    r=q(query)
    # print("response:"+str(r))
    if type(r) is list and len(r)>0 and type(r[0]) is dict:
        return r[0].get("AssignmentStatus",None)
    else:
        return None

def tdbGetAssignmentIntendedResourceByName(assignmentName):
    query="SELECT IntendedResource FROM 'Assignments' WHERE AssignmentName='"+str(assignmentName)+"';"
    # print("query:"+query)
    r=q(query)
    # print("response:"+str(r))
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
    # print('****************** tdbGetTeamsView called')
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
    # print('teamsList at end of tdbGetTeamsView:'+str(teamsList))
    return teamsList

# tdbUpdateTables can also be used to get the team and assignment counts
#  but, can't use the assignments view since it's actually a list of
#  pairings, and there may be more than one entry per assignment, so, 
#  use other db functions to get the accurate count of assigned assignments
def tdbPushTables(teamsViewList=None,assignmentsViewList=None):
    assignments=tdbGetAssignments() # get all assignments - not pairings
    if not teamsViewList:
        teamsViewList=tdbGetTeamsView()
    if not assignmentsViewList: # completed assignments should be part of assignmentsViewList
        assignmentsViewList=tdbGetAssignmentsView()
    assignmentsViewNotCompletedList=[x for x in assignmentsViewList if x[2]!='COMPLETED']
    assignmentsViewCompletedList=[x for x in assignmentsViewList if x[2]=='COMPLETED']
    unassignedTeamsCount=len([x for x in teamsViewList if x[2]=='UNASSIGNED'])
    assignedTeamsCount=len(teamsViewList)-unassignedTeamsCount
    unassignedAssignmentsCount=len([x for x in assignments if x['AssignmentStatus']=='UNASSIGNED'])
    completedAssignmentsCount=len([x for x in assignments if x['AssignmentStatus']=='COMPLETED'])
    assignedAssignmentsCount=len(assignments)-unassignedAssignmentsCount-completedAssignmentsCount
    d={
        "teamsView":teamsViewList,
        "assignmentsViewNotCompleted":assignmentsViewNotCompletedList,
        "assignmentsViewCompleted":assignmentsViewCompletedList,
        "assignedTeamsCount":assignedTeamsCount,
        "unassignedTeamsCount":unassignedTeamsCount,
        "assignedAssignmentsCount":assignedAssignmentsCount,
        "unassignedAssignmentsCount":unassignedAssignmentsCount,
        "completedAssignmentsCount":completedAssignmentsCount}
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
    # note that this is really a list of pairings (one pairing per row)
    # print('******************** tdbGetAssignmentsView called')
    assignmentsList=[]
    previousAssignments=[]
    tdbAssignments=tdbGetAssignments()
    tdbPairings=tdbGetPairings()
    for entry in tdbAssignments:
        aid=entry['aid']
        assignmentName=entry['AssignmentName']
        assignmentStatus=entry['AssignmentStatus']
        previous=[]
        current=[]
        pairings=[x for x in tdbPairings if x['aid']==aid] # pairings that include this assignment
        if pairings:
            for pairing in pairings:
                if pairing['PairingStatus']=='PREVIOUS':
                    previous.append(tdbGetTeamNameByID(pairing['tid']))
                else:
                    current.append(tdbGetTeamNameByID(pairing['tid']))
        else:
            assignmentsList.append([assignmentName,'--',assignmentStatus,tdbGetAssignmentIntendedResourceByName(assignmentName)])
        for teamName in current:
            assignmentsList.append([assignmentName,teamName,tdbGetTeamStatusByName(teamName),tdbGetTeamResourceByName(teamName)])
        for teamName in previous:
            previousAssignments.append([assignmentName,teamName,'COMPLETED',tdbGetTeamResourceByName(teamName)])
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

def tdbGetPairingIDByNames(assignmentName,teamName):
    aid=tdbGetAssignmentIDByName(assignmentName)
    tid=tdbGetTeamIDByName(teamName)
    condition='aid='+str(aid)+' AND tid='+str(tid)
    query="SELECT pid FROM 'Pairings' WHERE {condition};".format(condition=condition)
    return q(query)[0].get('pid',None)

def tdbSetPairingStatusByID(pid,status):
    # what history entries if any should happen here?
    q("UPDATE 'Pairings' SET PairingStatus = '"+str(status)+"' WHERE pid = '"+str(pid)+"';")
    r=q("SELECT * FROM 'Pairings' WHERE pid = "+str(pid)+";")
    if r:
        tdbUpdateLastEditEpoch(pid=pid)
        validate=r[0]
        tdbPushTables()
        return {'validate':validate}
    else:
        return {'error':'Query did not return a value'}
    
def tdbSetTeamStatusByID(tid,status,push=True):
    tdbAddHistoryEntry('Status changed to '+status,tid=tid,recordedBy='SYSTEM')
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
    tdbAddHistoryEntry('Status changed to '+status,aid=aid,recordedBy='SYSTEM')
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

def tdbUpdateLastEditEpoch(tid=None,aid=None,pid=None):
    if not tid and not aid and not pid:
        print("tdbUpdateLastEditEpoch called with no arguments; nothing to do")
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

def tdbAddHistoryEntry(entry,aid=-1,tid=-1,recordedBy='N/A'):
    qInsert('History',{
        'aid':aid,
        'tid':tid,
        'Entry':entry,
        'RecordedBy':recordedBy,
        'Epoch':round(time.time())})

def tdbGetPairingIDsByID(pid=None):
    r=tdbGetPairings(pid)
    return True

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
            [tid,aid]=tdbGetPairingIDsByID(pid)
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

# tdbProcessSync - called from client sync success handler
def tdbProcessSync(result):
    requiredKeys=['Teams','Assignments','Pairings','History']
    if not all(key in result.keys() for key in requiredKeys):
        print("ERROR: sync result does not contain all required keys:"+str(requiredKeys))
        return None
    # if the new/updated host entry already exists local entry,
    #  update the values of the local entry (e.g. status, resource, timestamp);
    # otherwise, add it as a new local entry (a different client created it)
    for e in result['Teams']:
        # fields to update: TeamStatus, Resource, LastEditEpoch
        #  (TeamName can never be changed)
        setString="TeamStatus='"+str(e['TeamStatus'])+"'"
        setString+=", Resource='"+str(e['Resource'])+"'"
        setString+=', LastEditEpoch='+str(e['LastEditEpoch'])
        query='UPDATE Teams SET '+setString+' WHERE tid='+str(e['tid'])+';'
        # print('Teams sync query:'+query)
        r=q(query) # return value is number of rows affected
        if r==0:
            tdbNewTeam(
                    e['TeamName'],
                    e['Resource'],
                    status=e['TeamStatus'],
                    tid=e['tid'],
                    lastEditEpoch=e['LastEditEpoch'])
    for e in result['Assignments']:
        # fields to update: AssignmentStatus, IntendedResource, LastEditEpoch
        #  (AssignmentName can never be changed)
        setString="AssignmentStatus='"+str(e['AssignmentStatus'])+"'"
        setString+=", IntendedResource='"+str(e['IntendedResource'])+"'"
        setString+=', LastEditEpoch='+str(e['LastEditEpoch'])
        query='UPDATE Assignments SET '+setString+' WHERE aid='+str(e['aid'])+';'
        # print('Assignment sync query:'+query)
        r=q(query) # return value is number of rows affected
        if r==0:
            tdbNewAssignment(
                    e['AssignmentName'],
                    e['IntendedResource'],
                    status=e['AssignmentStatus'],
                    aid=e['aid'],
                    lastEditEpoch=e['LastEditEpoch'])
    for e in result['Pairings']:
        # fields to update: PairingStatus, LastEditEpoch
        #  (tid, aid can never be changed)
        pass
    for e in result['History']:
        pass
