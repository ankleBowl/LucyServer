from tools.lucy_module import LucyModule, available_for_lucy

# CREATED BY GEMINI BECAUSE I AM SO SICK OF WRITING THE SAME BASIC TOOLS OVER AND OVER AGAIN
from datetime import datetime, timedelta

class LTime(LucyModule):
    def __init__(self):
        """
        Initializes the Time module.
        """
        super().__init__("time")

    def _get_ms_since_epoch(self, dt_obj):
        """Converts a datetime object to milliseconds since the epoch."""
        return int(dt_obj.timestamp() * 1000)

    def _parse_time_id(self, time_id: str):
        """Parses a time ID string and returns the milliseconds since epoch."""
        try:
            parts = time_id.split(':')
            if len(parts) != 2 or parts[0] != 'time':
                raise ValueError("Invalid time ID format. Must be 'time:<ms_since_epoch>'.")
            return int(parts[1])
        except (ValueError, IndexError) as e:
            raise ValueError(f"Could not parse time_id '{time_id}': {e}") from e


    @available_for_lucy
    async def get_current_time(self):
        """Gets the current time as a unique time ID"""
        now = datetime.now()
        ms_since_epoch = self._get_ms_since_epoch(now)
        return f"time:{ms_since_epoch}"

    @available_for_lucy
    async def get_specific_time(self, year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0):
        """Gets the time for a specific date and time and returns it as a unique time ID."""
        try:
            specific_date = datetime(year, month, day, hour, minute, second)
            ms_since_epoch = self._get_ms_since_epoch(specific_date)
            return f"time:{ms_since_epoch}"
        except ValueError as e:
            return {"error": f"Invalid date or time provided: {e}"}

    @available_for_lucy
    async def get_duration_between(self, time_id_1: str, time_id_2: str):
        """Calculates the duration between two time IDs and returns it in a human-readable format."""
        try:
            ms1 = self._parse_time_id(time_id_1)
            ms2 = self._parse_time_id(time_id_2)

            # Calculate absolute difference in seconds
            difference_seconds = abs(ms1 - ms2) / 1000
            delta = timedelta(seconds=difference_seconds)

            days = delta.days
            hours, remainder = divmod(delta.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)

            duration_parts = []
            if days > 0:
                duration_parts.append(f"{days} day{'s' if days != 1 else ''}")
            if hours > 0:
                duration_parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
            if minutes > 0:
                duration_parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
            if seconds > 0 or not duration_parts:
                 duration_parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")

            return {
                "duration": ", ".join(duration_parts)
            }
        except ValueError as e:
            return {"error": str(e)}
        
    @available_for_lucy
    async def get_human_readable_time(self, time_id: str):
        """
        Converts a time ID to a human-readable format.

        Args:
            time_id (str): The time ID (e.g., 'time:1678886400000').

        Returns:
            dict: A dictionary containing the human-readable time string.
        """
        try:
            ms = self._parse_time_id(time_id)
            dt = datetime.fromtimestamp(ms / 1000)
            return dt.strftime("%Y-%m-%d %H:%M:%S")

        except ValueError as e:
            return {"error": str(e)}
