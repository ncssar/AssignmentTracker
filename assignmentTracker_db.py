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
from websocket import create_connection # not websockets; websocket (singular) allows simple synchronous send

# use one table for teams, one table for assignments, and reduce duplication of data;
#  store the pairing data in a separete table

TEAM_COLS=[
    # TeamID is hardcoded as the primary key
    ["TeamName","TEXT"],
    ["TeamStatus","TEXT DEFAULT 'UNASSIGNED'"],
    ["Resource","TEXT DEFAULT 'Ground Type 2'"]]

ASSIGNMENT_COLS=[
    # AssignmentID is hardcoded as the primary key
    ["AssignmentName","TEXT"],
    ["AssignmentStatus","TEXT DEFAULT 'UNASSIGNED'"], # either UNASSIGNED or ASSIGNED
    ["IntendedResource","TEXT DEFAULT 'Ground Type 2'"]]

PAIRING_COLS=[
    ["TeamID","INTEGER"],
    ["AssignmentID","INTEGER"],
    ["PairingStatus","TEXT DEFAULT 'CURRENT'"]] # CURRENT or PREVIOUS

# History table: all activities are recorded in one table; each entry
#   has columns for AsignmentID, TeamID, Entry, RecordedBy, Epoch;
#   viewing the history can then be filtered by assignment, by team, 
#   or by pairing (assignment/team combination)

HISTORY_COLS=[
    ["AssignmentID","INTEGER"],
    ["TeamID","INTEGER"],
    ["Entry","TEXT"],
    ["RecordedBy","TEXT"],
    ["Epoch","INTEGER"]]

TEAM_STATUSES=["UNASSIGNED","ASSIGNED","WORKING","ENROUTE TO IC","DEBRIEFING"]

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
    print("q called: "+query)
    conn = sqlite3.connect('tracker.db')
    conn.row_factory = dict_factory # so that return value is a dict instead of tuples
    cur = conn.cursor()
    # fetchall if params is blank seems to only return a tuple, not a dict
    
    if params is not None:
        r=cur.execute(query,params).fetchall()
    else:
        r=cur.execute(query).fetchall()
    conn.commit()
    print("  result:" +str(r))
    return r

def wsSend(uri,msg):
    ws=create_connection(uri)
    ws.send(json.dumps({"msg":msg}))
    ws.close()

def createTeamsTableIfNeeded():
    colString="'TeamID' INTEGER PRIMARY KEY AUTOINCREMENT,"
    colString+=', '.join([str(x[0])+" "+str(x[1]) for x in TEAM_COLS])
    query='CREATE TABLE IF NOT EXISTS "Teams" ('+colString+');'
    return q(query)

def createAssignmentsTableIfNeeded():
    colString="'AssignmentID' INTEGER PRIMARY KEY AUTOINCREMENT,"
    colString+=', '.join([str(x[0])+" "+str(x[1]) for x in ASSIGNMENT_COLS])
    query='CREATE TABLE IF NOT EXISTS "Assignments" ('+colString+');'
    return q(query)

def createPairingsTableIfNeeded():
    colString="'PairingID' INTEGER PRIMARY KEY AUTOINCREMENT,"
    colString+=', '.join([str(x[0])+" "+str(x[1]) for x in PAIRING_COLS])
    query='CREATE TABLE IF NOT EXISTS "Pairings" ('+colString+');'
    return q(query)

def createHistoryTableIfNeeded():
    colString="'HistoryID' INTEGER PRIMARY KEY AUTOINCREMENT,"
    colString+=', '.join([str(x[0])+" "+str(x[1]) for x in HISTORY_COLS])
    query='CREATE TABLE IF NOT EXISTS "History" ('+colString+');'
    return q(query)

def tdbInit():
    # start with a clean database every time the app is started
    #  (need to implement auto-recover)
    if os.path.exists('tracker.db'):
        os.remove('tracker.db')
    createTeamsTableIfNeeded()
    createAssignmentsTableIfNeeded()
    createPairingsTableIfNeeded()
    createHistoryTableIfNeeded()

# intercept any None values and change them to NULL
# def noneToQuestion(x):
#     if x is None:
#         return 'NULL'
#     else:
#         return x
    
# def qInsert(tableName,d):
#     print("qInsert called: tableName="+str(tableName)+"  d="+str(d))
#     colList="({columns})".format(
#                 columns=', '.join(d.keys()))
# #     values=list(map(noneToNull,d.values()))
#     values=list(d.values())
#     print("  mapped values="+str(values))
#     valList="{values}".format(
#                 values=tuple(values))
#     
#     query="INSERT INTO '{tablename}' {colList} VALUES {valList};".format(
#         tablename=tableName,
#         colList=colList,
#         valList=valList)
#     return q(query)

# insert using db parameters to avoid SQL injection attack and to correctly handle None
def qInsert(tableName,d):
    print("qInsert called: tableName="+str(tableName)+"  d="+str(d))
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

def tdbNewTeam(name,resource):
    # createTeamsTableIfNeeded()
    qInsert('Teams',{'TeamName':name,'Resource':resource})
    # # create the team's history table
    # tableName=d["TeamName"]+"History"
    # colString="'TeamID' INTEGER PRIMARY KEY AUTOINCREMENT"
    # colString+=', '.join([str(x[0])+" "+str(x[1]) for x in TEAM_HISTORY_COLS])
    # query='CREATE TABLE IF NOT EXISTS "'+tableName+'" ('+colString+');'
    # q(query)
    # tdbAddTeamHistoryEntry({
    #         'TeamName':teamName,
    #         'Event':"Team Created",
    #         'Epoch':time.time(),
    #         'RecordedBy':'system'})
    # validate
    r=q('SELECT * FROM Teams ORDER BY TeamID DESC LIMIT 1;')
    tdbAddHistoryEntry("Team "+name+" Created",teamID=r[0]["TeamID"],recordedBy='SYSTEM')
    validate=r[0]
    # wsSend(json.dumps(validate))
    return {'validate':validate}

def tdbNewAssignment(name,intendedResource):
    # createAssignmentsTableIfNeeded()
    qInsert('Assignments',{'AssignmentName':name,'IntendedResource':intendedResource})
    r=q('SELECT * FROM Assignments ORDER BY AssignmentID DESC LIMIT 1;')
    tdbAddHistoryEntry("Assignment "+name+" Created",assignmentID=r[0]["AssignmentID"],recordedBy='SYSTEM')
    validate=r[0]
    return {'validate':validate}

# tdbHome - return a welcome message to verify that this code is running
def tdbHome():
    return '''<h1>AssignmentTracker Database API</h1>
            <p>API for interacting with the Assignment Tracker databases</p>'''


# team getters
def tdbGetTeamIDByName(teamName):
    query="SELECT TeamID FROM Teams WHERE TeamName='"+str(teamName)+"';"
    return q(query)[0].get("TeamID",None)

def tdbGetTeamNameByID(teamID):
    query="SELECT TeamName FROM Teams WHERE TeamID='"+str(teamID)+"';"
    return q(query)[0].get("TeamName",None)

def tdbGetTeamStatusByName(teamName):
    query="SELECT TeamStatus FROM Teams WHERE TeamName='"+str(teamName)+"';"
    return q(query)[0].get("TeamStatus",None)

def tdbGetTeamResourceByName(teamName):
    query="SELECT Resource FROM Teams WHERE TeamName='"+str(teamName)+"';"
    return q(query)[0].get("Resource",None)


# assignment getters
def tdbGetAssignmentNameByID(assignmentID):
    query="SELECT AssignmentName FROM Assignments WHERE AssignmentID='"+str(assignmentID)+"';"
    return q(query)[0].get("AssignmentName",None)

def tdbGetAssignmentIDByName(assignmentName):
    query="SELECT AssignmentID FROM Assignments WHERE AssignmentName='"+str(assignmentName)+"';"
    return q(query)[0].get("AssignmentID",None)

def tdbGetAssignmentStatusByName(assignmentName):
    query="SELECT AssignmentStatus FROM Assignments WHERE AssignmentName='"+str(assignmentName)+"';"
    return q(query)[0].get("AssignmentStatus",None)

def tdbGetAssignmentIntendedResourceByName(assignmentName):
    query="SELECT IntendedResource FROM Assignments WHERE AssignmentName='"+str(assignmentName)+"';"
    return q(query)[0].get("IntendedResource",None)


def tdbGetTeams(teamID=None):
    # createTeamsTableIfNeeded()
    if teamID:
        condition='TeamID='+str(teamID)
    else:
        condition='1'
    return q("SELECT * FROM 'Teams' WHERE {condition};".format(
            condition=condition))

# tdbGetTeamsView - return a list of rows, which can be used directly by kivy
#    to create the teams view RecycleView data, or, to generate the html table
#    for downstream html views i.e. pushed using websockets
def tdbGetTeamsView():
    print('****************** tdbGetTeamsView called')
    teamsList=[]
    tdbTeams=tdbGetTeams()
    tdbPairings=tdbGetPairings()
    for entry in tdbTeams:
        id=entry['TeamID']
        pairings=[x for x in tdbPairings if x['TeamID']==id] # pairings that include this team
        currentPairings=[x for x in pairings if x['PairingStatus']=='CURRENT']
        previousPairings=[x for x in pairings if x['PairingStatus']=='PREVIOUS']
        currentAssignments=[tdbGetAssignmentNameByID(x["AssignmentID"]) for x in currentPairings]
        previousAssignments=[tdbGetAssignmentNameByID(x["AssignmentID"]) for x in previousPairings]
        # Logger.info('Assignments for '+str(entry['TeamName'])+':'+str(assignments))
        teamsList.append([
            entry['TeamName'],
            ','.join(currentAssignments) or '--',
            entry['TeamStatus'],
            entry['Resource'],
            ','.join(previousAssignments) or '--'])
    print('teamsList at end of tdbGetTeamsView:'+str(teamsList))
    return teamsList

def tdbPushTables(uri,teamsViewList=None,assignmentsViewList=None,teamsCountText="---",assignmentsCountText="---"):
    # uri = "ws://localhost:8765"
    if not teamsViewList:
        teamsViewList=tdbGetTeamsView()
    if not assignmentsViewList:
        assignmentsViewList=tdbGetAssignmentsView()
    if uri=='pusher':
        pusher_client.trigger('my-channel','teamsViewUpdate',teamsViewList)
        pusher_client.trigger('my-channel','assignmentsViewUpdate',teamsViewList)
    else:
        wsSend(uri,json.dumps({
                "teamsView":teamsViewList,
                "assignmentsView":assignmentsViewList,
                "teamsCount":teamsCountText,
                "assignmentsCount":assignmentsCountText}))

    # def pushTeamsTable(self):
    #     # no-module table writer based on https://stackoverflow.com/a/49889528
    #     cols=["Team","Status","Resource","Current","Previous"]
    #     d=self.teamsList
    #     table='<table>\n<tr>{}</tr>'.format('\n'.join('<th>{}</th>'.format(i) for i in cols))
    #     table+='\n'.join(['<tr>{}</tr>'.format('\n'.join(['<td>{}</td>'.format(b) for b in i])) for i in d])
    #     table+='\n</table>'
    #     self.pusher_client.trigger('my-channel', 'teamsViewUpdate', table)

def tdbGetAssignments(assignmentID=None):
    # createAssignmentsTableIfNeeded()
    if assignmentID:
        condition='AssignmentID='+str(assignmentID)
    else:
        condition='1'
    return q("SELECT * FROM 'Assignments' WHERE {condition};".format(
            condition=condition))

def tdbGetAssignmentsView():
    # note that this is really a list of pairings (one pairing per row)
    print('******************** tdbGetAssignmentsView called')
    assignmentsList=[]
    previousAssignments=[]
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
                if pairing['PairingStatus']=='PREVIOUS':
                    previous.append(tdbGetTeamNameByID(pairing["TeamID"]))
                else:
                    current.append(tdbGetTeamNameByID(pairing["TeamID"]))
        else:
            assignmentsList.append([assignmentName,'--',assignmentStatus,tdbGetAssignmentIntendedResourceByName(assignmentName)])
        for teamName in current:
            assignmentsList.append([assignmentName,teamName,tdbGetTeamStatusByName(teamName),tdbGetTeamResourceByName(teamName)])
        for teamName in previous:
            previousAssignments.append([assignmentName,teamName,'COMPLETED',tdbGetTeamResourceByName(teamName)])
    assignmentsList+=previousAssignments # list completed assignments at the end, until a separate list display is arranged
    return assignmentsList
    
def tdbGetPairings(pairingID=None):
    if pairingID:
        condition='PairingID='+str(pairingID)
    else:
        condition='1'
    return q("SELECT * FROM 'Pairings' WHERE {condition};".format(
            condition=condition))

def tdbGetPairingsByAssignment(assignmentID,currentOnly=False):
    condition='AssignmentID='+str(assignmentID)
    if currentOnly:
        condition+=" AND PairingStatus='CURRENT'"
    return q("SELECT * FROM 'Pairings' WHERE {condition};".format(condition=condition))

def tdbGetPairingIDByNames(assignmentName,teamName):
    assignmentID=tdbGetAssignmentIDByName(assignmentName)
    teamID=tdbGetTeamIDByName(teamName)
    condition='AssignmentID='+str(assignmentID)+' AND TeamID='+str(teamID)
    query="SELECT PairingID FROM 'Pairings' WHERE {condition};".format(condition=condition)
    return q(query)[0].get('PairingID',None)

def tdbSetPairingStatusByID(pairingID,status):
    # what history entries if any should happen here?
    q("UPDATE 'Pairings' SET PairingStatus = '"+str(status)+"' WHERE PairingID = '"+str(pairingID)+"';")
    r=q("SELECT * FROM 'Pairings' WHERE PairingID = "+str(pairingID)+";")
    if r:
        validate=r[0]
        return {'validate':validate}
    else:
        return {'error':'Query did not return a value'}
    
def tdbSetTeamStatusByID(teamID,status):
    tdbAddHistoryEntry('Status changed to '+status,teamID=teamID,recordedBy='SYSTEM')
    q("UPDATE 'Teams' SET TeamStatus = '"+str(status)+"' WHERE TeamID = '"+str(teamID)+"';")
    r=q("SELECT * FROM 'Teams' WHERE TeamID = "+str(teamID)+";")
    if r:
        validate=r[0]
        return {'validate':validate}
    else:
        return {'error':'Query did not return a value'}

def tdbSetTeamStatusByName(teamName,status):
    tdbAddHistoryEntry('Status changed to '+status,teamID=tdbGetTeamIDByName(teamName),recordedBy='SYSTEM')
    query="UPDATE 'Teams' SET TeamStatus = '"+str(status)+"' WHERE TeamName = '"+str(teamName)+"';"
    return q(query)

def tdbSetAssignmentStatusByID(assignmentID,status):
    tdbAddHistoryEntry('Status changed to '+status,assignmentID=assignmentID,recordedBy='SYSTEM')
    q("UPDATE 'Assignments' SET AssignmentStatus = '"+str(status)+"' WHERE AssignmentID = '"+str(assignmentID)+"';")
    r=q("SELECT * FROM 'Assignments' WHERE AssignmentID = "+str(assignmentID)+";")
    if r:
        validate=r[0]
        return {'validate':validate}
    else:
        return {'error':'Query did not return a value'}

def tdbSetAssignmentStatusByName(assignmentName,status):
    query="UPDATE 'Assignments' SET AssignmentStatus = '"+str(status)+"' WHERE AssignmentName = '"+str(assignmentName)+"';"
    return q(query)

def tdbPair(assignmentID,teamID):
    # query="UPDATE 'Teams' SET CurrentAssignments = "+str(assignmentID)+" WHERE TeamID="+str(teamID)+";"
    # query="UPDATE 'Pairings' SET TeamID = "+str(teamID)+" WHERE AssignmentID = "+str(assignmentID)+";"
    # query="INSERT INTO 'Pairings' (AssignmentID,TeamID) VALUES("+str(assignmentID)+","+str(teamID)+");"
    # return q(query)
    assignmentName=tdbGetAssignmentNameByID(assignmentID)
    teamName=tdbGetTeamNameByID(teamID)
    tdbAddHistoryEntry("Pairing Created: Assignment "+assignmentName+" <=> Team "+teamName,assignmentID=assignmentID,teamID=teamID,recordedBy='SYSTEM')
    qInsert('Pairings',{'AssignmentID':assignmentID,'TeamID':teamID})
    r=q('SELECT * FROM Pairings ORDER BY PairingID DESC LIMIT 1;')
    validate=r[0]
    return {'validate':validate}

def tdbUpdateTeamLastEditEpoch(teamID):
    query="UPDATE 'Teams' SET LastEditEpoch = "+str(round(time.time(),2))+" WHERE TeamID="+str(teamID)+";"
    return q(query)

def tdbAddHistoryEntry(entry,assignmentID=-1,teamID=-1,recordedBy='N/A'):
    qInsert('History',{
        "AssignmentID":assignmentID,
        "TeamID":teamID,
        "Entry":entry,
        "RecordedBy":recordedBy,
        "Epoch":round(time.time())})

def tdbGetHistory(assignmentID=None,teamID=None,useAnd=None):
    if not assignmentID and not teamID:
        return([])
    op='OR' # by default, return history entries that involve either the team or the assignment
    if useAnd:
        op='AND' # optionally return history entries that only affect the status of both team and assignment
    if assignmentID:
        conditionA='AssignmentID='+str(assignmentID)
    if teamID:
        conditionT='TeamID='+str(teamID)
    if assignmentID and teamID:
        condition=conditionA+' '+op+' '+conditionT
    elif assignmentID:
        condition=conditionA
    else:
        condition=conditionT
    query="SELECT * FROM 'History' WHERE {condition};".format(
            condition=condition)
    return q(query)

# it's cleaner to let the host decide whether to add or to update;
# if ID, Agency, Name, and InEpoch match those of an existing record,
#  then update that record; otherwise, add a new record;
# PUT seems like a better fit than POST based on the HTTP docs
#  note: only store inEpoch to the nearest hundredth of a second since
#  comparison beyond 5-digits-right-of-decimal has shown truncation differences

# def sdbAddOrUpdate(eventID,d):
# #     app.logger.info("put1")
# #     app.logger.info("put called for event "+str(eventID))
# #     if not request.json:
# #         app.logger.info("no json")
# #         return "<h1>400</h1><p>Request has no json payload.</p>", 400
# #     if type(request.json) is str:
# #         d=json.loads(request.json)
# #     else: #kivy UrlRequest sends the dictionary itself
# #         d=request.json

# #     d['InEpoch']=round(d['InEpoch'],2)
# #     d['OutEpocj']=round(d['OutEpoch'],2)

#     # query builder from a dictionary that allows for different data types
#     #  https://stackoverflow.com/a/54611514/3577105
# #     colVal="({columns}) VALUES {values}".format(
# #                 columns=', '.join(d.keys()),
# #                 values=tuple(d.values())
# #             )
# #     colList="({columns})".format(
# #                 columns=', '.join(d.keys()))
# #     valList="{values}".format(
# #                 values=tuple(d.values()))
#     # 1. find any record(s) that should be modified
#     tablename=str(eventID)+"_SignIn"
#     condition="ID = '{id}' AND Name = '{name}' AND Agency = '{agency}' AND InEpoch = '{inEpoch}'".format(
#             id=d['ID'],name=d['Name'],agency=d['Agency'],inEpoch=d['InEpoch'])
#     query="SELECT * FROM '{tablename}' WHERE {condition};".format(
#             tablename=tablename,condition=condition)
# #     app.logger.info('query:'+query)
#     r=q(query)
# #     app.logger.info("result:"+str(r))
#     if len(r)==0: # no results: this is a new sign-in; add a new record
#         # query builder from a dictionary that allows for different data types
#         #  https://stackoverflow.com/a/54611514/3577105
# #         query="INSERT INTO {tablename} ({columns}) VALUES {values};" .format(
# #                 tablename='SignIn',
# #                 columns=', '.join(d.keys()),
# #                 values=tuple(d.values())
# #             )
# #         query="INSERT INTO {tablename} {colList} VALUES {valList};".format(
# #                 tablename='SignIn',
# #                 colList=colList,
# #                 valList=valList)
# #         app.logger.info("query string: "+query)
# #         q(query)
#         qInsert(tablename,d)
#         sdbUpdateLastEditEpoch(eventID)
#     elif len(r)==1: # one result found; this is a sign-out, status udpate, etc; modify existing record
#         # UPDATE .. SET () = () syntax is only supported for sqlite3 3.15.0 and up;
#         #  pythonanywhere only has 3.11.0, so, use simpler queries instead
# #       query="UPDATE {tablename} SET {colList} = {valList} WHERE {condition};".format(
# #               tablename='SignIn',
# #               colList=colList,
# #               valList=valList,
# #               condition=condition)
#         query="UPDATE '{tablename}' SET ".format(tablename=tablename)
#         for key in d.keys():
#             query+="{col} = '{val}', ".format(
#                 col=key,
#                 val=d[key])
#         query=query[:-2] # get rid of the final comma and space
#         query+=" WHERE {condition};".format(condition=condition)
# #         app.logger.info("query string: "+query)
#         q(query)
#         sdbUpdateLastEditEpoch(eventID)
#     else:
#         return {'error': 'more than one record in the host database matched the ID,Name,Agency,InEpoch values from the sign-in action'}, 405

#     # now get the same record(s) from the local (host) db so the downstream tool can validate
#     #  note that it should only return one record; the downstream tool should check
#     validate=q("SELECT * FROM '{tablename}' WHERE {condition};".format(
#             tablename=tablename,
#             condition=condition))

#     # in url request context, we want to return a full flask jsonify object and a response code
#     #  but since we are not using flask here, just return a dictionary and a response code,
#     #  and any downstream tool that needs to send json will have to jsonify the dictionary
# #     return jsonify({'query': query,'validate': validate}), 200
#     return {'query': query,'validate': validate}
