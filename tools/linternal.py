from tools.lucy_module import LucyModule, available_for_lucy

from tools.lspotify import LSpotify
from tools.ltime import LTime
from tools.lclock import LClock
from tools.lhome import LHome
from tools.linternet import LInternet
# from tools.lappletv import LAppleTV

class LInternal(LucyModule):

    tool_classes = {
        "spotify": LSpotify,
        "time": LTime,
        "home": LHome,
        "clock": LClock,
        "internet": LInternet,
    }
    
    
    def __init__(self, user_id, websocket, session):
        super().__init__("internal")
        print(f"Initializing internal tool for user {user_id}")

        self.websocket = websocket
        self.session = session
        self.user_id = user_id
        
        self.tool_registry = {}
        self.imported_tools = set()

        self.register_self()

        for tool_name in self.tool_classes:
            self.add_tool_sync(tool_name)

    def get_tool_registry(self):
        return self.tool_registry
    
    def register_self(self):
        self.tool_registry[self.name] = self.get_callable_functions()
        self.imported_tools.add(self.name)

    async def wake_word_identified(self):
        for tool_name in self.tool_registry:
            if tool_name == "internal":
                continue
            kwargs = {
                "self": self.tool_registry[tool_name]["module"]
            }
            await self.tool_registry[tool_name]["wake_word_identified"](**kwargs)

    async def undo_wake_word_identified(self):
        for tool_name in self.tool_registry:
            if tool_name == "internal":
                continue
            kwargs = {
                "self": self.tool_registry[tool_name]["module"]
            }
            await self.tool_registry[tool_name]["undo_wake_word_identified"](**kwargs)

    @available_for_lucy
    async def add_tool(self, name):
        self.imported_tools.add(name)
        return self.tool_registry[name]["module"].build_documentation()
    
    def add_tool_sync(self, name):
        print(f"Adding tool: {name}")
        if name not in LInternal.tool_classes:
            return f"Tool '{name}' is not available. Available tools: {', '.join(LInternal.tool_classes.keys())}"
        if name not in self.tool_registry:
            tool_obj = LInternal.tool_classes[name]()
            tool_obj.set_websocket(self.websocket)
            tool_obj.set_user_id(self.user_id)
            tool_obj.set_session(self.session)
            tool_obj.setup()
            self.tool_registry[name] = tool_obj.get_callable_functions()

        tool_obj = self.tool_registry[name]["module"]
        return tool_obj.build_documentation()
    
    def tool_is_imported(self, name):
        return name in self.imported_tools
    
    def get_global_web_preview(module_name, path, args={}):
        return LInternal.tool_classes[module_name].get_global_web_preview(path, args=args)