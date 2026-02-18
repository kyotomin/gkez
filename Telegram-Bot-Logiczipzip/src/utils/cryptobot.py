import logging

from aiocryptopay import AioCryptoPay, Networks
from src.config import CRYPTO_BOT_TOKEN

logger = logging.getLogger(__name__)

_crypto: AioCryptoPay | None = None


def get_crypto() -> AioCryptoPay | None:
    global _crypto
    if not CRYPTO_BOT_TOKEN:
        return None
    if _crypto is None:
        _crypto = AioCryptoPay(token=CRYPTO_BOT_TOKEN, network=Networks.MAIN_NET)
    return _crypto


async def create_invoice(amount: float, description: str = "", expires_in: int = 1800) -> dict | None:
    crypto = get_crypto()
    if not crypto:
        return None
    try:
        invoice = await crypto.create_invoice(
            asset="USDT",
            amount=amount,
            description=description,
            expires_in=expires_in,
        )
        return {
            "invoice_id": invoice.invoice_id,
            "bot_invoice_url": invoice.bot_invoice_url,
            "status": invoice.status,
        }
    except Exception as e:
        logger.error(f"CRYPTO: create_invoice failed: {e}")
        return None


async def check_invoice_paid(invoice_id: int) -> bool:
    crypto = get_crypto()
    if not crypto:
        return False
    try:
        invoices = await crypto.get_invoices(invoice_ids=[invoice_id])
        if invoices:
            inv = invoices[0] if isinstance(invoices, list) else invoices
            return inv.status == "paid"
    except Exception as e:
        logger.warning(f"CRYPTO: check_invoice_paid({invoice_id}) error: {e}")
    return False


async def close_crypto_session():
    global _crypto
    if _crypto:
        await _crypto.close()
        _crypto = None
