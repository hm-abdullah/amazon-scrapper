# Realtime WebSocket client connection manager and broadcasting.

import json
from typing import List, Dict, Any
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message_dict: Dict[str, Any]):
        try:
            message_json = json.dumps(message_dict)
        except Exception:
            return
            
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message_json)
            except Exception:
                disconnected.append(connection)
                
        for conn in disconnected:
            self.disconnect(conn)

manager = ConnectionManager()
