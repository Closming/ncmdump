import struct
import os
import sys
import json
import glob

CORE_KEY = bytes([
    0x68, 0x7A, 0x48, 0x52, 0x41, 0x6D, 0x73, 0x6F,
    0x35, 0x6B, 0x49, 0x6E, 0x63, 0x7A, 0x31, 0x37
])

META_KEY = bytes([
    0x23, 0x31, 0x34, 0x6B, 0x81, 0x33, 0x72, 0x79,
    0x6D, 0x75, 0x73, 0x69, 0x63
])


def convert_ncm(filepath):
    with open(filepath, 'rb') as f:
        data = f.read()

    if data[:8] != b'CTENFDAM':
        print(f"[SKIP] Not a valid NCM file: {os.path.basename(filepath)}")
        return False

    # Read key data block length
    key_length = struct.unpack('<I', data[10:14])[0]

    # Extract and decrypt the key data block
    key_data = bytearray(data[14:14 + key_length])

    # XOR decrypt with CORE_KEY
    for i in range(len(key_data)):
        key_data[i] ^= CORE_KEY[i % len(CORE_KEY)]

    # XOR first bytes with META_KEY
    for i in range(min(len(META_KEY), len(key_data))):
        key_data[i] ^= META_KEY[i]

    # Parse the decrypted key data structure
    meta_len = struct.unpack('<I', key_data[0:4])[0]
    meta_json = key_data[4:4 + meta_len].decode('utf-8', errors='replace').rstrip('\x00')
    meta = json.loads(meta_json)

    # Navigate to the music decrypt key
    offset = 4 + meta_len   # skip length field + JSON
    offset += 4             # skip CRC32
    offset += 1             # skip gap byte

    # Album image (if present)
    if offset + 4 <= len(key_data):
        album_size = struct.unpack('<I', key_data[offset:offset + 4])[0]
        offset += 4 + album_size

    # The remaining bytes are the music decrypt key
    music_key = bytes(key_data[offset:])

    if not music_key:
        print(f"[SKIP] No decrypt key found: {os.path.basename(filepath)}")
        return False

    # Determine output format from metadata
    data_format = meta.get('format', 'mp3')
    out_path = filepath.rsplit('.ncm', 1)[0] + '.' + data_format

    # Audio data starts after the key data block
    audio_data = data[14 + key_length:]

    # Decrypt using RC4-like algorithm (same as ncmdump)
    S = bytearray(range(256))
    j = 0
    for i in range(256):
        j = (j + S[i] + music_key[i % len(music_key)]) & 0xFF
        S[i], S[j] = S[j], S[i]

    result = bytearray(len(audio_data))
    x = 0
    y = 0
    for i in range(len(audio_data)):
        if i == 0:
            result[i] = audio_data[i] ^ 0x64
        else:
            x = (x + 1) & 0xFF
            y = (y + S[x]) & 0xFF
            S[x], S[y] = S[y], S[x]
            result[i] = audio_data[i] ^ S[(S[x] + S[y]) & 0xFF]

    with open(out_path, 'wb') as f:
        f.write(result)

    print(f"[OK] {os.path.basename(filepath)} -> {os.path.basename(out_path)}")
    return True


def main():
    # Find all .ncm files in current directory
    ncm_files = glob.glob("*.ncm")
    if not ncm_files:
        print("No .ncm files found in current directory.")
        return

    print(f"Found {len(ncm_files)} .ncm file(s)\n")
    success = 0
    for f in sorted(ncm_files):
        if convert_ncm(f):
            success += 1

    print(f"\nDone: {success}/{len(ncm_files)} converted.")


if __name__ == '__main__':
    main()
