/**
 * contract.js - Shared module for interacting with the ModelRegistry contract via ethers.js v6.
 * Depends on ethers.js injected via CDN and contract-config.js.
 */

let dAppContract = null;
let currentSigner = null;
let currentProvider = null;

async function initContract() {
  if (!window.ethereum) throw new Error("MetaMask is required");

  const currentChainId = await window.ethereum.request({ method: 'eth_chainId' });
  const targetChainIdHex = '0x' + CONTRACT_CONFIG.chainId.toString(16);

  if (currentChainId !== targetChainIdHex && CONTRACT_CONFIG.network !== 'hardhat' && CONTRACT_CONFIG.network !== 'localhost') {
    try {
      await window.ethereum.request({
        method: 'wallet_switchEthereumChain',
        params: [{ chainId: targetChainIdHex }],
      });
    } catch (switchError) {
      if (switchError.code === 4902 && typeof showToast === "function") {
        showToast(`Please add the ${CONTRACT_CONFIG.network} network to MetaMask`, "error");
      }
      throw switchError;
    }
  }

  currentProvider = new ethers.BrowserProvider(window.ethereum);
  currentSigner = await currentProvider.getSigner();

  dAppContract = new ethers.Contract(
    CONTRACT_CONFIG.address,
    CONTRACT_ABI,
    currentSigner
  );

  return dAppContract;
}

async function getContract() {
  if (dAppContract) return dAppContract;
  return await initContract();
}

window.addEventListener('walletConnected', async () => {
  try {
    await initContract();
  } catch (err) {
    console.warn("Failed to init contract initially", err);
  }
});
