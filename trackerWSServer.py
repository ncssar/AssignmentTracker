# modified from https://websockets.readthedocs.io/en/stable/intro.html#synchronization-example

import asyncio
import websockets

USERS = set()

async def register(websocket):
    print("register: "+str(websocket))
    USERS.add(websocket)

async def unregister(websocket):
    print("unregister: "+str(websocket))
    USERS.remove(websocket)

# each new connection calls trackerHandler, resulting in a new USERS entry
async def trackerHandler(websocket, path):
    await register(websocket)
    try:
        async for message in websocket:
            await asyncio.wait([user.send(message) for user in USERS])
    finally:
        await unregister(websocket)

start_server = websockets.serve(trackerHandler, "localhost", 8765)

asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
