import pytest

from app.download import _bencode, _bdecode, create_minimal_torrent


class TestBencode:
    def test_int(self):
        assert _bencode(42) == b"i42e"

    def test_negative_int(self):
        assert _bencode(-1) == b"i-1e"

    def test_zero(self):
        assert _bencode(0) == b"i0e"

    def test_bytes(self):
        assert _bencode(b"spam") == b"4:spam"

    def test_empty_bytes(self):
        assert _bencode(b"") == b"0:"

    def test_str(self):
        assert _bencode("hello") == b"5:hello"

    def test_list(self):
        assert _bencode([1, b"two"]) == b"li1e3:twoe"

    def test_empty_list(self):
        assert _bencode([]) == b"le"

    def test_dict(self):
        result = _bencode({b"a": 1, b"b": 2})
        assert result == b"d1:ai1e1:bi2ee"

    def test_dict_sorted_keys(self):
        result = _bencode({b"z": 1, b"a": 2})
        assert result == b"d1:ai2e1:zi1ee"

    def test_nested(self):
        data = {b"list": [1, {b"key": b"val"}]}
        result = _bencode(data)
        decoded = _bdecode(result)
        assert decoded == data

    def test_unsupported_type_raises(self):
        with pytest.raises(TypeError):
            _bencode(3.14)


class TestBdecode:
    def test_int(self):
        assert _bdecode(b"i42e") == 42

    def test_negative_int(self):
        assert _bdecode(b"i-1e") == -1

    def test_string(self):
        assert _bdecode(b"4:spam") == b"spam"

    def test_empty_string(self):
        assert _bdecode(b"0:") == b""

    def test_list(self):
        assert _bdecode(b"li1e3:twoe") == [1, b"two"]

    def test_empty_list(self):
        assert _bdecode(b"le") == []

    def test_dict(self):
        assert _bdecode(b"d1:ai1e1:bi2ee") == {b"a": 1, b"b": 2}

    def test_nested(self):
        data = b"d4:listli1ed3:key3:valeee"
        result = _bdecode(data)
        assert result == {b"list": [1, {b"key": b"val"}]}

    def test_invalid_raises(self):
        with pytest.raises((ValueError, IndexError)):
            _bdecode(b"x")


@pytest.mark.parametrize("value", [
    0, 42, -1,
    b"", b"spam", b"\x00\x01\x02",
    "hello",
    [], [1, 2, 3], [b"a", [b"b"]],
    {}, {b"key": b"val"}, {b"a": {b"b": 1}},
])
def test_bencode_bdecode_roundtrip(value):
    encoded = _bencode(value)
    decoded = _bdecode(encoded)
    if isinstance(value, str):
        assert decoded == value.encode()
    else:
        assert decoded == value


class TestCreateMinimalTorrent:
    def test_basic(self):
        result = create_minimal_torrent("test.mkv", 1048576, "-100123", 42)
        decoded = _bdecode(result)
        assert decoded[b"comment"] == b"-100123:42"
        assert decoded[b"created by"] == b"telegram-torznab"
        info = decoded[b"info"]
        assert info[b"name"] == b"test.mkv"
        assert info[b"length"] == 1048576
        assert info[b"piece length"] == 524288
        # 1MB / 512KB = 2 pieces, each 20 bytes SHA1
        assert len(info[b"pieces"]) == 40

    def test_zero_size(self):
        result = create_minimal_torrent("empty.txt", 0, "-100", 1)
        decoded = _bdecode(result)
        info = decoded[b"info"]
        assert info[b"length"] == 0
        # Zero size should still produce 1 piece
        assert len(info[b"pieces"]) == 20

    def test_large_file_pieces(self):
        # 5MB = 10 pieces of 512KB
        result = create_minimal_torrent("big.mkv", 5 * 1048576, "-100", 1)
        decoded = _bdecode(result)
        assert len(decoded[b"info"][b"pieces"]) == 10 * 20

    def test_roundtrip(self):
        torrent_bytes = create_minimal_torrent("file.mp4", 1000, "-999", 7)
        decoded = _bdecode(torrent_bytes)
        assert decoded[b"comment"] == b"-999:7"
        assert decoded[b"info"][b"name"] == b"file.mp4"
        assert decoded[b"info"][b"length"] == 1000

    def test_unicode_filename(self):
        result = create_minimal_torrent("película.mkv", 100, "-100", 1)
        decoded = _bdecode(result)
        assert decoded[b"info"][b"name"] == "película".encode("utf-8") + b".mkv"
