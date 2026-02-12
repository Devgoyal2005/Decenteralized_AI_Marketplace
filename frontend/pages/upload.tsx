import { useState } from 'react';
import Head from 'next/head';
import Link from 'next/link';

export default function Upload() {
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    creator: '',
    model_type: 'keras',
    category: 'General',
    price_monthly: '',
    price_yearly: '',
    input_shape: '',
    output_shape: '',
    tags: '',
    accuracy: '',
  });
  
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<any>(null);
  const [error, setError] = useState('');
  
  const [walletConnected, setWalletConnected] = useState(false);
  const [walletAddress, setWalletAddress] = useState('');

  const connectWallet = async () => {
    if (typeof window.ethereum !== 'undefined') {
      try {
        const accounts = await window.ethereum.request({ method: 'eth_requestAccounts' });
        setWalletAddress(accounts[0]);
        setWalletConnected(true);
        setFormData({ ...formData, creator: accounts[0] });
      } catch (err) {
        console.error('MetaMask connection error:', err);
        setError('Failed to connect MetaMask');
      }
    } else {
      setError('Please install MetaMask to upload models');
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setFormData({ ...formData, [name]: value });
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setError('');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!file) {
      setError('Please select a model file');
      return;
    }
    
    if (!walletConnected) {
      setError('Please connect your wallet first');
      return;
    }
    
    setUploading(true);
    setError('');
    setUploadResult(null);
    
    try {
      const formDataToSend = new FormData();
      formDataToSend.append('file', file);
      formDataToSend.append('name', formData.name);
      formDataToSend.append('description', formData.description);
      formDataToSend.append('creator', formData.creator);
      formDataToSend.append('model_type', formData.model_type);
      formDataToSend.append('category', formData.category);
      
      if (formData.price_monthly) {
        formDataToSend.append('price_monthly', formData.price_monthly);
      }
      if (formData.price_yearly) {
        formDataToSend.append('price_yearly', formData.price_yearly);
      }
      if (formData.input_shape) {
        formDataToSend.append('input_shape', formData.input_shape);
      }
      if (formData.output_shape) {
        formDataToSend.append('output_shape', formData.output_shape);
      }
      if (formData.tags) {
        formDataToSend.append('tags', formData.tags);
      }
      if (formData.accuracy) {
        formDataToSend.append('accuracy', formData.accuracy);
      }
      
      const response = await fetch('http://localhost:8000/api/models/upload', {
        method: 'POST',
        body: formDataToSend,
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Upload failed');
      }
      
      const result = await response.json();
      setUploadResult(result);
      
      // Reset form
      setFormData({
        name: '',
        description: '',
        creator: walletAddress,
        model_type: 'keras',
        category: 'General',
        price_monthly: '',
        price_yearly: '',
        input_shape: '',
        output_shape: '',
        tags: '',
        accuracy: '',
      });
      setFile(null);
      
    } catch (err: any) {
      setError(err.message || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <>
      <Head>
        <title>Upload Model - DAMM</title>
      </Head>

      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
        {/* Navigation */}
        <nav className="bg-white shadow-md">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex justify-between h-16">
              <div className="flex items-center">
                <Link href="/" className="text-2xl font-bold text-indigo-600">
                  DAMM
                </Link>
                <span className="ml-2 text-sm text-gray-600">Decentralized AI Model Marketplace</span>
              </div>
              <div className="flex items-center space-x-4">
                <Link href="/" className="text-gray-700 hover:text-indigo-600">
                  Marketplace
                </Link>
                <Link href="/about" className="text-gray-700 hover:text-indigo-600">
                  About
                </Link>
                <Link href="/upload" className="text-indigo-600 font-semibold">
                  Upload
                </Link>
              </div>
            </div>
          </div>
        </nav>

        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
          {/* Header */}
          <div className="text-center mb-12">
            <h1 className="text-4xl font-bold text-gray-900 mb-4">
              Upload Your AI Model
            </h1>
            <p className="text-lg text-gray-600">
              Share your trained model with the world via IPFS
            </p>
          </div>

          {/* Wallet Connection */}
          {!walletConnected && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6 mb-8">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-semibold text-yellow-800 mb-2">
                    Connect Your Wallet
                  </h3>
                  <p className="text-yellow-700">
                    You need to connect your MetaMask wallet to upload models
                  </p>
                </div>
                <button
                  onClick={connectWallet}
                  className="bg-yellow-600 hover:bg-yellow-700 text-white font-bold py-2 px-6 rounded-lg transition duration-200"
                >
                  Connect MetaMask
                </button>
              </div>
            </div>
          )}

          {walletConnected && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-8">
              <div className="flex items-center">
                <svg className="w-5 h-5 text-green-600 mr-3" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                </svg>
                <span className="text-green-800 font-medium">
                  Wallet connected: {walletAddress.substring(0, 6)}...{walletAddress.substring(38)}
                </span>
              </div>
            </div>
          )}

          {/* Upload Form */}
          <div className="bg-white rounded-xl shadow-lg p-8">
            <form onSubmit={handleSubmit} className="space-y-6">
              {/* Model File */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Model File *
                </label>
                <div className="mt-1 flex justify-center px-6 pt-5 pb-6 border-2 border-gray-300 border-dashed rounded-lg hover:border-indigo-500 transition duration-200">
                  <div className="space-y-1 text-center">
                    <svg className="mx-auto h-12 w-12 text-gray-400" stroke="currentColor" fill="none" viewBox="0 0 48 48">
                      <path d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                    <div className="flex text-sm text-gray-600">
                      <label className="relative cursor-pointer bg-white rounded-md font-medium text-indigo-600 hover:text-indigo-500">
                        <span>Upload a file</span>
                        <input
                          type="file"
                          className="sr-only"
                          accept=".keras,.h5,.pkl,.pt,.pth"
                          onChange={handleFileChange}
                          required
                        />
                      </label>
                      <p className="pl-1">or drag and drop</p>
                    </div>
                    <p className="text-xs text-gray-500">
                      .keras, .h5, .pkl, .pt files up to 500MB
                    </p>
                    {file && (
                      <p className="text-sm text-indigo-600 font-medium mt-2">
                        Selected: {file.name} ({(file.size / 1024 / 1024).toFixed(2)} MB)
                      </p>
                    )}
                  </div>
                </div>
              </div>

              {/* Model Name */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Model Name *
                </label>
                <input
                  type="text"
                  name="name"
                  value={formData.name}
                  onChange={handleInputChange}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                  placeholder="e.g., Brain Tumor Segmentation U-Net"
                  required
                />
              </div>

              {/* Description */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Description *
                </label>
                <textarea
                  name="description"
                  value={formData.description}
                  onChange={handleInputChange}
                  rows={4}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                  placeholder="Describe what your model does, the dataset it was trained on, and its performance..."
                  required
                />
              </div>

              {/* Category and Model Type */}
              <div className="grid grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Category *
                  </label>
                  <select
                    name="category"
                    value={formData.category}
                    onChange={handleInputChange}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                  >
                    <option value="General">General</option>
                    <option value="Medical Imaging">Medical Imaging</option>
                    <option value="Computer Vision">Computer Vision</option>
                    <option value="NLP">Natural Language Processing</option>
                    <option value="Audio">Audio Processing</option>
                    <option value="Time Series">Time Series</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Model Type *
                  </label>
                  <select
                    name="model_type"
                    value={formData.model_type}
                    onChange={handleInputChange}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                  >
                    <option value="keras">Keras (.keras, .h5)</option>
                    <option value="pytorch">PyTorch (.pt, .pth)</option>
                    <option value="sklearn">Scikit-learn (.pkl)</option>
                  </select>
                </div>
              </div>

              {/* Model Shapes */}
              <div className="grid grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Input Shape
                  </label>
                  <input
                    type="text"
                    name="input_shape"
                    value={formData.input_shape}
                    onChange={handleInputChange}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                    placeholder="128, 128, 1"
                  />
                  <p className="text-xs text-gray-500 mt-1">Comma-separated dimensions</p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Output Shape
                  </label>
                  <input
                    type="text"
                    name="output_shape"
                    value={formData.output_shape}
                    onChange={handleInputChange}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                    placeholder="128, 128, 1"
                  />
                  <p className="text-xs text-gray-500 mt-1">Comma-separated dimensions</p>
                </div>
              </div>

              {/* Tags and Accuracy */}
              <div className="grid grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Tags
                  </label>
                  <input
                    type="text"
                    name="tags"
                    value={formData.tags}
                    onChange={handleInputChange}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                    placeholder="medical, imaging, segmentation"
                  />
                  <p className="text-xs text-gray-500 mt-1">Comma-separated keywords</p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Accuracy (%)
                  </label>
                  <input
                    type="number"
                    name="accuracy"
                    value={formData.accuracy}
                    onChange={handleInputChange}
                    step="0.01"
                    min="0"
                    max="100"
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                    placeholder="99.77"
                  />
                </div>
              </div>

              {/* Pricing */}
              <div className="grid grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Monthly Price (USD)
                  </label>
                  <input
                    type="number"
                    name="price_monthly"
                    value={formData.price_monthly}
                    onChange={handleInputChange}
                    step="0.01"
                    min="0"
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                    placeholder="49.99"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Yearly Price (USD)
                  </label>
                  <input
                    type="number"
                    name="price_yearly"
                    value={formData.price_yearly}
                    onChange={handleInputChange}
                    step="0.01"
                    min="0"
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                    placeholder="499.99"
                  />
                </div>
              </div>

              {/* Submit Button */}
              <div className="pt-4">
                <button
                  type="submit"
                  disabled={uploading || !walletConnected}
                  className={`w-full py-3 px-6 rounded-lg font-semibold text-white transition duration-200 ${
                    uploading || !walletConnected
                      ? 'bg-gray-400 cursor-not-allowed'
                      : 'bg-indigo-600 hover:bg-indigo-700'
                  }`}
                >
                  {uploading ? (
                    <span className="flex items-center justify-center">
                      <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                      Uploading to IPFS...
                    </span>
                  ) : (
                    'Upload to IPFS'
                  )}
                </button>
              </div>
            </form>

            {/* Error Message */}
            {error && (
              <div className="mt-6 bg-red-50 border border-red-200 rounded-lg p-4">
                <div className="flex">
                  <svg className="w-5 h-5 text-red-600 mr-3" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                  </svg>
                  <span className="text-red-800">{error}</span>
                </div>
              </div>
            )}

            {/* Success Message */}
            {uploadResult && (
              <div className="mt-6 bg-green-50 border border-green-200 rounded-lg p-6">
                <div className="flex items-start">
                  <svg className="w-6 h-6 text-green-600 mr-3 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                  </svg>
                  <div className="flex-1">
                    <h3 className="text-lg font-semibold text-green-800 mb-2">
                      ✅ Upload Successful!
                    </h3>
                    <p className="text-green-700 mb-3">{uploadResult.message}</p>
                    
                    <div className="space-y-2 text-sm">
                      <div>
                        <span className="font-semibold text-green-800">Model ID:</span>
                        <code className="ml-2 bg-green-100 px-2 py-1 rounded">{uploadResult.model_id}</code>
                      </div>
                      <div>
                        <span className="font-semibold text-green-800">IPFS Hash:</span>
                        <code className="ml-2 bg-green-100 px-2 py-1 rounded text-xs">{uploadResult.ipfs_hash}</code>
                      </div>
                      <div className="pt-2">
                        <a
                          href={uploadResult.gateway_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-indigo-600 hover:text-indigo-800 font-medium"
                        >
                          View on IPFS Gateway →
                        </a>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Info Box */}
          <div className="mt-8 bg-blue-50 border border-blue-200 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-blue-900 mb-3">
              📡 How IPFS Upload Works
            </h3>
            <ol className="space-y-2 text-blue-800">
              <li>1. Your model file is uploaded to Pinata (IPFS provider)</li>
              <li>2. You receive a unique IPFS hash (Content Identifier)</li>
              <li>3. Model metadata is stored in the local registry</li>
              <li>4. Anyone can download your model using the IPFS hash</li>
              <li>5. Models are cached locally when first downloaded</li>
            </ol>
          </div>
        </div>
      </div>
    </>
  );
}
