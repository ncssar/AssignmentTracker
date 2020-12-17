# modified from https://websockets.readthedocs.io/en/stable/intro.html#synchronization-example

import asyncio
import websockets
import os
from datetime import datetime

USERS = set()
host="localhost"
port=80
pid=os.getpid()

async def register(websocket):
    print("register: "+str(websocket))
    USERS.add(websocket)

async def unregister(websocket):
    print("unregister: "+str(websocket))
    USERS.remove(websocket)

async def repeat(message):
    for user in USERS:
        try:
            await user.send(message)
        except Exception as e:
            if str(e).startswith('code = 1000 (OK)'):
                pass
            else:
                print("exception during await send:"+str(e))
        
# each new connection calls trackerHandler, resulting in a new USERS entry
async def trackerHandler(websocket, path):
    await register(websocket)
    try:
        async for message in websocket:
            print(datetime.now().strftime("%H:%M:%S")+" : incoming message:")
            print(str(message))
            await repeat(message)
            print("message repeated to "+str(len(USERS))+" registered listener(s)")
    finally:
        await unregister(websocket)

start_server = websockets.serve(trackerHandler,host,port)

print("Websocket repeater started (pid="+str(pid)+"): ws://"+host+":"+str(port))

try:
    asyncio.get_event_loop().run_until_complete(start_server)
except:
    pass

asyncio.get_event_loop().run_forever()
