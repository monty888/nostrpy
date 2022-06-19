"""
    code to support encrpted notes using ECDH as NIP4
"""

# FIXME: chenage to use cipher from cryptography so we dont need both Crypto and cryptography
import os
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
import secp256k1
from enum import Enum


# TODO: sort something out about the different key formats....
class KeyEnc(Enum):
    BYTES = 1
    HEX = 2


class Keys:

    @staticmethod
    def get_new_key_pair(priv_key=None):
        """
        :param priv_key: private key in hex str format
        where priv_key is not supplied a new priv key is generated

        :return:
        {
            priv_k : hex_str
            pub_k : hex_str
        }
        """
        if priv_key is None:
            pk = secp256k1.PrivateKey()
        else:
            pk = secp256k1.PrivateKey(bytes(bytearray.fromhex(priv_key)), raw=True)

        return {
            'priv_k': pk.serialize(),
            # note pub_k has 02 prefix that you'll probablly want to remove
            'pub_k': pk.pubkey.serialize(compressed=True).hex()
        }

    @staticmethod
    def is_key(key_str):
        """
        check that the string looks like a valid nostr pubkey in hex format
        """
        ret = False
        if len(key_str) == 64:
            # and also hex, will throw otherwise
            try:
                bytearray.fromhex(key_str)
                ret = True
            except:
                pass
        return ret


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

    @property
    def public_key_hex(self):
        return self.public_key_bytes.hex()

    @property
    def public_key_bytes(self):
        return self._pub_key.public_bytes(encoding=serialization.Encoding.X962,
                                          format=serialization.PublicFormat.CompressedPoint)

    def derive_shared_key(self, pub_key_hex, as_type=KeyEnc.HEX):
        pk = secp256k1.PublicKey()
        if len(pub_key_hex) == 64:
            pub_key_hex = '02' + pub_key_hex

        pk.deserialize(bytes.fromhex(pub_key_hex))
        pub_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256K1(), pk.serialize(False))
        self._shared_key = self._key.exchange(ec.ECDH(), pub_key)

        # added return so we don't have to do as 2 step all the time
        return self.shared_key(as_type)

    def shared_key(self, as_type=KeyEnc.HEX):
        if self._shared_key is None:
            raise Exception('SharedEncrypt::shared_key hasn\'t been derived yet')

        ret = self._shared_key
        if as_type == KeyEnc.HEX:
            ret = self._shared_key.hex()

        return ret

    def encrypt_message(self, data, pub_key_hex=None):
        if pub_key_hex is not None:
            self.derive_shared_key(pub_key_hex)

        key = secp256k1.PrivateKey().deserialize(self.shared_key(as_type=KeyEnc.HEX))
        # iv = get_random_bytes(16)
        iv = os.urandom(16)
        # data = Padding.pad(data, 16)
        padder = padding.PKCS7(128).padder()
        data = padder.update(data)
        data += padder.finalize()

        # cipher = AES.new(key, AES.MODE_CBC, iv)
        ciper = Cipher(algorithms.AES(key), modes.CBC(iv))
        encryptor = ciper.encryptor()

        return {
            'text': encryptor.update(data) + encryptor.finalize(),
            'iv': iv,
            'shared_key': self._shared_key
        }

    def decrypt_message(self, encrypted_data,iv, pub_key_hex=None):
        if pub_key_hex is not None:
            self.derive_shared_key(pub_key_hex)

        key = secp256k1.PrivateKey().deserialize(self.shared_key(as_type=KeyEnc.HEX))
        ciper = Cipher(algorithms.AES(key), modes.CBC(iv))
        decryptor = ciper.decryptor()

        ret = decryptor.update(encrypted_data)
        padder = padding.PKCS7(128).unpadder()
        ret = padder.update(ret)
        ret += padder.finalize()

        return ret