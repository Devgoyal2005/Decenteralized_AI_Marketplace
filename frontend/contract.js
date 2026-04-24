/**
 * contract.js - Shared module for interacting with DAMM contracts via ethers.js v6.
 * Depends on ethers.js injected via CDN and contract-config.js.
 */

let modelRegistryContract = null;
let modelLicenseContract = null;
let currentSigner = null;
let currentProvider = null;

function _getRegistryConfig() {
  if (typeof MODEL_REGISTRY_CONFIG !== "undefined") return MODEL_REGISTRY_CONFIG;
  if (typeof CONTRACT_CONFIG !== "undefined") return CONTRACT_CONFIG;
  throw new Error("Model registry contract config is missing");
}

function _getRegistryAbi() {
  if (typeof MODEL_REGISTRY_ABI !== "undefined") return MODEL_REGISTRY_ABI;
  if (typeof CONTRACT_ABI !== "undefined") return CONTRACT_ABI;
  throw new Error("Model registry ABI is missing");
}

function _getLicenseConfig() {
  if (typeof MODEL_LICENSE_CONFIG !== "undefined") return MODEL_LICENSE_CONFIG;
  throw new Error("Model license contract config is missing. Re-run deploy script for Phase 3.");
}

function _getLicenseAbi() {
  if (typeof MODEL_LICENSE_ABI !== "undefined") return MODEL_LICENSE_ABI;
  throw new Error("Model license ABI is missing. Re-run deploy script for Phase 3.");
}

async function initContract() {
  if (!window.ethereum) throw new Error("MetaMask is required");

  const registryConfig = _getRegistryConfig();
  const currentChainId = await window.ethereum.request({ method: 'eth_chainId' });
  const targetChainIdHex = '0x' + registryConfig.chainId.toString(16);

  if (currentChainId !== targetChainIdHex && registryConfig.network !== 'hardhat' && registryConfig.network !== 'localhost') {
    try {
      await window.ethereum.request({
        method: 'wallet_switchEthereumChain',
        params: [{ chainId: targetChainIdHex }],
      });
    } catch (switchError) {
      if (switchError.code === 4902 && typeof showToast === "function") {
        showToast(`Please add the ${registryConfig.network} network to MetaMask`, "error");
      }
      throw switchError;
    }
  }

  currentProvider = new ethers.BrowserProvider(window.ethereum);
  currentSigner = await currentProvider.getSigner();

  modelRegistryContract = new ethers.Contract(
    registryConfig.address,
    _getRegistryAbi(),
    currentSigner
  );

  const licenseConfig = _getLicenseConfig();
  modelLicenseContract = new ethers.Contract(
    licenseConfig.address,
    _getLicenseAbi(),
    currentSigner
  );

  return {
    modelRegistryContract,
    modelLicenseContract,
  };
}

async function getContract() {
  return getModelRegistryContract();
}

async function getModelRegistryContract() {
  if (modelRegistryContract) return modelRegistryContract;
  await initContract();
  return modelRegistryContract;
}

async function getModelLicenseContract() {
  if (modelLicenseContract) return modelLicenseContract;
  await initContract();
  return modelLicenseContract;
}

window.addEventListener('walletConnected', async () => {
  try {
    await initContract();
  } catch (err) {
    console.warn("Failed to init contract initially", err);
  }
});
