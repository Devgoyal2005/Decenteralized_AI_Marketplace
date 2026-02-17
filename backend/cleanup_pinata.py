"""
Script to clean up all pinned files from Pinata
"""
from ipfs_service import ipfs_service

print("="*80)
print("PINATA CLEANUP SCRIPT")
print("="*80)
print("\nThis will remove ALL pinned files from your Pinata account.")
confirm = input("Are you sure you want to continue? (yes/no): ")

if confirm.lower() == 'yes':
    print("\n🗑️ Starting cleanup...")
    result = ipfs_service.unpin_all()
    
    print(f"\n{'='*80}")
    print("CLEANUP COMPLETE")
    print(f"{'='*80}")
    print(f"✅ Successfully unpinned: {result['success']} files")
    print(f"❌ Failed to unpin: {len(result['failed'])} files")
    
    if result['failed']:
        print("\nFailed hashes:")
        for hash in result['failed']:
            print(f"  - {hash}")
else:
    print("\n❌ Cleanup cancelled")
