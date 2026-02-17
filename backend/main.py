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
import base64

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
        pinned_hashes = set()
        if PINATA_API_KEY:
            pinned_files = ipfs_service.list_pinned_files()
            pinned_hashes = {
                f.get('ipfs_pin_hash') for f in pinned_files if f.get('ipfs_pin_hash')
            }
            # Only include models still pinned on Pinata
            if pinned_hashes:
                models_list = [
                    m for m in models_list if m.get('ipfs_hash') in pinned_hashes
                ]
            else:
                models_list = []
        
        # Add gateway URLs for each model
        for model_info in models_list:
            if model_info.get('ipfs_hash'):
                model_info['gateway_url'] = f"{IPFS_GATEWAY}{model_info['ipfs_hash']}"
                model_info['ipfs_url'] = f"ipfs://{model_info['ipfs_hash']}"
        
        return {"models": models_list}
    
    except Exception as e:
        print(f"Error loading models: {str(e)}")
        return {"models": []}


@app.get("/api/models/{model_id}")
async def get_model_details(model_id: str):
    """Get detailed information about a specific model"""
    model_info = model_manager.get_model_info(model_id)
    
    if not model_info:
        raise HTTPException(status_code=404, detail="Model not found")
    
    # Verify model is still pinned on Pinata
    if model_info.get('ipfs_hash') and PINATA_API_KEY:
        pinned_files = ipfs_service.list_pinned_files()
        pinned_hashes = {
            f.get('ipfs_pin_hash') for f in pinned_files if f.get('ipfs_pin_hash')
        }
        if model_info.get('ipfs_hash') not in pinned_hashes:
            raise HTTPException(status_code=404, detail="Model not found on Pinata")

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
    price_per_hour: Optional[float] = Form(None),
    payment_currency: Optional[str] = Form("ETH"),
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
                "per_hour": price_per_hour,
                "currency": payment_currency
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


@app.put("/api/models/{model_id}")
async def update_model(
    model_id: str,
    wallet_address: str = Form(...),
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    price_per_hour: Optional[float] = Form(None),
    payment_currency: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    accuracy: Optional[float] = Form(None)
):
    """Update model metadata (only by owner)"""
    
    # Get model info
    model_info = model_manager.get_model_info(model_id)
    if not model_info:
        raise HTTPException(status_code=404, detail="Model not found")
    
    # Verify ownership
    if model_info.get('creator', '').lower() != wallet_address.lower():
        raise HTTPException(
            status_code=403,
            detail="Only the model owner can edit this model"
        )
    
    # Update fields
    if name:
        model_info['name'] = name
    if description:
        model_info['description'] = description
    if category:
        model_info['category'] = category
    if price_per_hour is not None:
        if 'pricing' not in model_info:
            model_info['pricing'] = {}
        model_info['pricing']['per_hour'] = price_per_hour
    if payment_currency:
        if 'pricing' not in model_info:
            model_info['pricing'] = {}
        model_info['pricing']['currency'] = payment_currency
    if tags:
        model_info['tags'] = [tag.strip() for tag in tags.split(',')]
    if accuracy is not None:
        if 'performance' not in model_info:
            model_info['performance'] = {}
        model_info['performance']['accuracy'] = accuracy
    
    # Update in registry
    model_manager.update_model(model_id, model_info)
    
    return {
        "success": True,
        "message": "Model updated successfully",
        "model": model_info
    }


@app.delete("/api/models/{model_id}")
async def delete_model(model_id: str, wallet_address: str = Form(...)):
    """Delete model (only by owner)"""
    
    # Get model info
    model_info = model_manager.get_model_info(model_id)
    if not model_info:
        raise HTTPException(status_code=404, detail="Model not found")
    
    # Verify ownership
    if model_info.get('creator', '').lower() != wallet_address.lower():
        raise HTTPException(
            status_code=403,
            detail="Only the model owner can delete this model"
        )
    
    # Unpin from Pinata
    ipfs_hash = model_info.get('ipfs_hash')
    if ipfs_hash:
        try:
            unpin_success = ipfs_service.unpin_file(ipfs_hash)
            if unpin_success:
                print(f"✅ Unpinned {ipfs_hash} from Pinata")
            else:
                print(f"⚠️ Failed to unpin {ipfs_hash} from Pinata")
        except Exception as e:
            print(f"⚠️ Error unpinning: {str(e)}")
    
    # Remove from registry
    model_manager.delete_model(model_id)
    
    # Remove from cache if exists
    cache_dir = Path("model_cache")
    cache_file = cache_dir / f"{model_id}.{model_info.get('model_type', 'keras')}"
    if cache_file.exists():
        cache_file.unlink()
        print(f"🗑️ Removed cached model: {cache_file}")
    
    return {
        "success": True,
        "message": f"Model '{model_info.get('name')}' deleted successfully"
    }


@app.post("/api/models/{model_id}/purchase")
async def purchase_model(model_id: str, wallet_address: str = Form(...)):
    """
    Purchase a model - downloads it to local cache for use
    For now, this is free. Payment integration will be added later.
    """
    
    model_info = model_manager.get_model_info(model_id)
    if not model_info:
        raise HTTPException(status_code=404, detail="Model not found")
    
    # Download model to cache
    try:
        print(f"📥 Purchasing model {model_id} for {wallet_address}...")
        
        # This will download and cache the model
        cached_path = model_manager.download_model(model_id)
        
        if not cached_path:
            raise HTTPException(status_code=500, detail="Failed to download model")
        
        # Increment download counter
        model_info['downloads'] = model_info.get('downloads', 0) + 1
        model_manager.update_model(model_id, model_info)
        
        print(f"✅ Model purchased and cached: {cached_path}")
        
        return {
            "success": True,
            "message": f"Model '{model_info.get('name')}' purchased successfully",
            "model_id": model_id,
            "cached": True,
            "pricing": model_info.get('pricing', {})
        }
    
    except Exception as e:
        print(f"❌ Purchase error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Purchase failed: {str(e)}")


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
        
        # Create segmented image for visualization
        # Convert binary mask to image (0-255 range)
        mask_img = (binary_mask * 255).astype(np.uint8)
        
        # Convert to PIL Image
        mask_pil = Image.fromarray(mask_img, mode='L')
        
        # Convert to base64 for frontend display
        buffered = io.BytesIO()
        mask_pil.save(buffered, format="PNG")
        mask_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
        
        # Also create overlay image (original + mask)
        # Resize original to 128x128 if needed
        original_resized = image.resize((128, 128), Image.LANCZOS)
        if original_resized.mode != 'RGB':
            original_resized = original_resized.convert('RGB')
        
        original_array = np.array(original_resized)
        
        # Create red overlay for tumor regions
        overlay = original_array.copy()
        overlay[:, :, 0] = np.where(binary_mask > 0.5, 255, overlay[:, :, 0])  # Red channel
        overlay[:, :, 1] = np.where(binary_mask > 0.5, 0, overlay[:, :, 1])    # Green channel
        overlay[:, :, 2] = np.where(binary_mask > 0.5, 0, overlay[:, :, 2])    # Blue channel
        
        # Blend original and overlay
        alpha = 0.4
        blended = cv2.addWeighted(original_array, 1-alpha, overlay, alpha, 0)
        
        # Convert to PIL and base64
        blended_pil = Image.fromarray(blended.astype(np.uint8))
        buffered2 = io.BytesIO()
        blended_pil.save(buffered2, format="PNG")
        overlay_base64 = base64.b64encode(buffered2.getvalue()).decode('utf-8')
        
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
                "mask_image": f"data:image/png;base64,{mask_base64}",
                "overlay_image": f"data:image/png;base64,{overlay_base64}",
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


@app.post("/api/admin/cleanup-pinata")
async def cleanup_pinata(confirm: bool = Form(False)):
    """Admin endpoint to remove all pinned files from Pinata"""
    if not confirm:
        raise HTTPException(status_code=400, detail="Must confirm cleanup with confirm=true")
    
    try:
        result = ipfs_service.unpin_all()
        return {
            "success": True,
            "message": f"Cleaned up Pinata storage",
            "unpinned_count": result['success'],
            "failed_count": len(result['failed']),
            "failed_hashes": result['failed']
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")


