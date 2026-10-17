"""Generate VAPID keys locally. Requires pip install cryptography."""
import base64
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
private = ec.generate_private_key(ec.SECP256R1())
public = private.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
print('VAPID_PUBLIC_KEY=' + base64.urlsafe_b64encode(public).rstrip(b'=').decode())
print('VAPID_PRIVATE_KEY (paste multiline PEM as secret):')
print(private.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode())
