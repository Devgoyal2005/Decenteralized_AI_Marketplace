from fastapi import FastAPI, File, UploadFile, HTTPException, Form
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
import tempfile
import uuid
from typing import Optional
from datetime import datetime

# Import our IPFS modules
from ipfs_service import IPFSService, IPFS_GATEWAY, PINATA_API_KEY
from model_manager import ModelManager

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

# Initialize IPFS service and Model Manager
ipfs_service = IPFSService()
model_manager = ModelManager(ipfs_service)

# Global model variable (kept for backwards compatibility, but we'll use model_manager now)
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
    """Load the default brain tumor model on startup"""
    global model
    
    print(f"\n{'='*80}")
    print("🚀 Starting DAMM Backend with IPFS Support")
    print(f"{'='*80}\n")
    
    # Try to load the brain tumor model (for backwards compatibility)
    model_path_abs = Path(__file__).parent / "unet_brain_tumor_final.keras"
    
    if model_path_abs.exists():
        print(f"Loading default brain tumor model from: {model_path_abs}")
        
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
            print("✅ Default model loaded successfully!")
            print(f"📊 Model input shape: {model.input_shape}")
            print(f"📊 Model output shape: {model.output_shape}")
            print("="*80 + "\n")
            
        except Exception as e:
            print(f"⚠️ Could not load default model: {str(e)}")
            model = None
    else:
        print("ℹ️ No default model found. Models will be loaded dynamically from IPFS.")
        model = None
    
    # Print IPFS status
    print(f"\n{'='*80}")
    print("📡 IPFS Service Status:")
    print(f"   Pinata configured: {PINATA_API_KEY is not None}")
    print(f"   Models in registry: {len(model_manager.list_models())}")
    print(f"{'='*80}\n")

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
    """Get list of available models from registry"""
    try:
        models_list = model_manager.list_models()
        
        # Add gateway URLs for each model
        for model_info in models_list:
            if model_info.get('ipfs_hash'):
                model_info['gateway_url'] = f"{IPFS_GATEWAY}{model_info['ipfs_hash']}"
                model_info['ipfs_url'] = f"ipfs://{model_info['ipfs_hash']}"
        
        return {"models": models_list}
    
    except Exception as e:
        print(f"Error loading models: {str(e)}")
        # Fallback to hardcoded model if registry fails
        return {"models": [{
            "id": "brain-tumor-unet",
            "name": "Brain Tumor Segmentation (U-Net)",
            "description": "U-Net deep learning model for brain tumor segmentation from MRI scans",
            "category": "Medical Imaging",
            "featured": True,
            "version": "1.0.0",
            "accuracy": 99.77,
            "stats": model_stats
        }]}


@app.get("/api/models/{model_id}")
async def get_model_details(model_id: str):
    """Get detailed information about a specific model"""
    model_info = model_manager.get_model_info(model_id)
    
    if not model_info:
        raise HTTPException(status_code=404, detail="Model not found")
    
    # Add gateway URLs
    if model_info.get('ipfs_hash'):
        model_info['gateway_url'] = f"{IPFS_GATEWAY}{model_info['ipfs_hash']}"
        model_info['ipfs_url'] = f"ipfs://{model_info['ipfs_hash']}"
    
    return model_info


@app.post("/api/models/upload")
async def upload_model(
    file: UploadFile = File(...),
    name: str = Form(...),
    description: str = Form(...),
    creator: str = Form(...),
    model_type: str = Form("keras"),
    category: str = Form("General"),
    price_monthly: Optional[float] = Form(None),
    price_yearly: Optional[float] = Form(None),
    input_shape: Optional[str] = Form(None),
    output_shape: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    accuracy: Optional[float] = Form(None)
):
    """Upload a new model to IPFS and add to registry"""
    
    # Validate file extension
    allowed_extensions = ['.keras', '.h5', '.pkl', '.pt', '.pth']
    file_ext = Path(file.filename).suffix.lower()
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"
        )
    
    try:
        # Save temporary file
        temp_dir = Path(tempfile.gettempdir())
        temp_file = temp_dir / f"upload_{uuid.uuid4()}{file_ext}"
        
        # Write uploaded file to disk
        content = await file.read()
        with open(temp_file, 'wb') as f:
            f.write(content)
        
        print(f"📤 Uploading {file.filename} ({len(content) / 1024 / 1024:.2f} MB) to IPFS...")
        
        # Upload to IPFS
        ipfs_hash = ipfs_service.upload_file(str(temp_file), file.filename)
        
        if not ipfs_hash:
            raise HTTPException(status_code=500, detail="Failed to upload to IPFS")
        
        print(f"✅ Uploaded to IPFS: {ipfs_hash}")
        
        # Generate model ID
        model_id = f"{name.lower().replace(' ', '-')}-{str(uuid.uuid4())[:8]}"
        
        # Prepare metadata
        metadata = {
            "id": model_id,
            "name": name,
            "description": description,
            "creator": creator,
            "ipfs_hash": ipfs_hash,
            "model_type": model_type,
            "category": category,
            "uploaded_at": datetime.now().isoformat(),
            "file_size_mb": round(len(content) / 1024 / 1024, 2),
            "downloads": 0,
            "predictions": 0,
            "active": True,
            "pricing": {
                "monthly": price_monthly,
                "yearly": price_yearly
            }
        }
        
        # Parse and add input/output shapes if provided
        if input_shape:
            try:
                metadata["input_shape"] = json.loads(f"[{input_shape}]")
            except:
                metadata["input_shape"] = input_shape
        
        if output_shape:
            try:
                metadata["output_shape"] = json.loads(f"[{output_shape}]")
            except:
                metadata["output_shape"] = output_shape
        
        # Add tags if provided
        if tags:
            metadata["tags"] = [tag.strip() for tag in tags.split(',')]
        
        # Add performance metrics if provided
        if accuracy:
            metadata["performance"] = {
                "accuracy": accuracy
            }
        
        # Add to registry
        model_manager.add_model(metadata)
        
        # Clean up temp file
        temp_file.unlink()
        
        return {
            "success": True,
            "model_id": model_id,
            "ipfs_hash": ipfs_hash,
            "gateway_url": f"{IPFS_GATEWAY}{ipfs_hash}",
            "message": f"Model '{name}' uploaded successfully"
        }
    
    except Exception as e:
        # Clean up on error
        if 'temp_file' in locals() and temp_file.exists():
            temp_file.unlink()
        
        print(f"❌ Upload error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.post("/api/predict")
async def predict(
    file: UploadFile = File(...),
    model_id: Optional[str] = Form("brain-tumor-unet")
):
    """Predict tumor segmentation from uploaded MRI image using specified model"""
    
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    try:
        # Load the specified model (will download from IPFS if needed)
        print(f"🔄 Loading model: {model_id}")
        
        loaded_model = model_manager.load_model(
            model_id,
            custom_objects={'dice_coef': dice_coef}
        )
        
        if loaded_model is None:
            # Fallback to global model if available
            if model is not None:
                loaded_model = model
                print("ℹ️ Using default loaded model")
            else:
                raise HTTPException(
                    status_code=503,
                    detail=f"Model '{model_id}' not found and no default model loaded"
                )
        
        print(f"✅ Model loaded: {model_id}")
        
        # Read image file
        image_data = await file.read()
        image = Image.open(io.BytesIO(image_data))
        print(f"Received image: {image.size}, mode: {image.mode}")
        
        # Preprocess image
        processed_img = preprocess_image(image)
        print(f"Preprocessed image shape: {processed_img.shape}")
        
        # Make prediction
        prediction = loaded_model.predict(processed_img, verbose=0)
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
        
        # Determine where model was loaded from
        model_source = "memory"
        if model_manager.is_model_cached(model_id):
            model_source = "cache"
        elif model_manager.get_model_info(model_id).get('ipfs_hash'):
            model_source = "ipfs"
        
        return {
            "success": True,
            "model_id": model_id,
            "model_source": model_source,
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
