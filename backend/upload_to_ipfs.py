"""
Test script to upload the brain tumor model to IPFS
"""
from pathlib import Path
import json
from ipfs_service import ipfs_service
from model_manager import model_manager

# Path to the model file
MODEL_FILE = Path(__file__).parent / "unet_brain_tumor_final.keras"

def main():
    print("="*80)
    print("UPLOADING BRAIN TUMOR MODEL TO IPFS")
    print("="*80)
    
    # Check if model exists
    if not MODEL_FILE.exists():
        print(f"❌ Model file not found: {MODEL_FILE}")
        return
    
    print(f"\n📁 Model file: {MODEL_FILE}")
    print(f"📊 File size: {MODEL_FILE.stat().st_size / (1024*1024):.2f} MB")
    
    # Upload to IPFS
    metadata = {
        "name": "Brain Tumor Segmentation U-Net",
        "description": "U-Net model trained on BraTS 2020",
        "model_type": "keras"
    }
    
    ipfs_hash = ipfs_service.upload_file(str(MODEL_FILE), metadata)
    
    if ipfs_hash:
        print(f"\n✅ Model uploaded successfully!")
        print(f"📦 IPFS Hash: {ipfs_hash}")
        print(f"🔗 Gateway URL: {ipfs_service.get_gateway_url(ipfs_hash)}")
        
        # Update the registry
        print(f"\n📝 Updating registry...")
        
        # Get the current brain tumor model from registry
        model_info = model_manager.get_model_info("brain-tumor-unet")
        
        if model_info:
            model_info['ipfs_hash'] = ipfs_hash
            
            # Save the updated registry
            model_manager._save_registry(model_manager.registry)
            
            print(f"✅ Registry updated with IPFS hash")
            
            # Save the hash to a separate file for easy access
            hash_file = Path(__file__).parent / "ipfs_hash.txt"
            with open(hash_file, 'w') as f:
                f.write(ipfs_hash)
            
            print(f"✅ IPFS hash saved to {hash_file}")
            
            print("\n" + "="*80)
            print("NEXT STEPS:")
            print("="*80)
            print("1. Copy your IPFS hash (above)")
            print("2. Verify it works: Visit the Gateway URL")
            print("3. Test download: python test_download_ipfs.py")
            print("="*80)
        else:
            print("❌ Model not found in registry")
    else:
        print("\n❌ Upload failed!")
        print("Make sure you have set PINATA_API_KEY and PINATA_SECRET_KEY in .env file")

if __name__ == "__main__":
    main()
