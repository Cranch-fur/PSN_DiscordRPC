import logging
import sys
import time
import yaml

from psnawp_api import PSNAWP
from pypresence import Presence

# Constants for logging
LOG_FORMAT = "%(asctime)s %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"






class PSNDiscordRPC:
    def __init__(self, config_path="config.yml"):
        self.Init_Logs()
        self.Init_Config(config_path)
        
        # Initialize API clients
        self.psn = PSNAWP(self.config["npsso_key"])
        self.rpc = Presence(self.config["client_app_id"])
        
        # State tracking variables
        self.current_activity = None
        self.start_time = None
        self.current_system = self.config["systems"]["default"]
        
        self.Init_RPC()

    def Init_Logs(self):
        """Configures standard output logging."""
        self.log = logging.getLogger()
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
        self.log.addHandler(handler)
        self.log.setLevel(logging.INFO)

    def Init_Config(self, path):
        """Safely loads application settings from the YAML file."""
        with open(path, encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

    def Init_RPC(self):
        """Establishes a connection to the local Discord client."""
        try:
            self.rpc.connect()
            self.log.info("Successfully connected to Discord RPC.")
        except Exception as e:
            self.log.error(f"Failed to connect to Discord: {e}")




    def Start(self):
        """Main loop that polls PSN presence and updates Discord."""
        previous_presence = None
        update_interval = self.config.get("update_interval", 15)
        
        while True:
            try:
                user = self.psn.user(online_id=self.config["online_id"])
                presence = user.get_presence()

                # Only process and update if presence actually changed
                if presence != previous_presence:
                    self.RPC_Update(presence)
                    previous_presence = presence

            except Exception as e:
                # Catching exceptions prevents the script from crashing during Sony 503 errors
                self.log.error(f"Network or parsing error fetching presence: {e}")

            time.sleep(update_interval)




    def RPC_Update(self, presence):
        """Parses the raw PSN presence dict and triggers the appropriate RPC update."""
        basic_presence = presence.get("basicPresence", {})
        primary_info = basic_presence.get("primaryPlatformInfo", {})
        
        # Default to offline to avoid undefined behavior
        online_status = primary_info.get("onlineStatus", "offline")

        if online_status == "offline":
            self.RPC_Clear()
            return

        # Determine user's active platform
        platform = primary_info.get("platform")
        if platform == "PS5":
            self.current_system = "ps5_main"
        elif platform == "PS4":
            self.current_system = "ps4_main"

        game_info_list = basic_presence.get("gameTitleInfoList", [])
        
        if not game_info_list:
            self.Scenario_Idle()
        else:
            self.Scenario_InGame(game_info_list[0])

    def RPC_Clear(self):
        """Clears Discord activity if the user goes offline."""
        if self.current_activity is not None:
            self.rpc.clear()
            self.current_activity = None
            self.start_time = None
            self.log.info("User is offline. Presence cleared.")




    def Scenario_Idle(self):
        """Sets Discord activity for users who are online but at the dashboard."""
        if self.current_activity != "online":
            self.start_time = int(time.time())
            self.current_activity = "online"

        system_name = self.config["systems"].get(self.current_system, "PlayStation")

        self.rpc.update(
            state="Online",
            start=self.start_time,
            small_image=self.current_system,
            large_image=self.current_system,
            small_text=system_name,
            large_text="Not in-game"
        )
        self.log.info("Presence updated: Online but not in-game.")


    def Scenario_InGame(self, game_info):
        """Sets Discord activity for users actively playing a game."""
        game_id = game_info.get("npTitleId") or game_info.get("titleId", "unknown_id")
        game_title = game_info.get("titleName", "Unknown Game")
        game_status = game_info.get("gameStatus")
        
        if game_status:
            game_title = f"{game_title}: {game_status}"

        # Reset timer if the user switched to a different game
        if game_id != self.current_activity:
            self.start_time = int(time.time())
            self.current_activity = game_id

        system_name = self.config["systems"].get(self.current_system, "PlayStation")
        
        # Check all possible keys for the game cover image
        icon_url = game_info.get("conceptIconUrl") or game_info.get("npTitleIconUrl") or game_info.get("iconUrl")

        # Determine large image: use direct URL if available, fallback to console icon
        large_image = self.current_system
        if icon_url and icon_url.startswith("http"):
            large_image = icon_url

        state_console = self.config.get("state_console", False)

        if state_console:
            self.rpc.update(
                state=game_title,
                start=self.start_time,
                small_image=self.current_system,
                large_image=large_image,
                small_text=system_name,
                large_text=game_title
            )
        else:
            self.rpc.update(
                details=f"Playing {game_title}",
                start=self.start_time,
                large_image=large_image,
                large_text=game_title
            )
            
        self.log.info(f"Presence updated: Playing {game_title}.")




if __name__ == "__main__":
    app = PSNDiscordRPC()
    app.Start()