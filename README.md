# AssignmentTracker
shared tool for SAR team and assignment tracking

Various command staff and general staff functions would benefit from having a shared up-to-date view of teams and assignments.  Having this view could also reduce the workload of walking papers around from one station to the other - which becomes a bigger issue as the search scales up and command post gets larger, i.e. multiple rooms in a large building.

Problems that this project hopes to address:
- confusion at various stations, which can affect team safety and generaly impact the overall search flow, due to stale views of team and assignment status
- lack of advance notice to resource unit that teams are returning, due to missed communication between radio station and situation unit (assuming the team did actually radio when they were enroute to CP)

This project could be folded in to, and/or tightly integrated with, the T-card project, but initially it's probably easier to keep it separate.

Ideas for this project:
- allow for a dedicated device (tablet or laptop) per 'station' at the command post - whether a fixed location (resource unit, situation unit, big screen display at CP) or roaming (search manager, ops chief, etc - who often try to keep track of this info on a clipboard that they walk around with)
- provide for a team view (rows are teams) and an assignment view (rows are assignments)
- quick visual at-a-glance indications of:
  - team status / location within the resource workflow (this includes how the team would be placed in the t-card sleeve, and also what their radiolog status is - working, waiting for transport, enroute to CP, at CP, etc)
  - current assignment(s) per team (i.e. 'team view')
  - current team(s) per assignment (i.e. 'assignment view')
  - visual and/or audio alerts when actions need to be taken, i.e. resource unit needs to prepare debrief packet when a team's status changes to 'enroute to CP'
  - visual acknowledgements, i.e. all other stations should see that resource unit acknowledged the alert that a team is enroute to CP
- 'chain-of-custody' accountability: when changes are made, keep track of who / which device changed them and at what time
- integrate with T-card, signin, and other projects if/when/as needed
- host and share the data in the same manner as those other projects - online when possible using a hosted database e.g. pythonanywhere; intranet or locally also
** consider security of shared data - this data could be used to track the progress of a search, which is generally sensitive and non-public

See examples on google docs: https://docs.google.com/spreadsheets/d/1OT0F97mIuSGyYnWuem34H2Ldpt0NmdrkRepA87KEhBo/edit?usp=sharing

## Multiple clients
- This app supports and syncs the following clients simultaneously:
  - one or more Kivy clients (Windows or Android)
  - any number of web browsers (any platform; nothing to install)
- Kivy clients are read/write (can write to the centralized database)
- web browsers are read-only
- different Kivy nodes (assigned to different ICS positions/personnel) will have different authority to enter data at different stages

## Database and Data Flow
- data is sent from Kivy client(s) to the centralized sqlite3 database using HTTP API
- database location could be one (or more?) of:
  - online / internet (pythonanywhere.com)
  - intranet (trailer server)
  - localhost (Windows or (eventually) Android)
- on each database change, the server pushes over websockets to all listeners:
  - entire teams view list
  - entire assignments view list
  - new history entries
- web browser clients are responsible for creating html tables in javascript, using the pushed data
- deeper data (history, etc) must be requested by the client using HTTP API
