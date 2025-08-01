from .lucy_module import LucyModule, available_for_lucy
import time
import asyncio
import json

from ..message import Message

class Timer:

    callback = None

    def __init__(self, duration_seconds, label=None):
        self.label = label
        self.duration_seconds = duration_seconds

    def time_remaining(self):
        return self.finish_time - time.time()
    
    def get_pretty_total_duration(self):
        total_seconds = self.duration_seconds
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        string = ""
        if hours > 0:
            string += f"{hours} hours, "
        if minutes > 0:
            string += f"{minutes} minutes, "
        if seconds > 0:
            string += f"{seconds} seconds, "
        return string.rstrip(", ")
    
    def get_label(self):
        return self.label
    
    def start(self):
        self.finish_time = time.time() + self.duration_seconds
        self.task = asyncio.create_task(self._start_internal())

    async def _start_internal(self):
        print("Sleeping for", self.duration_seconds, "seconds...")
        await asyncio.sleep(self.duration_seconds)
        print("Running callback...")
        await self.callback(self)

    def cancel(self):
        self.task.cancel()
        

class LClock(LucyModule):
    def __init__(self):
        super().__init__("clock")

    def setup(self):
        self.timers = []
        Timer.callback = self._timer_complete_callback

    @available_for_lucy
    async def create_timer(self, duration, unit, label=None):
        """Creates a timer for the specified duration and unit (seconds, minutes, hours) with an optional label."""
        unit = unit.lower()
        if unit not in ["seconds", "minutes", "hours"]:
            return {"error": "Invalid time unit. Use 'seconds', 'minutes', or 'hours'."}
        multiplier = {"seconds": 1, "minutes": 60, "hours": 3600}[unit]
        total_seconds = duration * multiplier
        if total_seconds >= 86400:
            return {"error": "Timer duration must be less than 24 hours."}
        if total_seconds <= 0:
            return {"error": "Timer duration must be greater than 0."}
        
        print(f"Creating timer for {duration} {unit} ({total_seconds} seconds) with label '{label}'")
        
        timer = Timer(total_seconds, label)
        self.timers.append(timer)
        timer.start()

        return {"message": f"Timer set for {duration} {unit} ({total_seconds} seconds)."}
    
    @available_for_lucy
    async def stop_timer_sound(self):
        """Stops the timer sound if it is currently playing."""
        await self.send_socket_message({"message": "STOP_TIMER_SOUND"})
    
    async def _timer_complete_callback(self, timer):
        self.timers.remove(timer)
        messages = [
            Message("tool_response", json.dumps({
                "status": "timer_complete",
                "duration": timer.get_pretty_total_duration(),
                "info": "The timer sound is now playing. You can stop it with the 'stop_timer_sound' command."
            })),
        ]
        if timer.get_label():
            messages[0].content["label"] = timer.get_label()
            messages.append(
                Message("assistant", f"Timer {timer.get_label()} has completed."))
        else:
            messages.append(
                Message("assistant", f"The {timer.get_pretty_total_duration()} timer has completed."))
        
        messages.append(Message("end", ""))

        await self.send_socket_message({"message": "START_TIMER_SOUND"})
        await self.session.run(messages)

if __name__ == "__main__":
    clock = LClock()
    clock.setup()
    asyncio.run(clock.create_timer(5, "minutes"))

    
    