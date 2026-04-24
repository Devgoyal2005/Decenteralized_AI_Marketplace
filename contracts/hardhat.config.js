require("@nomicfoundation/hardhat-ethers");

/**
 * Hardhat configuration for DAMM smart contracts.
 *
 * Networks:
 *   - hardhat  : In-memory local chain (default)
 *   - localhost: Local Hardhat node (npx hardhat node)
 *   - sepolia  : Ethereum Sepolia testnet
 *
 * To deploy to Sepolia, create a .env file in this directory with:
 *   SEPOLIA_RPC_URL=https://eth-sepolia.g.alchemy.com/v2/YOUR_KEY
 *   DEPLOYER_PRIVATE_KEY=0xYOUR_PRIVATE_KEY
 */

// Load .env if it exists (optional, won't crash if missing)
const fs = require("fs");
const path = require("path");
const envPath = path.resolve(__dirname, ".env");
if (fs.existsSync(envPath)) {
  const envContent = fs.readFileSync(envPath, "utf-8");
  envContent.split("\n").forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) return;
    const eqIdx = trimmed.indexOf("=");
    if (eqIdx > 0) {
      const key = trimmed.slice(0, eqIdx).trim();
      const val = trimmed.slice(eqIdx + 1).trim();
      if (!process.env[key]) process.env[key] = val;
    }
  });
}

const SEPOLIA_RPC_URL = process.env.SEPOLIA_RPC_URL || "";
const DEPLOYER_PRIVATE_KEY_RAW = (process.env.DEPLOYER_PRIVATE_KEY || "").trim();

function normalizePrivateKey(raw) {
  if (!raw) return "";
  const withPrefix = raw.startsWith("0x") ? raw : `0x${raw}`;
  return /^0x[0-9a-fA-F]{64}$/.test(withPrefix) ? withPrefix : "";
}

const DEPLOYER_PRIVATE_KEY = normalizePrivateKey(DEPLOYER_PRIVATE_KEY_RAW);

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    version: "0.8.20",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200,
      },
    },
  },
  networks: {
    hardhat: {},
    localhost: {
      url: "http://127.0.0.1:8545",
    },
    ...(SEPOLIA_RPC_URL && DEPLOYER_PRIVATE_KEY
      ? {
          sepolia: {
            url: SEPOLIA_RPC_URL,
            accounts: [DEPLOYER_PRIVATE_KEY],
            chainId: 11155111,
          },
        }
      : {}),
  },
  paths: {
    sources: "./contracts",
    tests: "./test",
    cache: "./cache",
    artifacts: "./artifacts",
  },
};
