from openai import OpenAI
from bs4 import BeautifulSoup
from io import BytesIO
from scipy.io import wavfile
import numpy as np

from datetime import datetime

import uuid
import json
import os
import asyncio

from importlib import resources
SYSTEM_PROMPT = resources.read_text("lucyserver", "prompt.md")


from .tools.linternal import LInternal
linternal = LInternal(None, None, None)
docs = linternal.build_documentation()
SYSTEM_PROMPT = SYSTEM_PROMPT.replace("[[INTERNAL_DOCS]]", json.dumps(docs, indent=2))

def parse_llm_output(output):
    soup = BeautifulSoup(output, "html.parser")
    children = soup.find_all(recursive=False)
    parsed = []
    for child in children:
        parsed.append({
            "tag": child.name,
            "content": child.get_text(strip=True)
        })
    return parsed

def parse_tool_response(result):
    str_result = ""
    if isinstance(result, dict) or isinstance(result, list):
        str_result = json.dumps(result)
    elif result is None:
        pass
    else:
        str_result = str(result)
    return str_result

from .message import Message

class LucySession:
    def __init__(self, user_id, websocket):
        self.messages = [ Message("system", SYSTEM_PROMPT) ]

        self.lock = asyncio.Lock()

        self.websocket = websocket

        self.BASE_URL = "https://api.groq.com/openai/v1"
        self.MODEL_NAME = "moonshotai/kimi-k2-instruct"

        self.internal = LInternal(user_id, websocket, self)

        settings = self.internal.load_data("settings", {
            "groq_api_key": "",
        })

        self.API_KEY = settings["groq_api_key"]

        self.client = OpenAI(
            base_url=self.BASE_URL,
            api_key=self.API_KEY
        )

    def get_openai_client(self):
        return self.client

    def messages_to_openai(self, messages):
        return [message.to_openai() for message in messages]

    def get_static_web_preview(module_name, path, args={}):
        return LInternal.get_global_web_preview(module_name, path, args=args)

    def dump_to_file(self):
        base_dir = os.path.expanduser("~/lucyserver/session_cache")
        os.makedirs(base_dir, exist_ok=True)
        if len(self.messages) <= 1:
            return
        
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        random_attatchment = str(uuid.uuid4())[:4]
        filename = f"{current_time} [{random_attatchment}].json"
        with open(os.path.join(base_dir, filename), "w") as f:
            json_data = [message.to_json() for message in self.messages]
            json.dump(json_data, f, indent=2)

    async def handle_tool_message(self, module, function, args):
        # args = {message: INIT_SPOTIFY}
        if not self.internal.tool_is_imported(module):
            return Message("error", f"Module '{module}' not imported.")

        args["self"] = self.internal.get_tool_registry()[module]["module"]

        if function not in self.internal.get_tool_registry()[module]:
            return Message("error", f"Function '{function}' not found in module '{module}'.")
        
        try:
            result = await self.internal.get_tool_registry()[module][function](**args)
        except Exception as e:
            return Message("error", f"Module '{module}' function '{function}' raised an exception: {str(e)}")
        

        output = []
        x = 0
        if isinstance(result, list):
            for item in result[1:]:
                print("APPENDING EXTRA ITEM:", item)
                output.append(item)
            result = result[0]

        result = parse_tool_response(result)
        return Message("tool_response", result)
        
    def get_next_action(self):
        completion = self.client.chat.completions.create(
            model=self.MODEL_NAME,
            messages= self.messages_to_openai(self.messages),
        )
        raw_output = completion.choices[0].message.content
        output = parse_llm_output(raw_output)
        if len(output) == 0:
            if len(raw_output) < 5:
                return Message("end", "")
            return Message("assistant", raw_output)

        output = output[0]
        return Message(output["tag"], output["content"])

    async def run(self, starting_messages):
        async with self.lock:
            await self.internal.undo_wake_word_identified()

            starting_messages_mut = starting_messages.copy()

            while True:
                await asyncio.sleep(0.01)

                if len(starting_messages_mut) > 0:
                    message = starting_messages_mut.pop(0)
                else:
                    message = self.get_next_action()

                self.messages.append(message)
                self.print_conversation()

                tag = message.type_
                content = message.content

                if tag == "tool":
                    content = json.loads(content)

                    module = content["module"]
                    function = content["function"]

                    await self.websocket.send_json({
                        "type": "tool",
                        "data": {
                            "module": module,
                            "function": function,
                            "args": content["args"]
                        }
                    })

                    message = await self.handle_tool_message(module, function, content["args"])
                    self.messages.append(message)
                if tag == "end":
                    await self.websocket.send_json({
                        "type": "end"
                    })
                    break
                if tag == "assistant":
                    await self.websocket.send_json({
                        "type": "assistant",
                        "data": content
                    })
                if tag == "user":
                    continue
                    
    def transcribe(self, audio):
        wav_buffer = BytesIO()
        wav_buffer.name = "audio.wav"
        wavfile.write(wav_buffer, 16000, audio.astype(np.int16))
        wav_buffer.seek(0)

        transcription = self.client.audio.transcriptions.create(
            file=wav_buffer,
            model="whisper-large-v3-turbo",
            response_format="text",
            language="en",
            temperature=0.0
        )
        return transcription, "incomplete_query"

    def print_conversation(self):
        print("Conversation:")
        messages = [message.to_openai() for message in self.messages]
        for message in messages:
            print(message['role'])
            for line in message['content'].split("\n"):
                print(f"  {line}")
            print()
        print()

if __name__ == "__main__":
    session = LucySession("meewhee", None)
    print(asyncio.run(session.handle_tool_message("internal", "add_tool", {"name": "internet"})))