export default function About() {
  return (
    <div className="px-4 py-8 max-w-4xl mx-auto">
      <h1 className="text-4xl font-bold mb-6">About DAMM</h1>
      <div className="bg-white rounded-lg shadow-md p-8">
        <h2 className="text-2xl font-bold mb-4">Decentralized AI Model Marketplace</h2>
        <p className="text-gray-700 mb-4">
          DAMM is a revolutionary platform that connects AI researchers, developers, and businesses
          in a decentralized marketplace for AI models.
        </p>
        <h3 className="text-xl font-bold mb-3">Our Mission</h3>
        <p className="text-gray-700 mb-4">
          To democratize access to cutting-edge AI models and create a fair, transparent ecosystem
          where model creators are rewarded for their innovations.
        </p>
        <h3 className="text-xl font-bold mb-3">Key Features</h3>
        <ul className="list-disc list-inside text-gray-700 space-y-2">
          <li>Browse and discover state-of-the-art AI models</li>
          <li>Subscribe to models with flexible pricing plans</li>
          <li>Test models before subscribing</li>
          <li>Secure blockchain-based transactions</li>
          <li>Transparent performance metrics</li>
        </ul>
      </div>
    </div>
  )
}
