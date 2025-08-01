import requests
import json

from .lucy_module import LucyModule, available_for_lucy

# TURNING ON LIGHTS AND SETTING COLOR SHOULD BE DIFFERENT FUNCTIONS
# REPLACE GET_DEVICE_TYPE WITH GET_DEVICES_IN_ROOM
# DEFAULT FLOW SHOULD BE: GET DEVICES IN ROOM -> GET DEVICE FUNCTIONS -> CALL FUNCTION
# CURRENTLY IT IS: GET DEVICES WITH TYPE -> GET DEVICE FUNCTIONS -> CALL FUNCTION

class LHome(LucyModule):
    def __init__(self):
        super().__init__("home")
        

    def setup(self):
        data = self.load_data("homeassistant", {
            "hass_url": "",
            "hass_token": "",
        })
        self.HASS_URL = data["hass_url"]
        self.HASS_TOKEN = data["hass_token"]

    def _make_request(self, endpoint, data=None):
        url = self.HASS_URL + endpoint
        headers = {
            "Authorization": f"Bearer {self.HASS_TOKEN}"
        }
        if data is None:
            response = requests.get(url, headers=headers)
        else:
            response = requests.post(url, headers=headers, json=data)

        return response
    
    def _get_device_areas(self, device_ids):
        template = "{{ "
        for device_id in device_ids:
            template += f"area_name('{device_id}'), "
        template = template[:-2] + " }}"

        response = self._make_request("/template", {"template": template}).text[1:-1].split(", ")

        device_area_map = {}
        for device_id, area_name in zip(device_ids, response):
            area_name = area_name[1:-1]
            if area_name == "on":
                area_name = "None"
            device_area_map[device_id] = area_name

        return device_area_map

    # def get_area_ids(self):
    #     endpoint = "/template"
    #     data = {
    #         "template": "{{ areas() }}"
    #     }
    #     response = self._make_request(endpoint, data).text
    #     response = response[1:-1].split(", ")
    #     areas = {}
    #     for area in response:
    #         area = area[1:-1]
    #         areas[area] = f"home:area:{area}"

    #     return areas
    
    @available_for_lucy
    async def get_devices(self, room):
        """Searches for smart devices in the Home. room is the room to search in (e.g., 'living room'). You may use 'all' to search all rooms and 'default' to search the default room. If the user does not specify a room, use the default room."""
        if self.HASS_TOKEN == "" or self.HASS_URL == "":
            return "Home Assistant URL or token is not set. Ask the user to set it by modifying the configuration file."
        
        endpoint = "/states"
        response = self._make_request(endpoint).json()
        
        # Reformat as a dictionary for easier access
        devices = {}
        for device in response:
            devices[device["entity_id"]] = device

        # Remove devices that are in groups
        for device_id in list(devices.keys()):
            if device_id not in devices:
                continue
            if "entity_id" in devices[device_id]["attributes"]:
                group_devices = devices[device_id]["attributes"]["entity_id"]
                for group_device in group_devices:
                    if group_device in devices:
                        del devices[group_device]
        
        # Get device areas
        device_ids = list(devices.keys())
        device_areas = self._get_device_areas(device_ids)

        # Filter devices with no area
        for device_id in list(devices.keys()):
            if device_areas[device_id] == "None":
                del devices[device_id]
            if room == "all":
                continue
            if room == "default":
                room = "garage"
            if device_areas[device_id].lower() != room.lower():
                if device_id in devices:
                    del devices[device_id]

        if len(devices) == 0:
            return {"error": f"Room '{room}' does not exist", "valid_rooms": list(set(device_areas.values()))}

        output = []
        for device_id, device in devices.items():
            area = device_areas[device_id]
            output.append({
                "id": f"home:device:{device_id}",
                "room": area,
                "name": device["attributes"].get("friendly_name", device_id),
                "type": device["entity_id"].split(".")[0],
                "state": device["state"],
            })

        return {"devices": output}
    
    def _dump_device_functions(self, device_type):
        services = self._make_request("/services").json()
        for service in services:
            if service["domain"] == device_type:
                services = service
                break
        print("Dumping services for device type:", device_type)
        json.dump(services, open(f"{device_type}_services.json", "w"), indent=4)

    @available_for_lucy
    async def get_device_functions(self, device_id):
        """Returns the available functions to control a specific device."""
        if self.HASS_TOKEN == "" or self.HASS_URL == "":
            return "Home Assistant URL or token is not set. Ask the user to set it by modifying the configuration file."
        
        device_type = device_id.split(":")[2].split(".")[0]
        functions = []
        if device_type == "light":
            functions.append(LHome.turn_on_lights)
            functions.append(LHome.turn_off_lights)
            functions.append(LHome.set_lights)
        else:
            return {"error": f"Device type '{device_type}' is not supported yet."}
        
        for x in range(len(functions)):
            functions[x] = self.build_documentation_for_func(functions[x])

        return {"functions": functions}
    
    async def set_lights(self, device_ids: list, brightness_pct: int = None, color_name: str = None):
        """Sets the brightness percentage (0-100) and/or the color name (e.g., 'red', 'blue', 'default') of a list of light devices. You can optionally specify either brightness_pct or color_name or both."""
        if brightness_pct is None and color_name is None:
            return {"error": "You must specify either brightness_pct or color_name or both."}
        data = {}
        if brightness_pct is not None:
            data["brightness_pct"] = brightness_pct
        if color_name is not None:
            data["color_name"] = color_name
        for device_id in device_ids:
            response = self._trigger(device_id, "turn_on", **data)
        return {"status": "success"}

    async def turn_on_lights(self, device_ids: list):
        """Turns on a list of light devices. You can optionally specify the brightness percentage (0-100) and the color name (e.g., 'red', 'blue')."""
        for device_id in device_ids:
            response = self._trigger(device_id, "turn_on")
        return {"status": "success"}

    async def turn_off_lights(self, device_ids: list):
        """Turns off a list of light devices."""
        for device_id in device_ids:
            response = self._trigger(device_id, "turn_off")
        return {"status": "success"}

    def _trigger(self, device_id, trigger_name, **kwargs):
        device_type = device_id.split(":")[2].split(".")[0]
        # endpoint = f"/services/{device_type}/{trigger_name}?return_response=true"
        endpoint = f"/services/{device_type}/{trigger_name}"
        data = {
            "entity_id": device_id.split(":")[2],
            **kwargs
        }
        response = self._make_request(endpoint, data)
        print("Request to", endpoint, "with data", data)
        print(response.text)
        return response.text
    
# if __name__ == "__main__":
#     import asyncio

#     lhome = LHome()
#     print(asyncio.run(lhome.turn_on_lights(["home:device:light.levds_dimmer_a16d_light"], brightness_pct=1)))
#     # print(asyncio.run(lhome.turn_off_lights(["home:device:light.levds_dimmer_a16d_light"])))