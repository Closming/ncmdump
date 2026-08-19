# NCM 转换器

将网易云音乐加密的 `.ncm` 文件转换为通用的 `.mp3` / `.flac` 格式。

基于 [anonymous5l/ncmdump](https://github.com/anonymous5l/ncmdump) 和 [nzix/ncmdump](https://github.com/nzix/ncmdump) 的算法实现，提供图形化操作界面。

## 使用方式

### 直接下载（推荐）

从 [Releases](../../releases) 下载 `NCM转换器.exe`，双击运行，无需安装 Python。

### 从源码运行

```bash
pip install -r requirements.txt
pythonw ncm_gui.pyw
```

## 打包为 .exe

```bash
pip install pyinstaller
pyinstaller --noconsole --onefile --name "NCM转换器" ^
  --hidden-import Crypto --hidden-import Crypto.Cipher --hidden-import Crypto.Util.Padding ^
  --hidden-import mutagen --hidden-import mutagen.mp3 --hidden-import mutagen.flac --hidden-import mutagen.id3 ^
  ncm_gui.pyw
```

`dist/NCM转换器.exe` 即为独立可执行文件。

## 技术原理

NCM 文件采用多层加密：

1. **AES-128-ECB**（密钥 `CORE_KEY`）→ 解密出 RC4 密钥
2. **AES-128-ECB**（密钥 `META_KEY`）→ 解密出歌曲元数据 JSON
3. **RC4 流密码**（第1步得到的密钥）→ 解密音频数据本体
4. 专辑封面明文存储，无需解密

两把 AES 密钥硬编码在网易云客户端中，逆向可得。

## 项目结构

```
├── ncm_gui.pyw          # GUI 应用源码
├── requirements.txt     # Python 依赖
└── README.md
```

## 许可

本项目仅用于个人学习和技术研究，不得用于商业用途或侵犯版权。
