import pytest
from aiokafka import codec

# Um produtor de fora (ex.: rpk) pode comprimir; o consumidor precisa abrir o registro antes do handle_record
CODECS = [
    ("snappy", codec.has_snappy, codec.snappy_encode, codec.snappy_decode),
    ("lz4", codec.has_lz4, codec.lz4_encode, codec.lz4_decode),
    ("zstd", codec.has_zstd, codec.zstd_encode, codec.zstd_decode),
]


@pytest.mark.parametrize("name,available,encode,decode", CODECS, ids=[c[0] for c in CODECS])
def test_consumer_can_decompress(name, available, encode, decode):
    payload = b'{"event_id": "x"}' * 50
    assert available(), f"codec {name} indisponivel: falta o cramjam na imagem"
    assert decode(encode(payload)) == payload
