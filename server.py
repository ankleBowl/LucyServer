from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pydantic import BaseModel
from main import LucySession
from message import Message
import asyncio
from importlib import resources

class UserMessageRequest(BaseModel):
    user_id: str
    message: str

class UserRequest(BaseModel):
    user_id: str

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sessions = {}

@app.get("/v1/{user_id}/module/{module_name}/{path:path}")
async def get_module(user_id: str, module_name: str, path: str, request: Request):
    if user_id not in sessions:
        return HTMLResponse("<h1>Session not found</h1>", status_code=404)
    session = sessions[user_id]
    if module_name not in session.internal.get_tool_registry():
        return HTMLResponse("<h1>Module not loaded</h1>", status_code=404)
    web_preview = session.internal.get_tool_registry()[module_name]["module"].get_web_preview(path, args=dict(request.query_params))
    if web_preview["type"] == "html":
        return HTMLResponse(web_preview["content"])
    elif web_preview["type"] == "redirect":
        return RedirectResponse(web_preview["content"])

@app.get('/v1/module/{module_name}/{path:path}')
async def get_global_module(module_name: str, path: str, request: Request):
    response = LucySession.get_static_web_preview(module_name, path, args=dict(request.query_params))
    if response["type"] == "html":
        return HTMLResponse(response["content"])
    elif response["type"] == "redirect":
        return RedirectResponse(response["content"])

import numpy as np

@app.post("/v1/{user_id}/transcribe")
async def process_audio(request: Request, user_id: str):
    if user_id not in sessions:
        return {"error": "Session not found"}, 404
    audio_data = await request.body()
    audio_data = np.frombuffer(audio_data, dtype=np.int16)

    session = sessions[user_id]
    response = session.transcribe(audio_data)
    
    return {
        "transcription": response[0],
        "classification": response[1]
    }


@app.websocket("/v1/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str = None):
    try:
        await websocket.accept()
        while True:
            data = await websocket.receive_json()

            print(f"Received data: {data}")

            if data["type"] == "auth":
                if user_id in sessions:
                    del sessions[user_id]
                sessions[user_id] = LucySession(user_id=user_id, websocket=websocket)
                await websocket.send_json({"status": "authenticated"})

            if user_id not in sessions:
                continue

            session = sessions[user_id]

            if data["type"] == "wake_word_detected":
                await session.internal.wake_word_identified()

            if data["type"] == "request":
                user_input = data["message"]
                if not user_input:
                    continue
                starting_messages = [Message("user", user_input)]
                asyncio.create_task(session.run(starting_messages))
            elif data["type"] == "tool_client_message":
                args = {
                   "message": data["data"] 
                }
                await session.handle_tool_message(data["tool"], "handle_message", args)
            elif data["type"] == "clear":
                if user_id in sessions:
                    sessions[user_id].dump_to_file()
                    del sessions[user_id]
                await websocket.send_json({"status": "session cleared"})
    except WebSocketDisconnect:
        print(f"WebSocket disconnected for user {user_id}")
        if user_id in sessions:
            sessions[user_id].dump_to_file()
            del sessions[user_id]


@app.get("/", response_class=HTMLResponse)
def get_home_page(request: Request):
    pass

@app.get("/chat", response_class=HTMLResponse)
def get_chat_page(request: Request):
    path = resources.files("lucyserver").joinpath("chat.html")
    return HTMLResponse(path.read_text())

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0",  port=8000, reload=True)
