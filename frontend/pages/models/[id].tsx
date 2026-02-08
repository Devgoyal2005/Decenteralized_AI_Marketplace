import { useState, useEffect, ChangeEvent } from 'react'
import { useRouter } from 'next/router'
import axios from 'axios'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'

interface ModelDetails {
  id: string
  name: string
  description: string
  category: string
  featured: boolean
  version: string
  author: string
  created_at: string
  stats: any
  architecture: any
  performance: any
  subscription: any
}

export default function ModelDetails() {
  const router = useRouter()
  const { id } = router.query
  const [model, setModel] = useState<ModelDetails | null>(null)
  const [loading, setLoading] = useState(true)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [predicting, setPredicting] = useState(false)
  const [prediction, setPrediction] = useState<any>(null)

  useEffect(() => {
    if (id) {
      fetchModelDetails()
    }
  }, [id])

  const fetchModelDetails = async () => {
    try {
      const response = await axios.get(`http://localhost:8000/api/models/${id}`)
      setModel(response.data)
    } catch (error) {
      console.error('Error fetching model details:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleFileSelect = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.files && event.target.files[0]) {
      setSelectedFile(event.target.files[0])
      setPrediction(null)
    }
  }

  const handlePredict = async () => {
    if (!selectedFile) return

    setPredicting(true)
    const formData = new FormData()
    formData.append('file', selectedFile)

    try {
      const response = await axios.post('http://localhost:8000/api/predict', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      })
      setPrediction(response.data.prediction)
    } catch (error) {
      console.error('Error predicting:', error)
      alert('Prediction failed. Please try again.')
    } finally {
      setPredicting(false)
    }
  }

  const handleSubscribe = () => {
    alert('Subscription feature coming soon! This will integrate with blockchain payments.')
  }

  if (loading) {
    return (
      <div className="text-center py-12">
        <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
        <p className="mt-4 text-gray-600">Loading model details...</p>
      </div>
    )
  }

  if (!model) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-600">Model not found</p>
      </div>
    )
  }

  return (
    <div className="px-4 py-8">
      <button
        onClick={() => router.push('/')}
        className="mb-6 text-indigo-600 hover:text-indigo-800 flex items-center"
      >
        ← Back to Marketplace
      </button>

      <div className="bg-white rounded-lg shadow-lg overflow-hidden">
        <div className="bg-gradient-to-r from-indigo-600 to-purple-600 text-white p-8">
          <div className="flex justify-between items-start">
            <div>
              <h1 className="text-3xl font-bold mb-2">{model.name}</h1>
              <p className="text-indigo-100 mb-4">{model.description}</p>
              <div className="flex space-x-4 text-sm">
                <span>Version: {model.version}</span>
                <span>•</span>
                <span>Author: {model.author}</span>
                <span>•</span>
                <span>Category: {model.category}</span>
              </div>
            </div>
            {model.featured && (
              <span className="bg-yellow-400 text-gray-900 px-3 py-1 rounded-full text-sm font-semibold">
                ⭐ Featured
              </span>
            )}
          </div>
        </div>

        <div className="p-8">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
            {/* Performance Metrics */}
            <div>
              <h2 className="text-2xl font-bold mb-4">Performance Metrics</h2>
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-green-50 p-4 rounded-lg">
                  <p className="text-sm text-gray-600">Train Accuracy</p>
                  <p className="text-2xl font-bold text-green-600">{model.performance.train_accuracy}%</p>
                </div>
                <div className="bg-blue-50 p-4 rounded-lg">
                  <p className="text-sm text-gray-600">Val Accuracy</p>
                  <p className="text-2xl font-bold text-blue-600">{model.performance.val_accuracy}%</p>
                </div>
                <div className="bg-purple-50 p-4 rounded-lg">
                  <p className="text-sm text-gray-600">Dice Coefficient</p>
                  <p className="text-2xl font-bold text-purple-600">{model.performance.dice_coefficient}%</p>
                </div>
                <div className="bg-orange-50 p-4 rounded-lg">
                  <p className="text-sm text-gray-600">Epochs Trained</p>
                  <p className="text-2xl font-bold text-orange-600">{model.performance.epochs_trained}</p>
                </div>
              </div>
            </div>

            {/* Subscription Options */}
            <div>
              <h2 className="text-2xl font-bold mb-4">Subscription Plans</h2>
              <div className="space-y-4">
                <div className="border-2 border-indigo-200 rounded-lg p-4 hover:border-indigo-500 transition-colors">
                  <div className="flex justify-between items-center mb-2">
                    <h3 className="font-bold text-lg">Monthly Plan</h3>
                    <span className="text-2xl font-bold text-indigo-600">${model.subscription.price_monthly}</span>
                  </div>
                  <p className="text-sm text-gray-600 mb-4">
                    {model.subscription.api_calls_limit.toLocaleString()} API calls/month
                  </p>
                  <button
                    onClick={handleSubscribe}
                    className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-2 px-4 rounded transition-colors"
                  >
                    Subscribe Monthly
                  </button>
                </div>
                <div className="border-2 border-purple-200 rounded-lg p-4 hover:border-purple-500 transition-colors">
                  <div className="flex justify-between items-center mb-2">
                    <h3 className="font-bold text-lg">Yearly Plan</h3>
                    <span className="text-2xl font-bold text-purple-600">${model.subscription.price_yearly}</span>
                  </div>
                  <p className="text-sm text-gray-600 mb-2">
                    {model.subscription.api_calls_limit.toLocaleString()} API calls/month
                  </p>
                  <p className="text-xs text-green-600 font-semibold mb-4">Save 17%!</p>
                  <button
                    onClick={handleSubscribe}
                    className="w-full bg-purple-600 hover:bg-purple-700 text-white font-medium py-2 px-4 rounded transition-colors"
                  >
                    Subscribe Yearly
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Dataset Statistics */}
          <div className="mb-8">
            <h2 className="text-2xl font-bold mb-4">Dataset Statistics</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-gray-50 p-4 rounded-lg">
                <p className="text-sm text-gray-600">3D MRI Volumes</p>
                <p className="text-xl font-bold">{model.stats.dataset.total_3d_volumes}</p>
              </div>
              <div className="bg-gray-50 p-4 rounded-lg">
                <p className="text-sm text-gray-600">Total 2D Slices</p>
                <p className="text-xl font-bold">{model.stats.dataset.total_2d_slices.toLocaleString()}</p>
              </div>
              <div className="bg-gray-50 p-4 rounded-lg">
                <p className="text-sm text-gray-600">Tumor Slices</p>
                <p className="text-xl font-bold">{model.stats.dataset.tumor_slices.toLocaleString()}</p>
              </div>
              <div className="bg-gray-50 p-4 rounded-lg">
                <p className="text-sm text-gray-600">Avg Tumor %</p>
                <p className="text-xl font-bold">{model.stats.dataset.average_tumor_percentage}%</p>
              </div>
            </div>
          </div>

          {/* Model Architecture */}
          <div className="mb-8">
            <h2 className="text-2xl font-bold mb-4">Model Architecture</h2>
            <div className="bg-gray-50 p-6 rounded-lg">
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <div>
                  <p className="text-sm text-gray-600">Architecture</p>
                  <p className="font-semibold">{model.stats.model_architecture.name}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-600">Total Parameters</p>
                  <p className="font-semibold">{model.stats.model_architecture.total_parameters.toLocaleString()}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-600">Model Size</p>
                  <p className="font-semibold">{model.stats.model_architecture.model_size_mb} MB</p>
                </div>
                <div>
                  <p className="text-sm text-gray-600">Input Shape</p>
                  <p className="font-semibold">{model.architecture.input_shape.join(' × ')}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-600">Loss Function</p>
                  <p className="font-semibold">{model.architecture.loss}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-600">Optimizer</p>
                  <p className="font-semibold">{model.architecture.optimizer}</p>
                </div>
              </div>
            </div>
          </div>

          {/* Training Progress Chart */}
          <div className="mb-8">
            <h2 className="text-2xl font-bold mb-4">Training Progress</h2>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={model.stats.training_progression}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="epoch" label={{ value: 'Epoch', position: 'insideBottom', offset: -5 }} />
                <YAxis label={{ value: 'Accuracy (%)', angle: -90, position: 'insideLeft' }} />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="train_acc" stroke="#8884d8" name="Train Accuracy" />
                <Line type="monotone" dataKey="val_acc" stroke="#82ca9d" name="Val Accuracy" />
                <Line type="monotone" dataKey="dice" stroke="#ffc658" name="Dice Coefficient" />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Try Model */}
          <div className="border-t pt-8">
            <h2 className="text-2xl font-bold mb-4">Try the Model</h2>
            <div className="bg-gray-50 p-6 rounded-lg">
              <p className="text-gray-600 mb-4">Upload an MRI scan (grayscale image) to test the model:</p>
              <input
                type="file"
                accept="image/*"
                onChange={handleFileSelect}
                className="mb-4 block w-full text-sm text-gray-500
                  file:mr-4 file:py-2 file:px-4
                  file:rounded-full file:border-0
                  file:text-sm file:font-semibold
                  file:bg-indigo-50 file:text-indigo-700
                  hover:file:bg-indigo-100"
              />
              {selectedFile && (
                <button
                  onClick={handlePredict}
                  disabled={predicting}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-2 px-6 rounded disabled:bg-gray-400 disabled:cursor-not-allowed"
                >
                  {predicting ? 'Analyzing...' : 'Predict Tumor'}
                </button>
              )}
              {prediction && (
                <div className="mt-6 p-4 bg-white rounded-lg border-2 border-indigo-200">
                  <h3 className="font-bold mb-2">Prediction Results:</h3>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-sm text-gray-600">Tumor Detected</p>
                      <p className="font-semibold text-lg">
                        {prediction.tumor_detected ? '✅ Yes' : '❌ No'}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600">Tumor Coverage</p>
                      <p className="font-semibold text-lg">{prediction.tumor_percentage}%</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600">Confidence</p>
                      <p className="font-semibold text-lg">{(prediction.confidence * 100).toFixed(2)}%</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600">Image Size</p>
                      <p className="font-semibold text-lg">{prediction.image_size.join(' × ')}</p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
