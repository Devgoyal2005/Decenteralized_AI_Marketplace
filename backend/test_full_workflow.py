"""
Test the full IPFS workflow:
1. Check if model is in registry
2. Test downloading from IPFS
3. Test loading the model
4. Test making a prediction
"""
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from model_manager import ModelManager
from ipfs_service import IPFSService
import numpy as np
from PIL import Image

print("="*80)
print("TESTING FULL IPFS WORKFLOW")
print("="*80)

# Initialize services
ipfs_service = IPFSService()
model_manager = ModelManager(ipfs_service)

# Step 1: List models in registry
print("\n📋 Step 1: Listing models in registry...")
models = model_manager.list_models()
print(f"Found {len(models)} model(s) in registry:")
for model in models:
    print(f"  - {model['id']}: {model['name']}")
    print(f"    IPFS Hash: {model.get('ipfs_hash', 'Not uploaded')}")
    print(f"    Category: {model.get('category', 'N/A')}")

if not models:
    print("\n❌ No models in registry!")
    print("Run 'python upload_to_ipfs.py' first to upload the brain tumor model")
    sys.exit(1)

# Step 2: Test downloading first model
model_id = models[0]['id']
print(f"\n📥 Step 2: Testing download for model: {model_id}")

if model_manager.is_model_cached(model_id):
    print(f"✅ Model already cached at: {model_manager.get_cached_model_path(model_id)}")
else:
    print(f"Model not in cache, will download from IPFS...")
    success = model_manager.download_model(model_id)
    if not success:
        print("❌ Download failed!")
        sys.exit(1)

# Step 3: Test loading the model
print(f"\n🔄 Step 3: Loading model {model_id}...")

# Define custom metric for brain tumor model
import tensorflow as tf
def dice_coef(y_true, y_pred, smooth=1e-7):
    y_true_f = tf.keras.backend.flatten(y_true)
    y_pred_f = tf.keras.backend.flatten(y_pred)
    intersection = tf.keras.backend.sum(y_true_f * y_pred_f)
    return (2. * intersection + smooth) / (tf.keras.backend.sum(y_true_f) + tf.keras.backend.sum(y_pred_f) + smooth)

loaded_model = model_manager.load_model(
    model_id,
    custom_objects={'dice_coef': dice_coef}
)

if loaded_model is None:
    print("❌ Model loading failed!")
    sys.exit(1)

print(f"✅ Model loaded successfully!")
print(f"   Input shape: {loaded_model.input_shape}")
print(f"   Output shape: {loaded_model.output_shape}")

# Step 4: Test prediction
print(f"\n🧪 Step 4: Testing prediction...")

# Create a dummy input image (128x128 grayscale)
dummy_image = np.random.rand(1, 128, 128, 1).astype(np.float32)
print(f"Created dummy input: {dummy_image.shape}")

try:
    prediction = loaded_model.predict(dummy_image, verbose=0)
    print(f"✅ Prediction successful!")
    print(f"   Output shape: {prediction.shape}")
    print(f"   Output range: [{prediction.min():.4f}, {prediction.max():.4f}]")
    
    # Calculate tumor percentage (for demo)
    binary_mask = (prediction[0, :, :, 0] > 0.5).astype(np.float32)
    tumor_percentage = (np.sum(binary_mask) / binary_mask.size) * 100
    print(f"   Simulated tumor percentage: {tumor_percentage:.2f}%")
    
except Exception as e:
    print(f"❌ Prediction failed: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Step 5: Verify caching
print(f"\n💾 Step 5: Verifying caching...")
print(f"Model in memory cache: {model_id in model_manager.loaded_models}")
print(f"Model in disk cache: {model_manager.is_model_cached(model_id)}")
print(f"Cache path: {model_manager.get_cached_model_path(model_id)}")

print("\n" + "="*80)
print("✅ ALL TESTS PASSED!")
print("="*80)
print("\n🎉 Your IPFS integration is working perfectly!")
print("\nNext steps:")
print("1. Start backend: uvicorn main:app --reload")
print("2. Start frontend: cd frontend && npm run dev")
print("3. Test upload: http://localhost:3000/upload")
print("4. Test prediction: http://localhost:3000/models/brain-tumor-unet")
