// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title ModelRegistry
 * @notice On-chain registry for the Decentralized AI Model Marketplace (DAMM).
 *         Models are registered with their IPFS hash, metadata hash, and price.
 *         Buyers pay ETH to the model owner; purchase records are stored on-chain.
 */
contract ModelRegistry {

    // ─── Structs ──────────────────────────────────────────────
    struct Model {
        string  modelId;
        string  ipfsHash;        // CID of model file on IPFS/Pinata
        string  metadataHash;    // CID of metadata JSON on IPFS/Pinata
        address owner;
        uint256 priceWei;        // price in wei (0 = free)
        uint256 totalPurchases;
        bool    exists;
    }

    struct Purchase {
        address buyer;
        uint256 paidWei;
        uint256 timestamp;
    }

    // ─── State ────────────────────────────────────────────────
    mapping(string => Model) public models;
    mapping(string => Purchase[]) public purchaseHistory;
    mapping(string => mapping(address => bool)) public hasPurchased;
    mapping(address => string[]) public ownerModels;

    string[] public allModelIds;

    // ─── Events ───────────────────────────────────────────────
    event ModelRegistered(
        string indexed modelId,
        address indexed owner,
        string  ipfsHash,
        string  metadataHash,
        uint256 priceWei
    );

    event ModelPurchased(
        string indexed modelId,
        address indexed buyer,
        address indexed owner,
        uint256 paidWei
    );

    event ModelPriceUpdated(
        string indexed modelId,
        uint256 oldPrice,
        uint256 newPrice
    );

    // ─── Modifiers ────────────────────────────────────────────
    modifier onlyModelOwner(string calldata _modelId) {
        require(models[_modelId].exists, "Model does not exist");
        require(models[_modelId].owner == msg.sender, "Not model owner");
        _;
    }

    // ─── Register ─────────────────────────────────────────────
    /**
     * @notice Register a new model using backend generated ID.
     */
    function registerModel(
        string calldata _modelId,
        string calldata _ipfsHash,
        string calldata _metadataHash,
        uint256 _priceWei
    ) external {
        require(bytes(_ipfsHash).length > 0, "IPFS hash required");
        require(!models[_modelId].exists, "Model already registered");

        models[_modelId] = Model({
            modelId:         _modelId,
            ipfsHash:        _ipfsHash,
            metadataHash:    _metadataHash,
            owner:           msg.sender,
            priceWei:        _priceWei,
            totalPurchases:  0,
            exists:          true
        });

        allModelIds.push(_modelId);
        ownerModels[msg.sender].push(_modelId);

        emit ModelRegistered(_modelId, msg.sender, _ipfsHash, _metadataHash, _priceWei);
    }

    // ─── Buy ──────────────────────────────────────────────────
    /**
     * @notice Purchase access to a model. Sends ETH to the model owner.
     *         Reverts if already purchased or insufficient payment.
     * @param _modelId  The model to purchase
     */
    function buyModel(string calldata _modelId) external payable {
        Model storage model = models[_modelId];
        require(model.exists, "Model does not exist");
        require(!hasPurchased[_modelId][msg.sender], "Already purchased");
        require(msg.value >= model.priceWei, "Insufficient payment");

        // Record purchase
        hasPurchased[_modelId][msg.sender] = true;
        model.totalPurchases += 1;

        purchaseHistory[_modelId].push(Purchase({
            buyer:     msg.sender,
            paidWei:   msg.value,
            timestamp: block.timestamp
        }));

        // Transfer payment to model owner
        if (msg.value > 0) {
            (bool sent,) = payable(model.owner).call{value: msg.value}("");
            require(sent, "ETH transfer to owner failed");
        }

        emit ModelPurchased(_modelId, msg.sender, model.owner, msg.value);
    }

    // ─── Update Price ─────────────────────────────────────────
    /**
     * @notice Model owner can update the price of their model.
     */
    function updatePrice(string calldata _modelId, uint256 _newPriceWei)
        external
        onlyModelOwner(_modelId)
    {
        uint256 oldPrice = models[_modelId].priceWei;
        models[_modelId].priceWei = _newPriceWei;
        emit ModelPriceUpdated(_modelId, oldPrice, _newPriceWei);
    }

    // ─── Views ────────────────────────────────────────────────
    function getModel(string calldata _modelId)
        external view
        returns (
            string memory ipfsHash,
            string memory metadataHash,
            address owner,
            uint256 priceWei,
            uint256 totalPurchases,
            bool exists_
        )
    {
        Model storage m = models[_modelId];
        return (m.ipfsHash, m.metadataHash, m.owner, m.priceWei, m.totalPurchases, m.exists);
    }

    function getTotalModels() external view returns (uint256) {
        return allModelIds.length;
    }

    function getOwnerModelCount(address _owner) external view returns (uint256) {
        return ownerModels[_owner].length;
    }

    function getPurchaseCount(string calldata _modelId) external view returns (uint256) {
        return purchaseHistory[_modelId].length;
    }

    /**
     * @notice Check if a buyer has purchased a specific model.
     */
    function checkPurchase(string calldata _modelId, address _buyer) external view returns (bool) {
        return hasPurchased[_modelId][_buyer];
    }
}
