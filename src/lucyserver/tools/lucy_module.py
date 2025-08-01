import inspect
import os
import json

def available_for_lucy(func):
    func._available_for_lucy = True
    return func

class LucyModule:
    def __init__(self, name):
        self.name = name
        self.testing_mode = False

        self.session = None

    def setup(self):
        """
        This method is called when the module is first loaded.
        Subclasses can override this method to perform any setup tasks.
        """
        pass

    def get_web_preview(self, path=None):
        raise NotImplementedError("This method should be implemented in subclasses.")
    
    async def wake_word_identified(self):
        """
        This method is called when the wake word is identified.
        Subclasses can override this method to handle wake word events.
        """
        pass
    
    async def undo_wake_word_identified(self):
        """
        This method is called when the request is being processed and the user has finished speaking.
        """
        pass

    async def handle_message(self, message):
        """
        This method is called when a tool message is received.
        Subclasses can override this method to handle tool messages.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")
    
    def save_data(self, key, value):
        base_dir = os.path.expanduser("~/lucyserver/cfg")
        user_tool_dir = os.path.join(base_dir, self.user_id, self.name)
        os.makedirs(user_tool_dir, exist_ok=True)
        
        file_path = os.path.join(user_tool_dir, f"{key}.json")
        with open(file_path, "w") as f:
            f.write(json.dumps(value, indent=4))

    def load_data(self, key, default):
        if self.name is None or self.user_id is None:
            return default
        
        try:
            base_dir = os.path.expanduser("~/lucyserver/cfg")
            file_path = os.path.join(base_dir, self.user_id, self.name, f"{key}.json")
            with open(file_path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            self.save_data(key, default)
            return default


    def get_callable_functions(self):
        functions = {}
        functions['module'] = self
        for name, func in inspect.getmembers(self.__class__, predicate=inspect.isfunction):
            functions[name] = func
        return functions

    def build_documentation(self):
        functions = []
        for name, func in inspect.getmembers(self.__class__, predicate=inspect.isfunction):
            if getattr(func, '_available_for_lucy', False):
                functions.append(self.build_documentation_for_func(func))
        return {"functions": functions}
    
    def build_documentation_for_func(self, func):
        sig = inspect.signature(func)
        arg_names = [str(param) for param in sig.parameters.values()]
        arg_names.remove('self')
        doc = inspect.getdoc(func) or ""
        return {
            "module": self.name,
            "function": func.__name__,
            "args": arg_names,
            "description": doc,
        }
    
    async def send_socket_message(self, json_data):
        wrapper = {
            "type": "tool_message",
            "tool": self.name,
            "data": json_data
        }
        await self.websocket.send_json(wrapper)

    def set_websocket(self, websocket):
        self.websocket = websocket

    def set_user_id(self, user_id):
        self.user_id = user_id

    def set_session(self, session):
        self.session = session

    def set_testing_mode(self, testing_mode):
        self.testing_mode = testing_mode

    def set_ai_client(self, ai_client):
        self.ai_client = ai_client