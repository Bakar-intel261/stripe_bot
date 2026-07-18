import requests
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class DonutManager:
    """Manages Donut Browser profiles via REST API"""
    
    def __init__(self, api_url="http://localhost:10108/v1"):
        self.api_url = api_url
        self.timeout = 30
    
    def create_profile(self, name: str, browser: str = "wayfern") -> str:
        """Create a new browser profile"""
        try:
            response = requests.post(
                f"{self.api_url}/profiles",
                json={
                    "name": name,
                    "browser": browser,
                    "version": "latest"
                },
                timeout=self.timeout
            )
            response.raise_for_status()
            profile_id = response.json()["profile"]["id"]
            logger.info(f"✅ Created profile: {profile_id}")
            return profile_id
        except Exception as e:
            logger.error(f"❌ Failed to create profile: {e}")
            raise
    
    def launch_profile(self, profile_id: str) -> int:
        """Launch a profile and return CDP port"""
        try:
            response = requests.post(
                f"{self.api_url}/profiles/{profile_id}/run",
                timeout=self.timeout
            )
            response.raise_for_status()
            cdp_port = response.json()["remote_debugging_port"]
            logger.info(f"✅ Launched profile: {profile_id} on port {cdp_port}")
            
            # Wait for browser to be ready
            time.sleep(2)
            return cdp_port
        except Exception as e:
            logger.error(f"❌ Failed to launch profile: {e}")
            raise
    
    def stop_profile(self, profile_id: str):
        """Stop a running profile"""
        try:
            response = requests.post(
                f"{self.api_url}/profiles/{profile_id}/stop",
                timeout=self.timeout
            )
            response.raise_for_status()
            logger.info(f"✅ Stopped profile: {profile_id}")
        except Exception as e:
            logger.error(f"❌ Failed to stop profile: {e}")
    
    def delete_profile(self, profile_id: str):
        """Delete a profile"""
        try:
            response = requests.delete(
                f"{self.api_url}/profiles/{profile_id}",
                timeout=self.timeout
            )
            response.raise_for_status()
            logger.info(f"✅ Deleted profile: {profile_id}")
        except Exception as e:
            logger.error(f"❌ Failed to delete profile: {e}")