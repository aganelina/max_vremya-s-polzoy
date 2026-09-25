import datetime as dt
from functools import cache
from io import BytesIO
from pathlib import Path

import structlog
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pyhanko.keys import (
    load_certs_from_pemder_data,
    load_private_key_from_pemder_data,
)
from pyhanko.pdf_utils.incremental_writer import (
    IncrementalPdfFileWriter,
)
from pyhanko.sign import fields, signers
from pyhanko_certvalidator.registry import (
    SimpleCertificateStore,
)

from app.config import get_settings
from app.domain.participant_settings import participant_settings

log = structlog.get_logger("certificate")

def generate_self_signed(common_name: str = "Vremya s polzoy (dev)") -> tuple[bytes, bytes]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Vremya s polzoy"),
        ]
    )
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=3650))
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=True,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return key_pem, cert.public_bytes(serialization.Encoding.PEM)

@cache
def _signer() -> signers.SimpleSigner | None:
    ps = participant_settings()
    if ps.cert_sign_key_path and ps.cert_sign_cert_path:
        key_pem = Path(ps.cert_sign_key_path).read_bytes()
        cert_pem = Path(ps.cert_sign_cert_path).read_bytes()
        passphrase = ps.cert_sign_key_passphrase.encode() or None
    elif get_settings().dev_auth_enabled:
        key_pem, cert_pem = generate_self_signed()
        passphrase = None
    else:
        log.warning("certificate_signing_disabled")
        return None
    certs = list(load_certs_from_pemder_data(cert_pem))
    key = load_private_key_from_pemder_data(key_pem, passphrase=passphrase)
    return signers.SimpleSigner(
        signing_cert=certs[0],
        signing_key=key,
        cert_registry=SimpleCertificateStore.from_certs(certs),  # type: ignore[no-untyped-call]
    )

def reset_signer() -> None:
    _signer.cache_clear()

def sign_pdf(pdf: bytes) -> bytes:
    signer = _signer()
    if signer is None:
        return pdf
    writer = IncrementalPdfFileWriter(BytesIO(pdf))
    meta = signers.PdfSignatureMetadata(
        field_name="Signature",
        subfilter=fields.SigSeedSubFilter.PADES,
        reason="Справка о волонтёрских часах",
        name="Время с пользой",
    )
    out = signers.sign_pdf(writer, meta, signer=signer)
    return bytes(out.getvalue())
