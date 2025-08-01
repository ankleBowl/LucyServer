from .lucy_module import LucyModule, available_for_lucy

from spotipy import Spotify
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyOAuth
from fuzzywuzzy import fuzz
from importlib import resources

import asyncio
import os
import json
import re
import requests
import base64
import time

REDIRECT_URL = "http://127.0.0.1:8000/v1/module/spotify/callback"
SCOPE = "user-read-playback-state user-modify-playback-state user-read-currently-playing user-library-read user-library-modify"

class LSpotify(LucyModule):
    def __init__(self):
        super().__init__("spotify")
    

    def refresh_tokens(self):
        # STUB - WILL REFRESH TOKENS IN A SEC - WILL SET self.is_logged_in
        if "refresh_token" not in self.tokens:
            self.is_logged_in = False
            return
        
        refresh_token = self.tokens["refresh_token"]
        url = "https://accounts.spotify.com/api/token"
        form_data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.CLIENT_ID
        }
        authorization = self.CLIENT_ID + ":" + self.CLIENT_SECRET 
        authorization = base64.b64encode(authorization.encode("ascii")).decode("ascii")
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": "Basic " + authorization
        }
        response = requests.post(url, data=form_data, headers=headers)
        if response.status_code != 200:
            print("Error refreshing tokens:", response.status_code, response.text)
            self.is_logged_in = False
            return {"error": "Error refreshing tokens"}
        new_tokens = response.json()
        new_tokens["refresh_token"] = refresh_token 
        self.set_tokens(new_tokens)


    def set_tokens(self, tokens):
        tokens["expires_in"] = tokens["expires_in"] + int(time.time())
        self.tokens = tokens
        self.save_data("tokens", tokens)
        self.is_logged_in = True

        self.sp = Spotify(auth=self.tokens["access_token"])
        
        self.liked_songs = LikedSongs(self.sp, self.save_data, self.load_data)
        self.liked_songs.update_liked_songs_cache()

        self.user_playlists = UserPlaylists(self.sp, self.save_data, self.load_data)
        self.user_playlists.update_user_playlists_cache()

    def setup(self):
        data = self.load_data("spotify_api", {
            "client_id": "",
            "client_secret": "",
        })
        self.CLIENT_ID = data["client_id"]
        self.CLIENT_SECRET = data["client_secret"]

        self.is_logged_in = False
        self.sp = None
        self.tokens = self.load_data("tokens", {})

        self.refresh_tokens()

        self.player_is_loaded = False
        

    async def _wrapped_spotify_function(self, func, tries=0, **kwargs):
        if self.is_logged_in == False:
            return {"error": "Not logged in to Spotify."}
        
        if self.tokens["expires_in"] < int(time.time()) + 60:
            self.refresh_tokens()
            if self.is_logged_in == False:
                return {"error": "Not logged in to Spotify."}
            
        try:
            response = func(**kwargs)
            return response
        except SpotifyException as e:
            if e.reason == "NO_ACTIVE_DEVICE":
                if tries == 1:
                    return {"error": "An error occured starting playback"}
                
                self.player_is_loaded = False
                await self.send_socket_message({"message": "INIT_SPOTIFY_STREAMING"})

                timeout = 0 # MAX IS 5 SECONDS
                while not self.player_is_loaded and timeout < 5:
                    await asyncio.sleep(0.1) # Wait for incoming websocket message to set player_is_loaded to True
                    timeout += 0.1

                # wait an extra 0.25 seconds to ensure player is ready
                await asyncio.sleep(0.25)

                if not self.player_is_loaded:
                    return {"error": "An error occured starting playback"}
                                
                return await self._wrapped_spotify_function(func, tries=1, **kwargs)
            else:
                print("SPOTIFY EXCEPTION", e, e.reason)
                return {"error": f"An error occurred: {e}"}
            

    def clean_name(self, name):
        # Remove text in parentheses
        name = re.sub(r'\([^)]*\)', '', name)

        # Replace & with 'and'
        formatted_name = name.replace("&", "and")
        
        # Convert to lowercase
        formatted_name = formatted_name.lower()
        
        # Remove non-alphanumeric characters except spaces
        formatted_name = ''.join(e for e in formatted_name if e.isalnum() or e == ' ')
        
        # Remove extra spaces
        formatted_name = formatted_name.split(" ")
        formatted_name = [word for word in formatted_name if word != ""]
        formatted_name = " ".join(formatted_name)
        
        return formatted_name


    def build_utterences(self, item_type, spotify_item):
        utterences = []
        if item_type == "track":
            item_type = "song"
        item_name = self.clean_name(spotify_item["name"])

        utterences.append(item_name)
        utterences.append(f"the {item_type} {item_name}")
        if item_type != "artist":
            primary_artist = spotify_item["artists"][0]["name"]
            utterences.append(f"{item_name} by {primary_artist}")
            utterences.append(f"the {item_type} {item_name} by {primary_artist}")
        return utterences
    
    def build_natrual_language_str(self, item_type, spotify_item):
        if item_type == "track":
            item_type = "song"
        item_name = self.clean_name(spotify_item["name"])
        natrual_language_str = f"{item_type} {item_name}"
        if item_type != "artist":
            primary_artist = spotify_item["artists"][0]["name"]
            natrual_language_str += f" by {primary_artist}"
        return natrual_language_str

    @available_for_lucy
    async def play_playlist(self, playlist_name: str):
        """
        Plays a Spotify playlist based on a fuzzy search of the playlist name.
        To play liked songs, use the query "liked-tracks".
        """
        if self.is_logged_in == False:
            return {"error": "Not logged in to Spotify."}

        if playlist_name.lower() == "liked-tracks":
            liked_songs = self.liked_songs.get_liked_songs_cache()
            liked_songs = list(liked_songs.keys())
            import random
            random.shuffle(liked_songs)
            liked_songs = liked_songs[:100]
            await self._wrapped_spotify_function(self.sp.start_playback, uris=liked_songs)
            return {"status": "playing", "item": "liked-tracks"}
            
        possible_playlists = self.user_playlists.fuzzy_search(playlist_name, return_amount=1)
        if len(possible_playlists) == 0:
            return {"error": f"No playlists found matching '{playlist_name}'"}
        best_playlist = possible_playlists[0][1]
        await self._wrapped_spotify_function(self.sp.start_playback, context_uri=best_playlist["uri"])
        return {"status": "playing", "item": f"playlist '{best_playlist['name']}'"}

    @available_for_lucy
    async def get_playlist_details(self, playlist_name: str):
        """
        Retrieves details about a Spotify playlist, including its name, description, owner, number of tracks, and the first 20 tracks.
        To get information about liked songs, use the query "liked-tracks".
        """
        if self.is_logged_in == False:
            return {"error": "Not logged in to Spotify."}

        if playlist_name.lower() != "liked-tracks":
            possible_playlists = self.user_playlists.fuzzy_search(playlist_name, return_amount=1)
            if len(possible_playlists) == 0:
                return {"error": f"No playlists found matching '{playlist_name}'"}
            best_playlist = possible_playlists[0][1]

            tracks = []
            # results = self.sp.playlist_items(best_playlist["id"], limit=20)
            results = await self._wrapped_spotify_function(self.sp.playlist_items, playlist_id=best_playlist["id"], limit=20)
            for item in results["items"]:
                track = item["track"]
                if track is None:
                    continue
                tracks.append({
                    "name": track["name"],
                    "artist": track["artists"][0]["name"],
                })
        else:
            liked_songs = self.liked_songs.get_liked_songs_cache()
            best_playlist = {
                "name": "Liked Songs",
                "description": "Your liked songs on Spotify",
                "owner": {"display_name": "You"},
                "tracks": {"total": len(liked_songs)},
            }
            tracks = []
            for track_id in list(liked_songs.keys())[:20]:
                track = liked_songs[track_id]
                if track is None:
                    continue
                tracks.append({
                    "name": track["name"],
                    "artist": track["artists"][0]["name"],
                })

        return {
            "name": best_playlist["name"],
            "description": best_playlist["description"],
            "owner": best_playlist["owner"]["display_name"],
            "num_tracks": best_playlist["tracks"]["total"],
            "first_20_tracks": tracks,
        }

    @available_for_lucy
    async def play(self, string_query: str, should_queue: bool = False):
        """
        Plays a song, album, or artist on Spotify based on a search query. 
        This takes natrual language input. For example, "wildfire", "the song wildfire", and "the song wildfire by Jeremy Zucker" are all valid inputs.
        This will play tracks, albums, or artists. It will not play playlists.
        """
        if self.is_logged_in == False:
            return {"error": "Not logged in to Spotify."}
            
        found_track = self.liked_songs.is_in_liked_songs(string_query)
        if found_track is not None:
            func = self.sp.start_playback if not should_queue else self.sp.add_to_queue
            track_uris = [found_track["uri"]]
            if not should_queue:
                await self._wrapped_spotify_function(func, uris=track_uris)
            else:
                await self._wrapped_spotify_function(func, uri=found_track["uri"])
            return {"status": "playing", "item": f"{found_track['name']} (track) by {found_track['artists'][0]['name']}"}
        
        # results = self.sp.search(q=string_query, type="track,album,artist", limit=10)
        results = await self._wrapped_spotify_function(self.sp.search, q=string_query, type="track,album,artist", limit=10)
        items = []
        added = set()
        for item_type in ["tracks", "albums", "artists"]:
            if item_type in results:
                for item in results[item_type]["items"]:
                    if item == None:
                        continue
                    nat_lang_str = self.build_natrual_language_str(item_type[:-1], item).lower()
                    if nat_lang_str in added:
                        continue
                    item_type_singular = item_type[:-1]
                    items.append({"type": item_type_singular, "item": item, "utterence": self.build_utterences(item_type_singular, item)})
                    added.add(self.build_natrual_language_str(item_type_singular, item).lower())

        best_items = []
        best_score = 0
        for entry in items:
            for utterence in entry["utterence"]:
                score = fuzz.ratio(string_query.lower(), utterence.lower())
                # boost score by 20 if in liked songs
                if entry["type"] == "track":
                    liked_songs = self.liked_songs.get_liked_songs_cache()
                    if entry["item"]["uri"] in liked_songs:
                        score += 20
                if score > best_score:
                    best_score = score
                    best_items = [entry]
                elif score == best_score:
                    best_items.append(entry)

        if best_score < 50:
            return {"error": f"No results found for '{string_query}'"}
        
        if len(best_items) > 1:
            best_items = [item for item in best_items if item["type"] != "artist"]
            print("Filtered out artists, remaining items:", len(best_items))
            if len(best_items) > 1:
                best_items = [item for item in best_items if item["type"] != "album"]

        if len(best_items) > 1:
            options = []
            for item in best_items:
                options.append(self.build_natrual_language_str(item["type"], item["item"]))

            song_names = {}

            for item in best_items:
                song_name = item["item"]["name"].lower()
                if song_name not in song_names:
                    song_names[song_name] = []
                song_names[song_name].append(item["item"]["artists"][0]["name"])

            response = "There are multiple options. "
            for song_name in song_names:
                response += f"{song_name.title()} by "
                artists = song_names[song_name]
                for i, artist in enumerate(artists):
                    if i == 0:
                        response += artist
                    elif i == len(artists) - 1:
                        response += f", and by {artist}. "
                    else:
                        response += f", by {artist}"
                response += " And "
            response = response[:-5] + "."

            return [
                {"error": f"Multiple results found for '{string_query}'", "options": options},
                {"tag": "assistant", "content": response},
                {"tag": "end", "content": ""}
            ]


        best_item = best_items[0]

        func = self.sp.start_playback if not should_queue else self.sp.add_to_queue
        track_uris = []
        if best_item["type"] == "track":
            track_uris = [best_item["item"]["uri"]]
        elif best_item["type"] == "album":
            album_tracks = await self._wrapped_spotify_function(self.sp.album_tracks, album_id=best_item["item"]["id"])
            track_uris = [track["uri"] for track in album_tracks["items"]]
        elif best_item["type"] == "artist":
            artist_tracks = await self._wrapped_spotify_function(self.sp.artist_top_tracks, artist_id=best_item["item"]["id"])
            track_uris = [track["uri"] for track in artist_tracks["tracks"]]

        if should_queue:
            for track_uri in track_uris:
                response = await self._wrapped_spotify_function(func, uri=track_uri)
        else:
            response = await self._wrapped_spotify_function(func, uris=track_uris)

        if response != None and "error" in response:
            return response

        best_item_string = f"{best_item['item']['name']} ({best_item['type']})"
        if best_item["type"] != "artist":
            best_item_string += f" by {best_item['item']['artists'][0]['name']}"
        return {"status": "playing", "item": best_item_string}

    @available_for_lucy
    async def get_current_playback(self):
        """
        Retrieves information about the currently playing track on Spotify, or "what song is currently playing".
        """
        if self.is_logged_in == False:
            return {"error": "Not logged in to Spotify."}
        
        current_playback = await self._wrapped_spotify_function(self.sp.current_playback)
        print("Current playback:", current_playback)
        if current_playback is None or current_playback.get("item") is None:
            return {"status": "no_song_playing"}
        return {
            "track_name": current_playback["item"]["name"], 
            "artist_name": current_playback["item"]["artists"][0]["name"],
            "album_name": current_playback["item"]["album"]["name"],
            "is_paused": not current_playback["is_playing"],
            "is_shuffling": current_playback["shuffle_state"],
            "completion_amount": current_playback["progress_ms"] / current_playback["item"]["duration_ms"],
        }
    
    @available_for_lucy
    async def control_playback(self, action: str):
        """
        Controls playback on Spotify. Action can be one of the following: "play", "pause", "next", "previous", "shuffle", "noshuffle".
        """
        if self.is_logged_in == False:
            return {"error": "Not logged in to Spotify."}
        
        if action == "play":
            await self._wrapped_spotify_function(self.sp.start_playback)
        elif action == "pause":
            await self._wrapped_spotify_function(self.sp.pause_playback)
        elif action == "next":
            await self._wrapped_spotify_function(self.sp.next_track)
        elif action == "previous":
            await self._wrapped_spotify_function(self.sp.previous_track)
        elif action == "shuffle":
            await self._wrapped_spotify_function(self.sp.shuffle, state=True)
        elif action == "noshuffle":
            await self._wrapped_spotify_function(self.sp.shuffle, state=False)

    @available_for_lucy
    async def like_current_song(self):
        """
        Likes the currently playing song on Spotify.
        """
        if self.is_logged_in == False:
            return {"error": "Not logged in to Spotify."}
        
        current_playback = await self._wrapped_spotify_function(self.sp.current_playback)
        if current_playback is None or current_playback.get("item") is None:
            return {"error": "No song is currently playing"}
        track_id = current_playback["item"]["id"]
        await self._wrapped_spotify_function(self.sp.current_user_saved_tracks_add, tracks=[track_id])
        self.liked_songs.update_liked_songs_cache()
        return {"status": "liked", "item": f"{current_playback['item']['name']} by {current_playback['item']['artists'][0]['name']}"}

    async def handle_message(self, message):
        print(f"Received message in LSpotify: {message}")
        if message["message"] == "SPOTIFY_STREAMING_INITIATED":
            self.player_is_loaded = True

    # GLOBAL AUTH STUFF
    state_map = {}

    def get_global_web_preview(path=None, args={}):
        if path == "callback":
            state = args.get("state", None)
            user_id = LSpotify.state_map.get(state, None)
            if user_id is None:
                return {
                    "type": "html",
                    "content": "<h1>Invalid state. Please try logging in again.</h1>",
                }
            del LSpotify.state_map[state]
            url = f"/v1/{user_id}/module/spotify/callback?code={args.get('code', '')}&state={state}"
            return {
                "type": "redirect",
                "content": url,
            }
        return {
            "type": "html",
            "content": "<h1>Invalid path</h1>",
        }
            


    def get_web_preview(self, path=None, args={}):
        if path == "web_player":
            html_path = resources.files("lucyserver").joinpath("lspotify.html")

            html = open(html_path, "r").read()
            html = html.replace("[[SPOTIFY_TOKEN]]", self.tokens["access_token"])
            return {
                "type": "html",
                "content": html,
            }
        if path == "authorize":
            redirect_url = "https://accounts.spotify.com/authorize"

            self.state = os.urandom(16).hex()
            LSpotify.state_map[self.state] = self.user_id

            query_params = {
                "response_type": "code",
                "client_id": self.CLIENT_ID,
                "scope": SCOPE,
                "redirect_uri": REDIRECT_URL,
                "state": self.state,
            }
            query_string = "&".join([f"{key}={value}" for key, value in query_params.items()])
            auth_url = f"{redirect_url}?{query_string}"
            return {
                "type": "redirect",
                "content": auth_url,
            }
        if path == "callback":
            code = args.get("code", None)
            state = args.get("state", None)
            if state != self.state:
                return {
                    "type": "html",
                    "content": "<h1>State mismatch. Please try logging in again.</h1>",
                }
            url = "https://accounts.spotify.com/api/token"
            form_data = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URL,
            }
            authorization = self.CLIENT_ID + ":" + self.CLIENT_SECRET
            authorization = base64.b64encode(authorization.encode("ascii")).decode("ascii")
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": "Basic " + authorization
            }
            response = requests.post(url, data=form_data, headers=headers)
            if response.status_code != 200:
                print("Error getting tokens:", response.status_code, response.text)
                return {
                    "type": "html",
                    "content": "<h1>Error getting tokens. Please try logging in again.</h1>",
                }
            self.set_tokens(response.json())
            return {
                "type": "html",
                "content": "<h1>Successfully logged in to Spotify! You can now close this window.</h1><script>setTimeout(() => { window.close(); }, 2000);</script>",
            }
        return {
            "type": "html",
            "content": f"<h1>Invalid path: {path}</h1>",
        }


    
class UserPlaylists:
    def __init__(self, sp, save_data_func, load_data_func):
        self.sp = sp
        self.save_data_func = save_data_func
        self.load_data_func = load_data_func
    
    def get_user_playlists_cache(self):
        return self.load_data_func("user_playlists_cache")
    
    def update_user_playlists_cache(self):
        playlists = {}
        offset = 0
        while True:
            print("Reading from " + str(offset) + "...")
            results = self.sp.current_user_playlists(limit=50, offset=offset)
            print("Found", len(results['items']), "playlists")
            for item in results['items']:
                playlists[item['id']] = item
            if len(results['items']) < 50:
                break
            offset += 50
        self.save_data_func("user_playlists_cache", playlists)

    def fuzzy_search(self, query: str, return_amount: int = 5):
        playlists = self.get_user_playlists_cache()
        best_playlists = []

        for playlist_id in playlists:
            playlist = playlists[playlist_id]
            name = playlist["name"]
            score = fuzz.ratio(query.lower(), name.lower())
            best_playlists.append((score, playlist))

        best_playlists.sort(key=lambda x: x[0], reverse=True)
        best_playlists = best_playlists[:return_amount]

        return best_playlists

class LikedSongs:
    def __init__(self, sp, save_data_func, load_data_func):
        self.sp = sp
        self.save_data_func = save_data_func
        self.load_data_func = load_data_func

    def get_liked_songs_cache(self):
        return self.load_data_func("liked_songs_cache", {})
    
    def update_liked_songs_cache(self):
        MAX_SONGS = 10000000

        offset = 0
        songs = self.load_data_func("liked_songs_cache", {})

        while True:
            caught_up = False

            print("Reading from " + str(offset) + "...")
            results = self.sp.current_user_saved_tracks(limit=50, offset=offset)
            print("Found", len(results['items']), "songs")
            for item in results['items']:
                track = item['track']
                song_id = "spotify:track:" + track['id']
                if song_id in songs:
                    caught_up = True
                    break
                songs[song_id] = track
                if len(songs) >= MAX_SONGS:
                    break
            if len(songs) >= MAX_SONGS or caught_up:
                break
            offset += 50
            if len(results['items']) == 0:
                break

        self.save_data_func("liked_songs_cache", songs)

    def get(self):
        songs = self.get_liked_songs_cache()
        return list(songs.values())
    
    def is_in_liked_songs(self, track_name: str):
        songs = self.get_liked_songs_cache()
        for song_id in songs:
            song = songs[song_id]
            if song["name"].lower() == track_name.lower():
                return song
        return None

    
if __name__ == "__main__":
    spotify = LSpotify()
    spotify.set_user_id("meewhee")
    spotify.setup()