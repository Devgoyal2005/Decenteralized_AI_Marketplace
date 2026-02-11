"""
IPFS Service - Handles upload/download from Pinata
"""
import os
import requests
from pathlib import Path
from typing import Optional, Dict
from dotenv import load_dotenv

load_dotenv()

PINATA_API_KEY = os.getenv("PINATA_API_KEY")
PINATA_SECRET_KEY = os.getenv("PINATA_SECRET_KEY")
IPFS_GATEWAY = os.getenv("IPFS_GATEWAY", "https://gateway.pinata.cloud/ipfs/")

PINATA_UPLOAD_URL = "https://api.pinata.cloud/pinning/pinFileToIPFS"
PINATA_PIN_JSON_URL = "https://api.pinata.cloud/pinning/pinJSONToIPFS"


class IPFSService:
    """Service for interacting with IPFS via Pinata"""
    
    def __init__(self):
        if not PINATA_API_KEY or not PINATA_SECRET_KEY:
            print("⚠️ WARNING: Pinata credentials not set in .env file")
            print("   IPFS upload/download features will not work")
        
        self.headers = {
            "pinata_api_key": PINATA_API_KEY,
            "pinata_secret_api_key": PINATA_SECRET_KEY
        }
    
    def upload_file(self, file_path: str, metadata: Optional[Dict] = None) -> Optional[str]:
        """
        Upload a file to IPFS via Pinata
        
        Args:
            file_path: Path to the file to upload
            metadata: Optional metadata to attach
        
        Returns:
            IPFS hash (CID) or None if failed
        """
        if not PINATA_API_KEY or not PINATA_SECRET_KEY:
            print("❌ Cannot upload: Pinata credentials not configured")
            return None
        
        try:
            file_path = Path(file_path)
            
            if not file_path.exists():
                print(f"❌ File not found: {file_path}")
                return None
            
            # Prepare the file
            with open(file_path, 'rb') as file:
                files = {
                    'file': (file_path.name, file)
                }
                
                # Prepare data payload
                # Note: For file uploads, Pinata doesn't accept these as form data
                # We'll just send the file without extra metadata to avoid JSON error
                
                print(f"📤 Uploading {file_path.name} to IPFS...")
                response = requests.post(
                    PINATA_UPLOAD_URL,
                    files=files,
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    result = response.json()
                    ipfs_hash = result['IpfsHash']
                    print(f"✅ Uploaded successfully! IPFS Hash: {ipfs_hash}")
                    print(f"🔗 Gateway URL: {IPFS_GATEWAY}{ipfs_hash}")
                    return ipfs_hash
                else:
                    print(f"❌ Upload failed: {response.status_code}")
                    print(f"Response: {response.text}")
                    return None
                    
        except Exception as e:
            print(f"❌ Error uploading to IPFS: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def upload_json(self, data: Dict, name: str = "metadata") -> Optional[str]:
        """
        Upload JSON data to IPFS
        
        Args:
            data: Dictionary to upload
            name: Name for the pinned content
        
        Returns:
            IPFS hash or None if failed
        """
        if not PINATA_API_KEY or not PINATA_SECRET_KEY:
            print("❌ Cannot upload: Pinata credentials not configured")
            return None
        
        try:
            payload = {
                "pinataContent": data,
                "pinataMetadata": {
                    "name": name
                },
                "pinataOptions": {
                    "cidVersion": 1
                }
            }
            
            print(f"📤 Uploading JSON metadata to IPFS...")
            response = requests.post(
                PINATA_PIN_JSON_URL,
                json=payload,
                headers=self.headers
            )
            
            if response.status_code == 200:
                result = response.json()
                ipfs_hash = result['IpfsHash']
                print(f"✅ JSON uploaded! IPFS Hash: {ipfs_hash}")
                return ipfs_hash
            else:
                print(f"❌ JSON upload failed: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Error uploading JSON: {str(e)}")
            return None
    
    def download_file(self, ipfs_hash: str, save_path: str) -> bool:
        """
        Download a file from IPFS
        
        Args:
            ipfs_hash: IPFS hash (CID) of the file
            save_path: Where to save the downloaded file
        
        Returns:
            True if successful, False otherwise
        """
        try:
            save_path = Path(save_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Try multiple gateways for redundancy
            gateways = [
                f"https://gateway.pinata.cloud/ipfs/{ipfs_hash}",
                f"https://ipfs.io/ipfs/{ipfs_hash}",
                f"https://cloudflare-ipfs.com/ipfs/{ipfs_hash}"
            ]
            
            print(f"📥 Downloading from IPFS: {ipfs_hash}")
            
            for gateway_url in gateways:
                try:
                    print(f"   Trying gateway: {gateway_url}")
                    response = requests.get(gateway_url, timeout=60, stream=True)
                    
                    if response.status_code == 200:
                        total_size = int(response.headers.get('content-length', 0))
                        
                        with open(save_path, 'wb') as f:
                            downloaded = 0
                            for chunk in response.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                                    downloaded += len(chunk)
                                    if total_size > 0:
                                        percent = (downloaded / total_size) * 100
                                        print(f"\r   Progress: {percent:.1f}%", end='', flush=True)
                        
                        print(f"\n✅ Downloaded successfully to: {save_path}")
                        return True
                        
                except Exception as e:
                    print(f"\n   ⚠️ Gateway failed: {str(e)}")
                    continue
            
            print(f"❌ All gateways failed for {ipfs_hash}")
            return False
            
        except Exception as e:
            print(f"❌ Error downloading from IPFS: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def get_gateway_url(self, ipfs_hash: str) -> str:
        """Get the gateway URL for an IPFS hash"""
        return f"{IPFS_GATEWAY}{ipfs_hash}"


# Global instance
ipfs_service = IPFSService()
