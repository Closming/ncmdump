import os
import struct
import base64
import json
import tkinter as tk
from tkinter import ttk, filedialog

# ── NCM conversion ───────────────────────────────────────────
CORE_KEY = bytes.fromhex("687A4852416D736F356B496E62617857")
META_KEY = bytes.fromhex("2331346C6A6B5F215C5D2630553C2728")


def convert_ncm(filepath):
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad

    with open(filepath, "rb") as f:
        data = f.read()

    if data[:8] != b"CTENFDAM":
        raise ValueError("不是有效的 NCM 文件")

    offset = 10

    # decrypt key → RC4 key
    key_len = int.from_bytes(data[offset : offset + 4], "little")
    offset += 4
    key_block = bytearray(data[offset : offset + key_len])
    offset += key_len
    for i in range(len(key_block)):
        key_block[i] ^= 0x64
    key_block = unpad(AES.new(CORE_KEY, AES.MODE_ECB).decrypt(bytes(key_block)), 16)
    rc4_key = key_block[17:]

    # RC4 KSA
    S = bytearray(range(256))
    j = 0
    for i in range(256):
        j = (j + S[i] + rc4_key[i % len(rc4_key)]) & 0xFF
        S[i], S[j] = S[j], S[i]

    # metadata
    meta_len = int.from_bytes(data[offset : offset + 4], "little")
    offset += 4
    meta_format = "mp3"
    if meta_len:
        meta_block = bytearray(data[offset : offset + meta_len])
        offset += meta_len
        for i in range(len(meta_block)):
            meta_block[i] ^= 0x63
        raw = base64.b64decode(bytes(meta_block[22:]))
        raw = unpad(AES.new(META_KEY, AES.MODE_ECB).decrypt(raw), 16)
        meta = json.loads(raw[6:].decode("utf-8"))
        meta_format = meta.get("format", "mp3")

    # skip CRC32(4) + gap(1)
    offset += 5
    img_space = int.from_bytes(data[offset : offset + 4], "little")
    offset += 4
    img_size = int.from_bytes(data[offset : offset + 4], "little")
    offset += 4
    img_data = data[offset : offset + img_size] if img_size else None
    offset += img_space

    # decrypt audio
    audio = data[offset:]
    stream = bytearray()
    for i in range(256):
        stream.append(S[(S[i] + S[(i + S[i]) & 0xFF]) & 0xFF])
    full_stream = bytes(stream * ((len(audio) // 256) + 2))[1 : 1 + len(audio)]
    audio = bytes(a ^ s for a, s in zip(audio, full_stream))

    out_path = os.path.splitext(filepath)[0] + "." + meta_format
    with open(out_path, "wb") as f:
        f.write(audio)

    # embed cover art
    if img_data:
        try:
            from mutagen import mp3 as mmp3, flac, id3

            if meta_format == "flac":
                af = flac.FLAC(out_path)
                pic = flac.Picture()
                pic.encoding = 0
                pic.type = 3
                pic.mime = "image/png" if img_data[:4] == b"\x89PNG" else "image/jpeg"
                pic.data = img_data
                af.clear_pictures()
                af.add_picture(pic)
                af.save()
            else:
                af = mmp3.MP3(out_path)
                apic = id3.APIC()
                apic.encoding = 0
                apic.type = 6
                apic.mime = "image/png" if img_data[:4] == b"\x89PNG" else "image/jpeg"
                apic.data = img_data
                af.tags.add(apic)
                af.save()
        except Exception:
            pass

    return os.path.basename(out_path)


# ── GUI ───────────────────────────────────────────────────────


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("NCM 转换器")
        self.root.geometry("660x520")
        self.root.minsize(520, 380)
        self.root.configure(bg="#f5f5f5")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._queue = []       # list of (iid, path), processed sequentially
        self._busy = False
        self._jobs = {}        # iid -> {name, path, status, output}

        self._build()
        self._process()

    # ── UI ─────────────────────────────────────────────────
    def _build(self):
        # title bar
        h = tk.Frame(self.root, bg="#f5f5f5")
        h.pack(fill="x", padx=28, pady=(24, 0))
        tk.Label(
            h,
            text="NCM 转换器",
            font=("Microsoft YaHei UI", 20, "bold"),
            bg="#f5f5f5",
            fg="#222",
        ).pack(anchor="w")
        tk.Label(
            h,
            text="网易云音乐加密文件 → MP3 / FLAC",
            font=("Microsoft YaHei UI", 10),
            bg="#f5f5f5",
            fg="#888",
        ).pack(anchor="w")

        # drop zone
        zo = tk.Frame(self.root, bg="#e0e0e0")
        zo.pack(fill="x", padx=28, pady=(18, 12))

        self.zone = tk.Frame(zo, bg="#ffffff", cursor="hand2")
        self.zone.pack(fill="x", padx=2, pady=2, ipady=34)

        self.zone_lbl = tk.Label(
            self.zone,
            text="点击此处选择 .ncm 文件",
            font=("Microsoft YaHei UI", 13),
            bg="#ffffff",
            fg="#999",
            justify="center",
            cursor="hand2",
        )
        self.zone_lbl.pack(expand=True)

        # bind click
        self.zone.bind("<Button-1>", self._browse)
        self.zone_lbl.bind("<Button-1>", self._browse)

        # hover
        self.zone.bind("<Enter>", lambda e: self.zone.configure(bg="#f0f6ff"))
        self.zone.bind("<Leave>", lambda e: self.zone.configure(bg="#ffffff"))
        self.zone_lbl.bind("<Enter>", lambda e: (
            self.zone.configure(bg="#f0f6ff"),
            self.zone_lbl.configure(bg="#f0f6ff"),
        ))
        self.zone_lbl.bind("<Leave>", lambda e: (
            self.zone.configure(bg="#ffffff"),
            self.zone_lbl.configure(bg="#ffffff"),
        ))

        # list header
        lh = tk.Frame(self.root, bg="#f5f5f5")
        lh.pack(fill="x", padx=28, pady=(6, 2))
        tk.Label(
            lh,
            text="转换列表",
            font=("Microsoft YaHei UI", 12, "bold"),
            bg="#f5f5f5",
            fg="#222",
        ).pack(side="left")
        self.cnt = tk.Label(
            lh,
            text="",
            font=("Microsoft YaHei UI", 9),
            bg="#f5f5f5",
            fg="#999",
        )
        self.cnt.pack(side="right")

        # treeview
        tvf = tk.Frame(self.root, bg="#ffffff")
        tvf.pack(fill="both", expand=True, padx=28, pady=(0, 20))

        cols = ("fn", "st", "out")
        self.tv = ttk.Treeview(tvf, columns=cols, show="headings", height=9)
        self.tv.heading("fn", text="文件名")
        self.tv.heading("st", text="状态")
        self.tv.heading("out", text="输出")
        self.tv.column("fn", width=280, minwidth=120)
        self.tv.column("st", width=100, minwidth=60)
        self.tv.column("out", width=200, minwidth=80)

        sb = ttk.Scrollbar(tvf, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        s = ttk.Style()
        s.theme_use("clam")
        s.configure("Treeview", background="#fff", fieldbackground="#fff", rowheight=30)
        s.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"))
        self.tv.tag_configure("ok", foreground="#27ae60")
        self.tv.tag_configure("err", foreground="#e74c3c")
        self.tv.tag_configure("ing", foreground="#1677ff")

    # ── events ────────────────────────────────────────────
    def _browse(self, event=None):
        files = filedialog.askopenfilenames(
            title="选择 NCM 文件",
            filetypes=[("NCM 文件", "*.ncm"), ("所有文件", "*.*")],
        )
        for f in files:
            self._enqueue(f)

    def _on_close(self):
        self.root.destroy()

    # ── job queue ──────────────────────────────────────────
    def _enqueue(self, path):
        name = os.path.basename(path)
        # skip duplicates
        for info in self._jobs.values():
            if info["path"] == path:
                return
        iid = self.tv.insert("", "end", values=(name, "等待中", ""))
        self._jobs[iid] = {"name": name, "path": path}
        self._queue.append(iid)
        self._refresh_count()

    def _process(self):
        """Process one file per tick on the main thread."""
        if not self._busy and self._queue:
            self._busy = True
            iid = self._queue.pop(0)
            info = self._jobs[iid]

            self.tv.set(iid, "st", "转换中")
            self.tv.item(iid, tags=("ing",))

            def do_work():
                try:
                    out = convert_ncm(info["path"])
                    self.tv.set(iid, "st", "完成")
                    self.tv.set(iid, "out", out)
                    self.tv.item(iid, tags=("ok",))
                except Exception as e:
                    self.tv.set(iid, "st", "失败")
                    self.tv.set(iid, "out", str(e))
                    self.tv.item(iid, tags=("err",))
                finally:
                    self._busy = False
                    self._refresh_count()

            self.root.after(10, do_work)

        self._refresh_count()
        self.root.after(200, self._process)

    def _refresh_count(self):
        total = len(self._jobs)
        done = sum(
            1
            for iid in self._jobs
            if self.tv.item(iid, "tags")[0] in ("ok", "err")
        )
        self.cnt.config(text=f"{done}/{total}" if total else "")


if __name__ == "__main__":
    App(tk.Tk())
    tk.mainloop()
