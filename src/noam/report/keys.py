"""WP5 — מפתח החתימה של העמדה.

ברירת מחדל זמנית (עד החלטה על TPM, docs/SECURITY.md §1):
קובץ PEM מוצפן (PKCS#8, AES-256) שנפתח בסיסמת מנהל. הסיסמה מוזנת בהפעלה ונשמרת בזיכרון בלבד —
לא בקובץ, לא ב-config, לא ביומן.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

PASSPHRASE_ENV = "NOAM_SIGNING_PASSPHRASE"
MIN_PASSPHRASE = 12


def fingerprint(public_key: ec.EllipticCurvePublicKey) -> str:
    """8 הבתים הראשונים של SHA-256 על המפתח הציבורי (DER), בפורמט 4C:19:AA:…"""
    der = public_key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return ":".join(f"{b:02X}" for b in hashlib.sha256(der).digest()[:8])


def generate_key(path: Path, passphrase: str, station_name: str = "NOAM Station") -> str:
    """יוצר מפתח חדש לעמדה. נכשל אם כבר קיים — החלפת מפתח היא פעולה מכוונת (ידנית)."""
    if len(passphrase) < MIN_PASSPHRASE:
        raise ValueError(f"passphrase must be at least {MIN_PASSPHRASE} characters")
    path = Path(path)
    if path.exists():
        raise FileExistsError("signing key already exists — rotate deliberately")
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(passphrase.encode()),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(pem)
    pub = path.with_suffix(".pub.pem")
    pub.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    _write_certificate(key, path.with_suffix(".crt"), station_name)
    return fingerprint(key.public_key())


def cert_path(key_path: Path) -> Path:
    return Path(key_path).with_suffix(".crt")


def _write_certificate(key: ec.EllipticCurvePrivateKey, out: Path, station_name: str) -> None:
    """תעודה בחתימה עצמית לעמדה — PAdES (pyHanko) דורש תעודה, לא רק מפתח.
    Adobe יציג "חתום, לא שונה"; הזהות תוצג כ"לא מאומתת" עד שמישהו יסמוך על התעודה (או על CA)."""
    from cryptography import x509

    fp = fingerprint(key.public_key())
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, f"{station_name} · NOAM {fp}"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "NOAM"),
        x509.NameAttribute(NameOID.COUNTRY_NAME, "IL"),
    ])
    now = _dt.datetime.now(_dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - _dt.timedelta(days=1))
        .not_valid_after(now + _dt.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(True, True, False, False, False, False, False, False, False), critical=True)
        .sign(key, hashes.SHA256())
    )
    out.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def load_public_key(path: Path) -> ec.EllipticCurvePublicKey:
    key = serialization.load_pem_public_key(Path(path).read_bytes())
    if not isinstance(key, ec.EllipticCurvePublicKey):
        raise TypeError("not an EC public key")
    return key


class SigningKey:
    def __init__(self, private_key: ec.EllipticCurvePrivateKey, path: Path | None = None,
                 passphrase: str | None = None) -> None:
        self._key = private_key
        self.path = Path(path) if path else None
        self._pw = passphrase  # בזיכרון בלבד — pyHanko צריך לטעון את הקובץ בעצמו
        self.public_key = private_key.public_key()
        self.fingerprint = fingerprint(self.public_key)

    @classmethod
    def load(cls, path: Path, passphrase: str | None = None) -> SigningKey:
        """passphrase — מהמנהל בהפעלה; אם חסרה, מ-NOAM_SIGNING_PASSPHRASE. אין ברירת מחדל."""
        pw = passphrase if passphrase is not None else os.environ.get(PASSPHRASE_ENV)
        if not pw:
            raise RuntimeError(f"signing key is locked: provide the admin passphrase ({PASSPHRASE_ENV})")
        try:
            key = serialization.load_pem_private_key(Path(path).read_bytes(), password=pw.encode())
        except ValueError as e:
            raise PermissionError("wrong passphrase or corrupt key") from e
        if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
            raise TypeError("signing key must be ECDSA P-256")
        return cls(key, path, pw)

    def sign(self, data: bytes) -> bytes:
        return self._key.sign(data, ec.ECDSA(hashes.SHA256()))


def verify_bytes(public_key: ec.EllipticCurvePublicKey, data: bytes, signature: bytes) -> bool:
    try:
        public_key.verify(signature, data, ec.ECDSA(hashes.SHA256()))
        return True
    except InvalidSignature:
        return False
