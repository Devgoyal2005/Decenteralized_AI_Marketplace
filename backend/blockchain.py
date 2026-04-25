"""
Blockchain (Web3) helpers — contract interaction, signature verification, on-chain usage recording.
"""
from typing import Any, Dict

from fastapi import HTTPException
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct

from backend.config import (
    WEB3_RPC_URL,
    MODEL_LICENSE_ADDRESS,
    MODEL_LICENSE_ABI_MIN,
    MODEL_LICENSE_MAX_USE_GAS,
    MODEL_LICENSE_TX_TIMEOUT,
    BACKEND_SIGNER_PRIVATE_KEY,
)


def _normalized_private_key(raw: str) -> str:
    key = (raw or "").strip()
    if not key:
        return ""
    with_prefix = key if key.startswith("0x") else f"0x{key}"
    return with_prefix if len(with_prefix) == 66 else ""


def _get_model_license_contract():
    if not WEB3_RPC_URL:
        raise HTTPException(status_code=500, detail="WEB3_RPC_URL is not configured")
    if not MODEL_LICENSE_ADDRESS:
        raise HTTPException(status_code=500, detail="MODEL_LICENSE_ADDRESS is not configured")

    w3 = Web3(Web3.HTTPProvider(WEB3_RPC_URL, request_kwargs={"timeout": MODEL_LICENSE_TX_TIMEOUT}))
    if not w3.is_connected():
        raise HTTPException(status_code=502, detail="Unable to connect to WEB3_RPC_URL")
    if not Web3.is_address(MODEL_LICENSE_ADDRESS):
        raise HTTPException(status_code=500, detail="MODEL_LICENSE_ADDRESS is invalid")

    contract = w3.eth.contract(
        address=Web3.to_checksum_address(MODEL_LICENSE_ADDRESS),
        abi=MODEL_LICENSE_ABI_MIN,
    )
    return w3, contract


def _verify_license_for_model(model_id: str, wallet_address: str, token_id: int) -> Dict[str, Any]:
    w3, contract = _get_model_license_contract()

    if not Web3.is_address(wallet_address):
        raise HTTPException(status_code=400, detail="wallet_address is invalid")

    try:
        usable, reason = contract.functions.isLicenseUsable(
            int(token_id), Web3.to_checksum_address(wallet_address), model_id
        ).call()
        if not usable:
            raise HTTPException(status_code=403, detail=f"License not usable: {reason}")

        status = contract.functions.getLicenseStatus(int(token_id)).call()
        # Check if the license owner is the zero address, which indicates non-existence
        if str(status[1]) == "0x0000000000000000000000000000000000000000":
            raise HTTPException(status_code=404, detail="License does not exist")
    except HTTPException:
        raise
    except Exception as exc:
        # Check if the error message indicates the token does not exist
        if "invalid token ID" in str(exc) or "URI query for nonexistent token" in str(exc):
            raise HTTPException(status_code=404, detail="License does not exist")
        raise HTTPException(status_code=502, detail=f"Failed to verify license on-chain: {exc}")

    return {
        "model_id": str(status[0]),
        "owner": str(status[1]),
        "max_uses": int(status[2]),
        "used_count": int(status[3]),
        "expired": bool(status[4]),
        "metadata_uri": str(status[5]),
    }


def _record_license_use_on_chain(token_id: int) -> str:
    normalized_key = _normalized_private_key(BACKEND_SIGNER_PRIVATE_KEY)
    if not normalized_key:
        raise HTTPException(status_code=500, detail="BACKEND_SIGNER_PRIVATE_KEY is not configured")

    w3, contract = _get_model_license_contract()
    account = Account.from_key(normalized_key)

    try:
        nonce = w3.eth.get_transaction_count(account.address, "pending")
        tx = contract.functions.recordUse(int(token_id)).build_transaction(
            {
                "from": account.address,
                "nonce": nonce,
                "gas": MODEL_LICENSE_MAX_USE_GAS,
                "gasPrice": w3.eth.gas_price,
                "chainId": w3.eth.chain_id,
            }
        )

        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=MODEL_LICENSE_TX_TIMEOUT)
        if receipt.status != 1:
            raise HTTPException(status_code=502, detail="recordUse transaction reverted")
        return tx_hash.hex()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to record license usage on-chain: {exc}")


def verify_personal_signature(wallet: str, signature: str, message: str) -> None:
    """Verify an EIP-191 personal_sign signature matches the claimed wallet address."""
    try:
        w3 = Web3()
        encoded_message = encode_defunct(text=message)
        recovered_address = w3.eth.account.recover_message(encoded_message, signature=signature).lower()
        if recovered_address != wallet.lower():
            raise HTTPException(status_code=403, detail="Invalid signature")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Signature verification failed: {e}")
