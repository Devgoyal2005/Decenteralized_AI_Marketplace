"""Test the FastAPI backend /api/predict endpoint"""
import requests
from pathlib import Path

# API URL
API_URL = "http://localhost:8000"

def test_health():
    """Test health endpoint"""
    print("Testing /api/health...")
    response = requests.get(f"{API_URL}/api/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    return response.json().get("model_loaded", False)

def test_predict(image_path):
    """Test predict endpoint"""
    print(f"\nTesting /api/predict with {image_path.name}...")
    
    with open(image_path, 'rb') as f:
        files = {'file': (image_path.name, f, 'image/png')}
        response = requests.post(f"{API_URL}/api/predict", files=files)
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print("✅ Prediction successful!")
        print(f"Tumor detected: {result['prediction']['tumor_detected']}")
        print(f"Tumor percentage: {result['prediction']['tumor_percentage']}%")
        print(f"Confidence: {result['prediction']['confidence']}")
    else:
        print(f"❌ Error: {response.text}")
    
    return response.status_code == 200

def main():
    print("=" * 80)
    print("TESTING FASTAPI BACKEND")
    print("=" * 80)
    
    # Test health
    model_loaded = test_health()
    
    if not model_loaded:
        print("\n❌ Model not loaded! Check backend logs.")
        return
    
    # Find test images
    test_images_dir = Path(__file__).parent.parent / "Test_images"
    image_files = list(test_images_dir.glob("*.png"))
    
    if not image_files:
        print("\n❌ No test images found!")
        return
    
    # Test prediction with first image
    success = test_predict(image_files[0])
    
    if success:
        print("\n" + "=" * 80)
        print("✅ ALL API TESTS PASSED!")
        print("=" * 80)
    else:
        print("\n" + "=" * 80)
        print("❌ API TESTS FAILED!")
        print("=" * 80)

if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to backend. Is it running on http://localhost:8000?")
