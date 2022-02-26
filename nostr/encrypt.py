"""
    code to support encrpted notes using ECDH as NIP4
"""

# FIXME: chenage to use cipher from cryptography so we dont need both Crypto and cryptography
from Crypto.Cipher import AES                   # REPLACE with equivs...
from Crypto.Util import Padding                 # REPLACE
from Crypto.Random import get_random_bytes      # REPLACE
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
import secp256k1
from enum import Enum

# TODO: sort something out about the different key formats....
class KeyEnc(Enum):
    BYTES = 1
    HEX = 2

class SharedEncrypt:
    def __init__(self, priv_k_hex):
        """
        :param priv_k_hex:              our private key
        TODO: take a look at priv_k and try to create and work out from it

        """

        # us, hex, int and key
        self._priv_hex = priv_k_hex
        self._priv_int = int(priv_k_hex, 16)
        self._key = ec.derive_private_key(self._priv_int, ec.SECP256K1())
        # our public key for priv key
        self._pub_key = self._key.public_key()
        # shared key for priv/pub ECDH
        self._shared_key = None

    def get_keys(self, as_type=KeyEnc.HEX):
        pass

    @property
    def public_key_hex(self):
        return self.public_key_bytes.hex()

    @property
    def public_key_bytes(self):
        return self._pub_key.public_bytes(encoding=serialization.Encoding.X962,
                                          format=serialization.PublicFormat.CompressedPoint)

    def derive_shared_key(self, pub_key_hex):
        pk = secp256k1.PublicKey()
        # pk.deserialize(bytes.fromhex('02' + pub_key_hex))
        pk.deserialize(bytes.fromhex(pub_key_hex))
        pub_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256K1(), pk.serialize(False))
        self._shared_key = self._key.exchange(ec.ECDH(), pub_key)

    def shared_key(self, as_type=KeyEnc.HEX):
        if self._shared_key is None:
            raise Exception('SharedEncrypt::shared_key hasn\'t been derived yet')

        ret = self._shared_key
        if as_type==KeyEnc.HEX:
            ret = self._shared_key.hex()

        return ret

    def encrypt_message(self, data, pub_key_hex=None):
        if pub_key_hex is not None:
            self.derive_shared_key(pub_key_hex)

        key = secp256k1.PrivateKey().deserialize(self.shared_key(as_type=KeyEnc.HEX))
        iv = get_random_bytes(16)
        data = Padding.pad(data, 16)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        return {
            'text' : cipher.encrypt(data),
            'iv' : iv,
            'shared_key' : self._shared_key
        }

    def decrypt_message(self, encrypted_data,iv, pub_key_hex=None):
        if pub_key_hex is not None:
            self.get_shared_key(pub_key_hex)

        key = secp256k1.PrivateKey().deserialize(self.shared_key(as_type=KeyEnc.HEX))
        cipher = AES.new(key, AES.MODE_CBC, iv)
        ret = cipher.decrypt(encrypted_data)
        ret = Padding.unpad(ret,16)
        return ret