// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC721/extensions/ERC721URIStorage.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

interface IModelRegistry {
    function getModel(string calldata _modelId)
        external
        view
        returns (
            string memory ipfsHash,
            string memory metadataHash,
            address owner,
            uint256 priceWei,
            uint256 totalPurchases,
            bool exists_
        );
}

contract ModelLicense is ERC721URIStorage, Ownable {
    struct LicenseInfo {
        string modelId;
        uint256 maxUses;
        uint256 usedCount;
        bool exists;
    }

    IModelRegistry public immutable modelRegistry;
    address public backendSigner;
    uint256 public nextTokenId;
    uint256 public defaultMaxUses = 1000;

    mapping(uint256 => LicenseInfo) public licenses;
    mapping(string => uint256) public modelMaxUses;
    mapping(address => uint256[]) private ownerTokenIds;
    mapping(string => mapping(address => uint256[])) private ownerModelTokenIds;

    event LicenseMinted(
        uint256 indexed tokenId,
        string indexed modelId,
        address indexed buyer,
        uint256 maxUses,
        uint256 paidWei,
        string metadataUri
    );

    event LicenseUseRecorded(
        uint256 indexed tokenId,
        string indexed modelId,
        uint256 usedCount,
        uint256 maxUses,
        bool expired
    );

    event BackendSignerUpdated(address indexed oldSigner, address indexed newSigner);
    event ModelMaxUsesUpdated(string indexed modelId, uint256 oldMaxUses, uint256 newMaxUses);

    modifier onlyBackendSigner() {
        require(msg.sender == backendSigner, "Only backend signer");
        _;
    }

    constructor(address _registryAddress, address _backendSigner)
        ERC721("DAMM Model License", "DAMML")
        Ownable()
    {
        require(_registryAddress != address(0), "Registry address required");
        require(_backendSigner != address(0), "Backend signer required");
        modelRegistry = IModelRegistry(_registryAddress);
        backendSigner = _backendSigner;
    }

    function setBackendSigner(address _newSigner) external onlyOwner {
        require(_newSigner != address(0), "Backend signer required");
        address oldSigner = backendSigner;
        backendSigner = _newSigner;
        emit BackendSignerUpdated(oldSigner, _newSigner);
    }

    function setDefaultMaxUses(uint256 _defaultMaxUses) external onlyOwner {
        require(_defaultMaxUses > 0, "Default maxUses must be > 0");
        defaultMaxUses = _defaultMaxUses;
    }

    function setModelMaxUses(string calldata _modelId, uint256 _maxUses) external onlyOwner {
        require(bytes(_modelId).length > 0, "Model ID required");
        require(_maxUses > 0, "maxUses must be > 0");
        uint256 oldValue = modelMaxUses[_modelId];
        modelMaxUses[_modelId] = _maxUses;
        emit ModelMaxUsesUpdated(_modelId, oldValue, _maxUses);
    }

    function mintLicense(string calldata _modelId, string calldata _metadataUri)
        external
        payable
        returns (uint256 tokenId)
    {
        require(bytes(_modelId).length > 0, "Model ID required");
        require(bytes(_metadataUri).length > 0, "Metadata URI required");

        (
            ,
            ,
            address modelOwner,
            uint256 modelPriceWei,
            ,
            bool exists_
        ) = modelRegistry.getModel(_modelId);

        require(exists_, "Model does not exist in registry");
        require(modelOwner != address(0), "Model owner missing");
        require(msg.value >= modelPriceWei, "Insufficient payment");

        uint256 maxUses = modelMaxUses[_modelId];
        if (maxUses == 0) {
            maxUses = defaultMaxUses;
        }

        tokenId = ++nextTokenId;
        _safeMint(msg.sender, tokenId);
        _setTokenURI(tokenId, _metadataUri);

        licenses[tokenId] = LicenseInfo({
            modelId: _modelId,
            maxUses: maxUses,
            usedCount: 0,
            exists: true
        });

        ownerTokenIds[msg.sender].push(tokenId);
        ownerModelTokenIds[_modelId][msg.sender].push(tokenId);

        if (msg.value > 0) {
            (bool sent, ) = payable(modelOwner).call{value: msg.value}("");
            require(sent, "ETH transfer failed");
        }

        emit LicenseMinted(tokenId, _modelId, msg.sender, maxUses, msg.value, _metadataUri);
    }

    function recordUse(uint256 _tokenId) external onlyBackendSigner {
        LicenseInfo storage lic = licenses[_tokenId];
        require(lic.exists, "License does not exist");
        require(_exists(_tokenId), "License burned");
        require(lic.usedCount < lic.maxUses, "License exhausted");

        lic.usedCount += 1;

        emit LicenseUseRecorded(
            _tokenId,
            lic.modelId,
            lic.usedCount,
            lic.maxUses,
            lic.usedCount >= lic.maxUses
        );
    }

    function isLicenseUsable(uint256 _tokenId, address _wallet, string calldata _modelId)
        external
        view
        returns (bool usable, string memory reason)
    {
        LicenseInfo storage lic = licenses[_tokenId];
        if (!lic.exists) return (false, "License does not exist");
        if (!_exists(_tokenId)) return (false, "License burned");
        if (ownerOf(_tokenId) != _wallet) return (false, "Wallet does not own token");
        if (keccak256(bytes(lic.modelId)) != keccak256(bytes(_modelId))) {
            return (false, "Token is for another model");
        }
        if (lic.usedCount >= lic.maxUses) return (false, "License exhausted");
        return (true, "OK");
    }

    function getLicenseStatus(uint256 _tokenId)
        external
        view
        returns (
            string memory modelId,
            address owner,
            uint256 maxUses,
            uint256 usedCount,
            bool expired,
            string memory metadataUri
        )
    {
        LicenseInfo storage lic = licenses[_tokenId];
        require(lic.exists, "License does not exist");
        modelId = lic.modelId;
        owner = ownerOf(_tokenId);
        maxUses = lic.maxUses;
        usedCount = lic.usedCount;
        expired = usedCount >= maxUses;
        metadataUri = tokenURI(_tokenId);
    }

    function getOwnedLicensesForModel(address _owner, string calldata _modelId)
        external
        view
        returns (uint256[] memory)
    {
        return ownerModelTokenIds[_modelId][_owner];
    }

    function getOwnedLicenseTokenIds(address _owner)
        external
        view
        returns (uint256[] memory)
    {
        return ownerTokenIds[_owner];
    }
}
