"""Test script to debug model prediction issues"""
import sys
from pathlib import Path
import tensorflow as tf
from tensorflow import keras
import numpy as np
from PIL import Image

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Model path
MODEL_PATH = Path(__file__).parent.parent / "unet_brain_tumor_final.keras"

def dice_coef(y_true, y_pred, smooth=1e-7):
    """Dice coefficient metric for binary segmentation"""
    y_true_f = tf.keras.backend.flatten(y_true)
    y_pred_f = tf.keras.backend.flatten(y_pred)
    intersection = tf.keras.backend.sum(y_true_f * y_pred_f)
    return (2. * intersection + smooth) / (tf.keras.backend.sum(y_true_f) + tf.keras.backend.sum(y_pred_f) + smooth)

def preprocess_image(image: Image.Image, target_size=(128, 128)):
    """Preprocess the input image for model prediction"""
    # Convert to grayscale if needed
    if image.mode != 'L':
        image = image.convert('L')
    
    # Resize to model input size
    image = image.resize(target_size, Image.LANCZOS)
    
    # Convert to numpy array
    img_array = np.array(image, dtype=np.float32)
    
    # Normalize to [0, 1]
    if img_array.max() > 1.0:
        img_array = img_array / 255.0
    
    # Add channel dimension and batch dimension
    img_array = np.expand_dims(img_array, axis=-1)  # (128, 128, 1)
    img_array = np.expand_dims(img_array, axis=0)   # (1, 128, 128, 1)
    
    return img_array

def main():
    print("=" * 80)
    print("TESTING MODEL PREDICTION")
    print("=" * 80)
    
    # Load model
    print(f"\n1. Loading model from: {MODEL_PATH}")
    print(f"   Model exists: {MODEL_PATH.exists()}")
    
    if not MODEL_PATH.exists():
        print("❌ Model not found!")
        return
    
    try:
        # Suppress verbose output
        import os
        os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
        import logging
        logging.getLogger('tensorflow').setLevel(logging.ERROR)
        
        print("   Loading with custom objects...")
        model = keras.models.load_model(
            str(MODEL_PATH),
            custom_objects={'dice_coef': dice_coef}
        )
        print("✅ Model loaded successfully!")
        print(f"   Input shape: {model.input_shape}")
        print(f"   Output shape: {model.output_shape}")
    except Exception as e:
        print(f"❌ Error loading model: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Find test images
    test_images_dir = Path(__file__).parent.parent / "Test_images"
    print(f"\n2. Looking for test images in: {test_images_dir}")
    
    if not test_images_dir.exists():
        print("❌ Test_images folder not found!")
        return
    
    # Get all image files
    image_files = list(test_images_dir.glob("*.png")) + list(test_images_dir.glob("*.jpg")) + list(test_images_dir.glob("*.jpeg"))
    print(f"   Found {len(image_files)} images")
    
    if not image_files:
        print("❌ No test images found!")
        return
    
    # Test with first image
    test_image_path = image_files[0]
    print(f"\n3. Testing with: {test_image_path.name}")
    
    try:
        # Load and preprocess image
        image = Image.open(test_image_path)
        print(f"   Original image: {image.mode}, {image.size}")
        
        img_array = preprocess_image(image)
        print(f"   Preprocessed shape: {img_array.shape}")
        print(f"   Value range: [{img_array.min():.3f}, {img_array.max():.3f}]")
        
        # Make prediction
        print("\n4. Running prediction...")
        prediction = model.predict(img_array, verbose=0)
        print(f"✅ Prediction successful!")
        print(f"   Output shape: {prediction.shape}")
        print(f"   Value range: [{prediction.min():.3f}, {prediction.max():.3f}]")
        
        # Calculate tumor percentage
        mask = prediction[0, :, :, 0]
        tumor_pixels = np.sum(mask > 0.5)
        total_pixels = mask.shape[0] * mask.shape[1]
        tumor_percentage = (tumor_pixels / total_pixels) * 100
        
        print(f"\n5. Results:")
        print(f"   Tumor pixels: {tumor_pixels}/{total_pixels}")
        print(f"   Tumor percentage: {tumor_percentage:.2f}%")
        
        print("\n" + "=" * 80)
        print("✅ ALL TESTS PASSED!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ Prediction failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
