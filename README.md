# DAMM - Decentralized AI Model Marketplace

A full-stack application for browsing, testing, and subscribing to AI models. Features a brain tumor segmentation model using U-Net architecture trained on the BraTS 2020 dataset.

## Project Structure

```
├── backend/              # FastAPI backend server
│   ├── main.py          # Main API application
│   ├── model_stats.json # Model metadata and statistics
│   └── unet_brain_tumor_final.keras # Trained U-Net model (not in git)
├── frontend/            # Next.js frontend application
│   ├── pages/          # Page components
│   ├── styles/         # Tailwind CSS styles
│   └── package.json    # Frontend dependencies
├── Test_images/        # Sample MRI images for testing
└── unet_brain_tumor_final.keras # Model file (copy to backend/)
```

## Features

- 🧠 **Brain Tumor Segmentation** - U-Net model (7.7M parameters, 99.77% accuracy)
- 📊 **Model Statistics** - Dataset info, architecture details, training metrics
- 🔍 **Live Testing** - Upload MRI images and get real-time predictions
- 💳 **Subscription Plans** - Monthly/yearly pricing (blockchain integration coming)
- 📈 **Visualizations** - Training progress charts and performance metrics
- 🎯 **REST API** - FastAPI backend with CORS support

## Tech Stack

### Backend
- **FastAPI** - Modern Python web framework
- **TensorFlow 2.15** - Deep learning model inference
- **Pillow** - Image processing
- **Python 3.10+** - Runtime environment

### Frontend
- **Next.js 14** - React framework with SSR
- **React 18** - UI library
- **TypeScript 5** - Type-safe JavaScript
- **Tailwind CSS 3** - Utility-first CSS framework
- **Recharts** - Data visualization library
- **Axios** - HTTP client

## Model Details

- **Architecture**: U-Net 2D for binary segmentation
- **Dataset**: BraTS 2020 (368 patients, 57,040 slices)
- **Performance**: 99.77% validation accuracy, 94.27% Dice coefficient
- **Input**: 128x128 grayscale MRI images
- **Output**: Binary tumor segmentation mask

## Setup & Running

### Prerequisites
- Python 3.10 or higher
- Node.js 18 or higher
- 2GB RAM minimum

### Backend Setup

```bash
# Navigate to backend directory
cd backend

# Install dependencies
pip install -r requirements.txt

# Make sure model file exists in backend/
# (Copy from root if needed: unet_brain_tumor_final.keras)

# Start the server
uvicorn main:app --host 0.0.0.0 --port 8000
```

Backend will be available at `http://localhost:8000`
API docs at `http://localhost:8000/docs`

### Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

Frontend will be available at `http://localhost:3000`

### Testing the API

```bash
# Test with sample images
cd backend
python test_predict.py  # Tests model loading and prediction
python test_api.py      # Tests API endpoints
```

## API Endpoints

- `GET /api/models` - List all available models
- `GET /api/models/{id}` - Get specific model details
- `POST /api/predict` - Upload image for prediction
- `GET /api/health` - Health check endpoint

## Development Notes

- Model file (`unet_brain_tumor_final.keras`) is ~100MB and excluded from git
- Custom `dice_coef` metric is required for model loading
- CORS is configured for `http://localhost:3000`
- TensorFlow verbose output is suppressed during startup

## Future Enhancements

- [ ] Blockchain integration for subscriptions
- [ ] User authentication and authorization
- [ ] Model versioning and A/B testing
- [ ] Batch prediction API
- [ ] Model performance monitoring
- [ ] Support for multiple AI models
- [ ] Payment gateway integration

## License

MIT

## Contributing

Pull requests are welcome. For major changes, please open an issue first.
```
