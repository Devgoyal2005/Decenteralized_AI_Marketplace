import { useState, useEffect } from 'react'
import Link from 'next/link'
import axios from 'axios'

interface Model {
  id: string
  name: string
  description: string
  category: string
  featured: boolean
  version: string
  accuracy?: number
  ipfs_hash?: string
  gateway_url?: string
  creator?: string
  pricing?: {
    monthly?: number
    yearly?: number
  }
}

export default function Home() {
  const [models, setModels] = useState<Model[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchModels()
  }, [])

  const fetchModels = async () => {
    try {
      const response = await axios.get('http://localhost:8000/api/models')
      setModels(response.data.models)
    } catch (error) {
      console.error('Error fetching models:', error)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="px-4 py-8">
      {/* Navigation */}
      <nav className="max-w-7xl mx-auto mb-8">
        <div className="flex justify-between items-center">
          <Link href="/" className="text-2xl font-bold text-indigo-600">
            DAMM
          </Link>
          <div className="flex items-center space-x-6">
            <Link href="/" className="text-gray-700 hover:text-indigo-600 font-medium">
              Marketplace
            </Link>
            <Link href="/upload" className="text-gray-700 hover:text-indigo-600 font-medium">
              Upload
            </Link>
            <Link href="/about" className="text-gray-700 hover:text-indigo-600 font-medium">
              About
            </Link>
          </div>
        </div>
      </nav>

      <div className="text-center mb-12">
        <h1 className="text-5xl font-bold text-gray-900 mb-4">
          DAMM
        </h1>
        <p className="text-xl text-gray-600 mb-2">
          Decentralized AI Model Marketplace
        </p>
        <p className="text-gray-500">
          Discover, subscribe, and deploy cutting-edge AI models
        </p>
      </div>

      {loading ? (
        <div className="text-center py-12">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
          <p className="mt-4 text-gray-600">Loading models...</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {models.map((model) => (
            <div
              key={model.id}
              className={`bg-white rounded-lg shadow-md overflow-hidden hover:shadow-xl transition-shadow ${
                model.featured ? 'ring-2 ring-indigo-500' : ''
              }`}
            >
              {model.featured && (
                <div className="bg-indigo-600 text-white text-center py-1 text-sm font-semibold">
                  ⭐ FEATURED MODEL
                </div>
              )}
              <div className="p-6">
                <div className="flex justify-between items-start mb-4">
                  <h3 className="text-xl font-bold text-gray-900">{model.name}</h3>
                  <span className="bg-green-100 text-green-800 text-xs font-medium px-2.5 py-0.5 rounded">
                    {model.version || 'v1.0'}
                  </span>
                </div>
                <p className="text-gray-600 mb-4 text-sm">{model.description}</p>
                
                <div className="space-y-2 mb-4">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-500">{model.category}</span>
                    {model.accuracy && (
                      <span className="text-sm font-semibold text-indigo-600">
                        Accuracy: {model.accuracy}%
                      </span>
                    )}
                  </div>
                  
                  {model.ipfs_hash && (
                    <div className="text-xs text-gray-500 truncate">
                      <span className="font-semibold">IPFS:</span> {model.ipfs_hash.substring(0, 12)}...
                    </div>
                  )}
                  
                  {model.creator && (
                    <div className="text-xs text-gray-500 truncate">
                      <span className="font-semibold">Creator:</span> {model.creator.substring(0, 8)}...
                    </div>
                  )}
                  
                  {model.pricing && model.pricing.monthly && (
                    <div className="text-sm font-bold text-green-600">
                      ${model.pricing.monthly}/month
                    </div>
                  )}
                </div>
                
                <div className="flex gap-2">
                  <Link href={`/models/${model.id}`} className="flex-1">
                    <button className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-2 px-4 rounded transition-colors">
                      View Details →
                    </button>
                  </Link>
                  {model.gateway_url && (
                    <a 
                      href={model.gateway_url} 
                      target="_blank" 
                      rel="noopener noreferrer"
                      className="bg-gray-200 hover:bg-gray-300 text-gray-700 font-medium py-2 px-3 rounded transition-colors"
                      title="View on IPFS"
                    >
                      📡
                    </a>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {!loading && models.length === 0 && (
        <div className="text-center py-12">
          <p className="text-gray-600">No models available at the moment.</p>
        </div>
      )}
    </div>
  )
}
