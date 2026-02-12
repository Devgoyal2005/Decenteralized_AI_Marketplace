"""
Model Manager - Handles dynamic model loading from IPFS
"""
import os
import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import tensorflow as tf
from tensorflow import keras

# Model cache directory
MODEL_CACHE_DIR = Path(os.getenv("MODEL_CACHE_DIR", "./model_cache"))
MODEL_CACHE_DIR.mkdir(exist_ok=True)

# Registry file
REGISTRY_FILE = Path(__file__).parent / "models_registry.json"


class ModelManager:
    """Manages model loading, caching, and registry"""
    
    def __init__(self, ipfs_service_instance=None):
        self.loaded_models: Dict[str, Any] = {}  # model_id -> loaded model object
        self.registry = self._load_registry()
        
        # Import ipfs_service if not provided
        if ipfs_service_instance:
            self.ipfs_service = ipfs_service_instance
        else:
            from ipfs_service import ipfs_service
            self.ipfs_service = ipfs_service
    
    def _load_registry(self) -> Dict:
        """Load the models registry from JSON"""
        if REGISTRY_FILE.exists():
            with open(REGISTRY_FILE, 'r') as f:
                return json.load(f)
        else:
            # Create empty registry
            registry = {"models": []}
            self._save_registry(registry)
            return registry
    
    def _save_registry(self, registry: Dict):
        """Save the models registry to JSON"""
        with open(REGISTRY_FILE, 'w') as f:
            json.dump(registry, f, indent=2)
    
    def add_model(self, model_info: Dict) -> bool:
        """
        Add a new model to the registry
        
        Args:
            model_info: Dictionary with model metadata
        
        Returns:
            True if successful
        """
        try:
            # Add timestamp if not present
            if 'uploaded_at' not in model_info:
                model_info['uploaded_at'] = datetime.utcnow().isoformat()
            
            # Add to registry
            self.registry['models'].append(model_info)
            self._save_registry(self.registry)
            
            print(f"✅ Model {model_info['id']} added to registry")
            return True
            
        except Exception as e:
            print(f"❌ Error adding model to registry: {str(e)}")
            return False
    
    def get_model_info(self, model_id: str) -> Optional[Dict]:
        """Get model info from registry"""
        for model in self.registry['models']:
            if model['id'] == model_id:
                return model
        return None
    
    def list_models(self) -> list:
        """List all models in registry"""
        return self.registry['models']
    
    def get_cached_model_path(self, model_id: str) -> Path:
        """Get the local cache path for a model"""
        model_info = self.get_model_info(model_id)
        if not model_info:
            return None
        
        # Use model type for extension
        model_type = model_info.get('model_type', 'keras')
        extension = {
            'keras': '.keras',
            'h5': '.h5',
            'pkl': '.pkl',
            'pt': '.pt'
        }.get(model_type, '.keras')
        
        return MODEL_CACHE_DIR / f"{model_id}{extension}"
    
    def is_model_cached(self, model_id: str) -> bool:
        """Check if model is downloaded in cache"""
        cache_path = self.get_cached_model_path(model_id)
        return cache_path and cache_path.exists()
    
    def download_model(self, model_id: str) -> bool:
        """
        Download model from IPFS to local cache
        
        Args:
            model_id: ID of the model to download
        
        Returns:
            True if successful
        """
        try:
            model_info = self.get_model_info(model_id)
            if not model_info:
                print(f"❌ Model {model_id} not found in registry")
                return False
            
            ipfs_hash = model_info.get('ipfs_hash')
            if not ipfs_hash:
                print(f"❌ No IPFS hash for model {model_id}")
                return False
            
            # Check if already cached
            cache_path = self.get_cached_model_path(model_id)
            if cache_path.exists():
                print(f"✅ Model {model_id} already cached at {cache_path}")
                return True
            
            # Download from IPFS
            print(f"📥 Downloading model {model_id} from IPFS...")
            success = self.ipfs_service.download_file(ipfs_hash, str(cache_path))
            
            if success:
                print(f"✅ Model {model_id} downloaded to cache")
                return True
            else:
                print(f"❌ Failed to download model {model_id}")
                return False
                
        except Exception as e:
            print(f"❌ Error downloading model: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def load_model(self, model_id: str, custom_objects: Optional[Dict] = None) -> Optional[Any]:
        """
        Load a model (downloads from IPFS if needed)
        
        Args:
            model_id: ID of the model to load
            custom_objects: Custom objects for model loading (e.g., custom metrics)
        
        Returns:
            Loaded model or None if failed
        """
        try:
            # Check if already loaded in memory
            if model_id in self.loaded_models:
                print(f"✅ Model {model_id} already loaded in memory")
                return self.loaded_models[model_id]
            
            # Get model info
            model_info = self.get_model_info(model_id)
            if not model_info:
                print(f"❌ Model {model_id} not found in registry")
                return None
            
            # Download if not cached
            if not self.is_model_cached(model_id):
                print(f"📥 Model not in cache, downloading from IPFS...")
                if not self.download_model(model_id):
                    return None
            
            # Load the model
            cache_path = self.get_cached_model_path(model_id)
            model_type = model_info.get('model_type', 'keras')
            
            print(f"🔄 Loading model {model_id} from {cache_path}...")
            
            if model_type in ['keras', 'h5']:
                # Suppress TensorFlow verbose output
                import logging
                logging.getLogger('tensorflow').setLevel(logging.FATAL)
                
                model = keras.models.load_model(
                    str(cache_path),
                    custom_objects=custom_objects or {}
                )
                
                # Cache in memory
                self.loaded_models[model_id] = model
                
                print(f"✅ Model {model_id} loaded successfully")
                print(f"   Input shape: {model.input_shape}")
                print(f"   Output shape: {model.output_shape}")
                
                return model
            
            elif model_type == 'pkl':
                import pickle
                with open(cache_path, 'rb') as f:
                    model = pickle.load(f)
                self.loaded_models[model_id] = model
                return model
            
            elif model_type == 'pt':
                import torch
                model = torch.load(cache_path)
                self.loaded_models[model_id] = model
                return model
            
            else:
                print(f"❌ Unsupported model type: {model_type}")
                return None
                
        except Exception as e:
            print(f"❌ Error loading model: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def unload_model(self, model_id: str):
        """Unload a model from memory"""
        if model_id in self.loaded_models:
            del self.loaded_models[model_id]
            print(f"✅ Model {model_id} unloaded from memory")
    
    def clear_cache(self):
        """Clear all cached models from disk"""
        import shutil
        if MODEL_CACHE_DIR.exists():
            shutil.rmtree(MODEL_CACHE_DIR)
            MODEL_CACHE_DIR.mkdir(exist_ok=True)
            print("✅ Model cache cleared")


# Global instance (will be initialized in main.py with ipfs_service)
# model_manager = ModelManager()
