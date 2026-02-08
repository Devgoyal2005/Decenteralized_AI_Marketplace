from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import tensorflow as tf
from tensorflow import keras
import numpy as np
import cv2
from pathlib import Path
import json
from PIL import Image
import io
import os

# Suppress TensorFlow verbose output
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

app = FastAPI(title="DAMM - Brain Tumor Segmentation API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js default port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths
MODEL_PATH = Path("unet_brain_tumor_final.keras")  # Look in current directory
STATS_PATH = Path("model_stats.json")

# Global model variable
model = None


# Custom Dice Coefficient metric
def dice_coef(y_true, y_pred, smooth=1e-7):
    """Dice coefficient metric for binary segmentation"""
    y_true_f = tf.keras.backend.flatten(y_true)
    y_pred_f = tf.keras.backend.flatten(y_pred)
    intersection = tf.keras.backend.sum(y_true_f * y_pred_f)
    return (2. * intersection + smooth) / (tf.keras.backend.sum(y_true_f) + tf.keras.backend.sum(y_pred_f) + smooth)


@app.on_event("startup")
async def load_model():
    """Load the trained model on startup"""
    global model
    
    # Make MODEL_PATH absolute to avoid issues with working directory
    model_path_abs = Path(__file__).parent / "unet_brain_tumor_final.keras"
    
    print(f"\n{'='*80}")
    print(f"[DEBUG] Current working directory: {Path.cwd()}")
    print(f"[DEBUG] Script location: {Path(__file__).parent}")
    print(f"[DEBUG] Model path: {model_path_abs}")
    print(f"[DEBUG] Model exists: {model_path_abs.exists()}")
    print(f"{'='*80}\n")
    
    if not model_path_abs.exists():
        print(f"❌ Model file not found at {model_path_abs}")
        print("⚠️ API will run but predictions will fail")
        model = None
        return
    
    print(f"Loading model from: {model_path_abs}")
    
    try:
        # Suppress TensorFlow logging
        import logging
        logging.getLogger('tensorflow').setLevel(logging.FATAL)
        
        # Load model with custom objects
        model = keras.models.load_model(
            str(model_path_abs),
            custom_objects={'dice_coef': dice_coef}
        )
        
        print("\n" + "="*80)
        print("✅ Model loaded successfully!")
        print(f"📊 Model input shape: {model.input_shape}")
        print(f"📊 Model output shape: {model.output_shape}")
        print(f"📊 Model is not None: {model is not None}")
        print("="*80 + "\n")
        
    except Exception as e:
        print("\n" + "="*80)
        print(f"❌ EXCEPTION DURING MODEL LOADING:")
        print(f"Exception type: {type(e).__name__}")
        print(f"Exception message: {str(e)}")
        print("="*80)
        import traceback
        traceback.print_exc()
        print("="*80)
        print("⚠️ API will run but predictions will fail")
        print("="*80 + "\n")
        model = None

# Load model statistics
with open(STATS_PATH, 'r') as f:
    model_stats = json.load(f)


def preprocess_image(image: Image.Image, target_size=(128, 128)):
    """
    Preprocess the input image for model prediction
    Args:
        image: PIL Image object
        target_size: Target size for the model (height, width)
    Returns:
        Preprocessed numpy array
    """
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


@app.get("/")
async def root():
    return {"message": "DAMM - Decentralized AI Model Marketplace API", "status": "running"}


@app.get("/api/models")
async def get_models():
    """Get list of available models"""
    models = [
        {
            "id": "brain-tumor-unet",
            "name": "Brain Tumor Segmentation (U-Net)",
            "description": "U-Net deep learning model for brain tumor segmentation from MRI scans",
            "category": "Medical Imaging",
            "featured": True,
            "version": "1.0.0",
            "accuracy": 99.77,
            "stats": model_stats
        }
    ]
    return {"models": models}


@app.get("/api/models/{model_id}")
async def get_model_details(model_id: str):
    """Get detailed information about a specific model"""
    if model_id != "brain-tumor-unet":
        raise HTTPException(status_code=404, detail="Model not found")
    
    return {
        "id": "brain-tumor-unet",
        "name": "Brain Tumor Segmentation (U-Net)",
        "description": "Advanced U-Net architecture trained on BraTS 2020 dataset for precise brain tumor segmentation from FLAIR MRI scans",
        "category": "Medical Imaging",
        "featured": True,
        "version": "1.0.0",
        "author": "DAMM Research Team",
        "created_at": "2024-02-08",
        "stats": model_stats,
        "architecture": {
            "type": "U-Net 2D",
            "input_shape": [128, 128, 1],
            "output_shape": [128, 128, 1],
            "activation": "sigmoid",
            "loss": "binary_crossentropy",
            "optimizer": "Adam (lr=1e-4)"
        },
        "performance": {
            "train_accuracy": 99.81,
            "val_accuracy": 99.77,
            "dice_coefficient": 94.27,
            "epochs_trained": 15
        },
        "subscription": {
            "price_monthly": 49.99,
            "price_yearly": 499.99,
            "api_calls_limit": 10000
        }
    }


@app.post("/api/predict")
async def predict(file: UploadFile = File(...)):
    """Predict tumor segmentation from uploaded MRI image"""
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    try:
        # Read image file
        image_data = await file.read()
        image = Image.open(io.BytesIO(image_data))
        print(f"Received image: {image.size}, mode: {image.mode}")
        
        # Preprocess image
        processed_img = preprocess_image(image)
        print(f"Preprocessed image shape: {processed_img.shape}")
        
        # Make prediction
        prediction = model.predict(processed_img, verbose=0)
        print(f"Prediction shape: {prediction.shape}")
        
        # Extract mask
        mask = prediction[0, :, :, 0]  # (128, 128)
        
        # Threshold prediction
        binary_mask = (mask > 0.5).astype(np.float32)
        
        # Calculate tumor percentage
        tumor_pixels = int(np.sum(binary_mask))
        total_pixels = binary_mask.size
        tumor_percentage = (tumor_pixels / total_pixels) * 100
        
        # Convert mask to list for JSON serialization
        mask_list = binary_mask.tolist()
        
        return {
            "success": True,
            "prediction": {
                "mask": mask_list,
                "tumor_detected": tumor_pixels > 0,
                "tumor_percentage": round(tumor_percentage, 2),
                "confidence": round(float(np.max(mask)), 4),
                "image_size": [128, 128]
            }
        }
    
    except Exception as e:
        print(f"ERROR in prediction: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Prediction error: {str(e)}")


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "model_loaded": model is not None,
        "tensorflow_version": tf.__version__
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
