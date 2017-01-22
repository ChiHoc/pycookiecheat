# -*- coding: utf-8 -*-
"""pyCookieCheat.py
See relevant post at http://n8h.me/HufI1w

Use your browser's cookies to make grabbing data from login-protected sites
easier. Intended for use with Python Requests http://python-requests.org

Accepts a URL from which it tries to extract a domain. If you want to force the
domain, just send it the domain you'd like to use instead.

Adapted from my code at http://n8h.me/HufI1w

"""

import os.path
import sqlite3
import sys

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher
from cryptography.hazmat.primitives.ciphers.algorithms import AES
from cryptography.hazmat.primitives.ciphers.modes import CBC
from cryptography.hazmat.primitives.hashes import SHA1
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import keyring

try:
    from urllib.error import URLError
    from urllib.parse import urlparse
except ImportError:
    from urllib2 import URLError
    from urlparse import urlparse


def chrome_cookies(url, cookie_file=None):

    def decrypt(value, encrypted_value, key=None):

        # Mac or Linux
        if (sys.platform == 'darwin') or sys.platform.startswith('linux'):
            if value or (encrypted_value[:3] != b'v10'):
                return value
            else:
                return aes_decrypt(encrypted_value, key)

        # Windows
        elif sys.platform.startswith('win32'):
            try:
                import win32crypt
            except ImportError:
                raise BrowserCookieError('win32crypt must be available to decrypt Chrome cookie on Windows')
            data = win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)[1].decode("utf-8")
            return data

        else:
            raise OSError("Unknown platform.")


    def aes_decrypt(encrypted_value, key=None):

        iv = b' ' * 16

        # Encrypted cookies should be prefixed with 'v10' according to the
        # Chromium code. Strip it off.
        encrypted_value = encrypted_value[3:]

        # Strip padding by taking off number indicated by padding
        # eg if last is '\x0e' then ord('\x0e') == 14, so take off 14.
        def clean(x):
            last = x[-1]
            if isinstance(last, int):
                return x[:-last].decode('utf8')
            else:
                return x[:-ord(last)].decode('utf8')

        cipher = Cipher(
            algorithm=AES(key),
            mode=CBC(iv),
            backend=default_backend(),
        )
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(encrypted_value) + decryptor.finalize()

        return clean(decrypted)

    # Generate key from values
    def generate_aes_decrypt_key(my_pass, iterations):

        salt = b'saltysalt'
        length = 16

        kdf = PBKDF2HMAC(
            algorithm=SHA1(),
            length=length,
            salt=salt,
            iterations=iterations,
            backend=default_backend(),
        )
        return kdf.derive(bytes(my_pass))

    # If running Chrome on OSX
    if sys.platform == 'darwin':
        key = generate_aes_decrypt_key(keyring.get_password('Chrome Safe Storage', 'Chrome').encode('utf8'), 1003)
        cookie_file = cookie_file or os.path.expanduser(
            u'~/Library/Application Support/Google/Chrome/Default/Cookies'
        )

    # If running Chromium on Linux
    elif sys.platform.startswith('linux'):
        key = generate_aes_decrypt_key('peanuts'.encode('utf8'), 1)
        cookie_file = cookie_file or os.path.expanduser(
            u'~/.config/chromium/Default/Cookies'
        )

    # If running Chrome on Windows
    elif sys.platform.startswith('win32'):
        key = None
        cookie_file = cookie_file or os.path.expanduser(
            u'~\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\Cookies'
        )

    else:
        raise OSError("Unknown platform.")

    parsed_url = urlparse(url)

    if not parsed_url.scheme:
        raise URLError("You must include a scheme with your URL")
    domain = urlparse(url).netloc

    conn = sqlite3.connect(cookie_file)

    sql = 'select name, value, encrypted_value from cookies where host_key '\
          'like ?'

    cookies = {}

    for host_key in generate_host_keys(domain):
        print(host_key)
        cookies_list = []
        for k, v, ev in conn.execute(sql, (host_key,)):
            # if there is a not encrypted value or if the encrypted value
            # doesn't start with the 'v10' prefix, return v
            decrypted_tuple = (k, decrypt(v, ev, key=key))
            cookies_list.append(decrypted_tuple)
        cookies.update(cookies_list)

    conn.rollback()
    return cookies


def generate_host_keys(hostname):
    """Yield Chrome keys for `hostname`, from least to most specific.

    Given a hostname like foo.example.com, this yields the key sequence:

    example.com
    .example.com
    foo.example.com
    .foo.example.com

    """
    labels = hostname.split('.')
    for i in range(2, len(labels) + 1):
        domain = '.'.join(labels[-i:])
        yield domain
        yield '.' + domain
