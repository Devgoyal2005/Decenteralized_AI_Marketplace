"""
Test script for new IPFS marketplace features
"""
import requests
import json

BASE_URL = "http://localhost:8000"

def test_api():
    print("="*80)
    print("TESTING NEW API ENDPOINTS")
    print("="*80)
    
    # 1. List models
    print("\n1. Testing GET /api/models...")
    response = requests.get(f"{BASE_URL}/api/models")
    if response.status_code == 200:
        models = response.json()['models']
        print(f"✅ Found {len(models)} models")
        if models:
            print(f"   First model: {models[0].get('name')}")
            print(f"   Pricing: {models[0].get('pricing')}")
    else:
        print(f"❌ Failed: {response.status_code}")
    
    # 2. Test health
    print("\n2. Testing GET /api/health...")
    response = requests.get(f"{BASE_URL}/api/health")
    if response.status_code == 200:
        print(f"✅ Backend healthy: {response.json()}")
    else:
        print(f"❌ Failed: {response.status_code}")
    
    print("\n" + "="*80)
    print("API TEST COMPLETE")
    print("="*80)
    print("\n📝 To test edit/delete/purchase endpoints:")
    print("   1. Start backend: cd backend && uvicorn main:app --reload")
    print("   2. Start frontend: cd frontend && npm run dev")
    print("   3. Upload a model via UI")
    print("   4. Try edit/buy/delete buttons")

if __name__ == "__main__":
    try:
        test_api()
    except requests.exceptions.ConnectionError:
        print("\n❌ Backend not running!")
        print("   Start it with: cd backend && uvicorn main:app --reload")
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
