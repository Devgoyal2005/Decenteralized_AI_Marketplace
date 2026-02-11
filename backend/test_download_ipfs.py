"""
Test script to download and load a model from IPFS
"""
from model_manager import model_manager
import numpy as np
from PIL import Image
from pathlib import Path

def dice_coef(y_true, y_pred, smooth=1e-7):
    """Dice coefficient - needed for model loading"""
    import tensorflow as tf
    y_true_f = tf.keras.backend.flatten(y_true)
    y_pred_f = tf.keras.backend.flatten(y_pred)
    intersection = tf.keras.backend.sum(y_true_f * y_pred_f)
    return (2. * intersection + smooth) / (tf.keras.backend.sum(y_true_f) + tf.keras.backend.sum(y_pred_f) + smooth)

def main():
    print("="*80)
    print("TESTING IPFS MODEL DOWNLOAD AND LOADING")
    print("="*80)
    
    model_id = "brain-tumor-unet"
    
    # Get model info
    model_info = model_manager.get_model_info(model_id)
    
    if not model_info:
        print(f"❌ Model {model_id} not found in registry")
        return
    
    print(f"\n📋 Model Info:")
    print(f"   Name: {model_info['name']}")
    print(f"   IPFS Hash: {model_info.get('ipfs_hash', 'NOT SET')}")
    
    if not model_info.get('ipfs_hash'):
        print("\n❌ No IPFS hash set for this model!")
        print("Run: python upload_to_ipfs.py first")
        return
    
    # Load the model (will download from IPFS if needed)
    print(f"\n🔄 Loading model from IPFS...")
    model = model_manager.load_model(
        model_id,
        custom_objects={'dice_coef': dice_coef}
    )
    
    if model:
        print(f"\n✅ Model loaded successfully!")
        print(f"   Input shape: {model.input_shape}")
        print(f"   Output shape: {model.output_shape}")
        
        # Test with a dummy image
        print(f"\n🧪 Testing prediction with dummy image...")
        
        # Create dummy 128x128 grayscale image
        test_img = np.random.rand(1, 128, 128, 1).astype(np.float32)
        
        prediction = model.predict(test_img, verbose=0)
        
        print(f"✅ Prediction successful!")
        print(f"   Prediction shape: {prediction.shape}")
        print(f"   Value range: [{prediction.min():.3f}, {prediction.max():.3f}]")
        
        # Check cache
        cache_path = model_manager.get_cached_model_path(model_id)
        print(f"\n📁 Model cached at: {cache_path}")
        print(f"   Cache size: {cache_path.stat().st_size / (1024*1024):.2f} MB")
        
        print("\n" + "="*80)
        print("✅ ALL TESTS PASSED!")
        print("="*80)
    else:
        print("\n❌ Model loading failed!")

if __name__ == "__main__":
    main()
