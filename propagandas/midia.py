"""Identificação dos arquivos de mídia pelo conteúdo, não só pela extensão."""

EXTENSOES = {
    "jpg": "imagem",
    "jpeg": "imagem",
    "png": "imagem",
    "gif": "imagem",
    "webp": "imagem",
    "mp4": "video",
    "m4v": "video",
    "webm": "video",
}

# Formatos de IMAGEM que também usam a estrutura "ftyp" do MP4.
_MARCAS_DE_IMAGEM = {b"avif", b"avis", b"heic", b"heix", b"mif1", b"msf1"}


def extensao_de(nome):
    return nome.rsplit(".", 1)[-1].lower() if "." in nome else ""


def detectar_tipo(cabecalho):
    """Olha os primeiros bytes do arquivo e diz se é 'imagem', 'video' ou None."""
    if cabecalho.startswith(b"\xff\xd8\xff"):  # JPEG
        return "imagem"
    if cabecalho.startswith(b"\x89PNG\r\n\x1a\n"):
        return "imagem"
    if cabecalho[:6] in (b"GIF87a", b"GIF89a"):
        return "imagem"
    if cabecalho[:4] == b"RIFF" and cabecalho[8:12] == b"WEBP":
        return "imagem"
    if cabecalho[4:8] == b"ftyp" and cabecalho[8:12] not in _MARCAS_DE_IMAGEM:  # MP4
        return "video"
    if cabecalho.startswith(b"\x1a\x45\xdf\xa3"):  # WebM / Matroska
        return "video"
    return None
