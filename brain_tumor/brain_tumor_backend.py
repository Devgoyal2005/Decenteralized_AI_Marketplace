from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import tensorflow as tf
from tensorflow import keras
import numpy as np
from PIL import Image
import io
import base64
from pathlib import Path
import cv2

# Initialize FastAPI app
app = FastAPI(
    title="Brain Tumor Segmentation API",
    description="API for brain tumor segmentation using U-Net model",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the Stats folder so static HTML reports can be served
stats_path = Path("Stats")
if stats_path.exists():
    app.mount("/stats", StaticFiles(directory=str(stats_path)), name="stats")
else:
    print("⚠️ Stats folder not found; /stats endpoint will not be available until the folder exists")

# Model path
MODEL_PATH = "unet_brain_tumor_final.keras"

# Global model variable
model = None

# Custom Dice Coefficient metric (needed for model loading)
def dice_coef(y_true, y_pred, smooth=1e-7):
    """
    Dice coefficient metric for binary segmentation
    """
    y_true_f = tf.keras.backend.flatten(y_true)
    y_pred_f = tf.keras.backend.flatten(y_pred)
    intersection = tf.keras.backend.sum(y_true_f * y_pred_f)
    return (2. * intersection + smooth) / (tf.keras.backend.sum(y_true_f) + tf.keras.backend.sum(y_pred_f) + smooth)

@app.on_event("startup")
async def load_model():
    """Load the trained model on startup"""
    global model
    try:
        model_path = Path(MODEL_PATH)
        if not model_path.exists():
            print(f"❌ Model file not found at {MODEL_PATH}")
            print("⚠️ API will run but predictions will fail until model is available")
            return
        
        # Load model with custom objects
        model = keras.models.load_model(
            MODEL_PATH,
            custom_objects={'dice_coef': dice_coef}
        )
        print("✅ Model loaded successfully!")
        print(f"📊 Model input shape: {model.input_shape}")
        print(f"📊 Model output shape: {model.output_shape}")
    except Exception as e:
        print(f"❌ Error loading model: {str(e)}")
        print("⚠️ API will run but predictions will fail")

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

def create_segmentation_overlay(original_img: np.ndarray, mask: np.ndarray):
    """
    Create an overlay visualization of the segmentation mask on the original image
    Args:
        original_img: Original grayscale image (128, 128)
        mask: Binary segmentation mask (128, 128)
    Returns:
        RGB image with overlay
    """
    # Normalize original image to [0, 255]
    if original_img.max() <= 1.0:
        original_img = (original_img * 255).astype(np.uint8)
    
    # Create RGB version of original image
    rgb_img = cv2.cvtColor(original_img, cv2.COLOR_GRAY2RGB)
    
    # Create colored mask (red for tumor)
    colored_mask = np.zeros_like(rgb_img)
    colored_mask[:, :, 0] = (mask > 0.5).astype(np.uint8) * 255  # Red channel
    
    # Blend original and mask
    overlay = cv2.addWeighted(rgb_img, 0.7, colored_mask, 0.3, 0)
    
    # Add contours for better visibility
    mask_binary = (mask > 0.5).astype(np.uint8)
    contours, _ = cv2.findContours(mask_binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(overlay, contours, -1, (0, 255, 0), 2)  # Green contours
    
    return overlay

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Brain Tumor Segmentation API",
        "version": "1.0.0",
        "model_loaded": model is not None,
        "endpoints": {
            "POST /predict": "Predict tumor segmentation from uploaded image",
            "GET /health": "Check API health status",
            "GET /model-info": "Get model information"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "model_loaded": model is not None,
        "model_path": MODEL_PATH
    }

@app.get("/model-info")
async def model_info():
    """Get model information"""
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    return {
        "model_name": "U-Net Brain Tumor Segmentation",
        "input_shape": str(model.input_shape),
        "output_shape": str(model.output_shape),
        "total_params": model.count_params(),
        "architecture": "U-Net 2D"
    }

@app.post("/predict")
async def predict_tumor(file: UploadFile = File(...)):
    """
    Predict tumor segmentation from uploaded MRI image
    Args:
        file: Uploaded image file
    Returns:
        JSON with segmentation results
    """
    if model is None:
        raise HTTPException(
            status_code=503,
            detail="Model not loaded. Please ensure the model file exists at the specified path."
        )
    
    try:
        # Validate file type
        if not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        # Read image file
        image_data = await file.read()
        image = Image.open(io.BytesIO(image_data))
        
        # Store original size
        original_size = image.size
        
        # Preprocess image
        processed_img = preprocess_image(image)
        
        # Make prediction
        prediction = model.predict(processed_img, verbose=0)
        
        # Extract mask
        mask = prediction[0, :, :, 0]  # (128, 128)
        
        # Calculate statistics
        tumor_pixels = int(np.sum(mask > 0.5))
        total_pixels = mask.shape[0] * mask.shape[1]
        tumor_percentage = (tumor_pixels / total_pixels) * 100
        
        # Get original image array for overlay
        original_img_array = processed_img[0, :, :, 0]  # (128, 128)
        
        # Create visualization
        overlay_img = create_segmentation_overlay(original_img_array, mask)
        
        # Convert overlay to PIL Image
        overlay_pil = Image.fromarray(overlay_img)
        
        # Resize back to original size if needed
        if original_size != (128, 128):
            overlay_pil = overlay_pil.resize(original_size, Image.LANCZOS)
        
        # Convert to base64 for JSON response
        buffered = io.BytesIO()
        overlay_pil.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        # Also convert mask to base64
        mask_img = Image.fromarray((mask * 255).astype(np.uint8))
        if original_size != (128, 128):
            mask_img = mask_img.resize(original_size, Image.LANCZOS)
        mask_buffered = io.BytesIO()
        mask_img.save(mask_buffered, format="PNG")
        mask_str = base64.b64encode(mask_buffered.getvalue()).decode()
        
        return {
            "success": True,
            "tumor_pixels": tumor_pixels,
            "total_pixels": total_pixels,
            "tumor_percentage": round(tumor_percentage, 2),
            "segmented_image": img_str,
            "mask": mask_str,
            "original_size": list(original_size),
            "model_size": [128, 128]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")

@app.post("/batch-predict")
async def batch_predict(files: list[UploadFile] = File(...)):
    """
    Predict tumor segmentation for multiple images
    Args:
        files: List of uploaded image files
    Returns:
        JSON with batch segmentation results
    """
    if model is None:
        raise HTTPException(
            status_code=503,
            detail="Model not loaded. Please ensure the model file exists at the specified path."
        )
    
    if len(files) > 10:
        raise HTTPException(
            status_code=400,
            detail="Maximum 10 images allowed per batch"
        )
    
    results = []
    
    for idx, file in enumerate(files):
        try:
            # Read image file
            image_data = await file.read()
            image = Image.open(io.BytesIO(image_data))
            
            # Preprocess image
            processed_img = preprocess_image(image)
            
            # Make prediction
            prediction = model.predict(processed_img, verbose=0)
            
            # Extract mask
            mask = prediction[0, :, :, 0]
            
            # Calculate statistics
            tumor_pixels = int(np.sum(mask > 0.5))
            total_pixels = mask.shape[0] * mask.shape[1]
            tumor_percentage = (tumor_pixels / total_pixels) * 100
            
            results.append({
                "filename": file.filename,
                "success": True,
                "tumor_pixels": tumor_pixels,
                "tumor_percentage": round(tumor_percentage, 2)
            })
            
        except Exception as e:
            results.append({
                "filename": file.filename,
                "success": False,
                "error": str(e)
            })
    
    return {
        "total_images": len(files),
        "successful": sum(1 for r in results if r["success"]),
        "failed": sum(1 for r in results if not r["success"]),
        "results": results
    }

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Brain Tumor Segmentation API...")
    print("📍 API will be available at http://localhost:8000")
    print("📖 Documentation at http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000)
