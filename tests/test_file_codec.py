import json

from securegenomics.file_codec import (
    load_file_smart,
    save_file_smart,
    serialize_encrypted_data,
    write_encrypted_data,
)


def test_load_file_smart_handles_json_text_and_binary(tmp_path):
    json_path = tmp_path / "payload.json"
    json_path.write_text('{"score": 42}')

    text_path = tmp_path / "payload.txt"
    text_path.write_text("plain payload")

    binary_path = tmp_path / "payload.bin"
    binary_path.write_bytes(b"\xff\xfe\x00\x01")

    assert load_file_smart(json_path) == {"score": 42}
    assert load_file_smart(text_path) == "plain payload"
    assert load_file_smart(binary_path) == b"\xff\xfe\x00\x01"


def test_save_file_smart_handles_strings_bytes_and_json(tmp_path):
    text_path = tmp_path / "payload.txt"
    binary_path = tmp_path / "payload.bin"
    json_path = tmp_path / "payload.json"

    save_file_smart(text_path, "plain payload")
    save_file_smart(binary_path, b"encrypted")
    save_file_smart(json_path, {"score": 42})

    assert text_path.read_text() == "plain payload"
    assert binary_path.read_bytes() == b"encrypted"
    assert json.loads(json_path.read_text()) == {"score": 42}


def test_write_encrypted_data_serializes_protocol_outputs(tmp_path):
    text_path = tmp_path / "text.encrypted"
    json_path = tmp_path / "json.encrypted"
    bytes_path = tmp_path / "bytes.encrypted"

    assert write_encrypted_data(text_path, "encrypted") == b"encrypted"
    assert text_path.read_bytes() == b"encrypted"

    json_bytes = write_encrypted_data(json_path, {"score": 42})
    assert json.loads(json_bytes.decode("utf-8")) == {"score": 42}
    assert json.loads(json_path.read_text()) == {"score": 42}

    assert write_encrypted_data(bytes_path, b"already bytes") == b"already bytes"
    assert bytes_path.read_bytes() == b"already bytes"


def test_serialize_encrypted_data_preserves_non_string_and_non_dict_objects():
    payload = ["legacy", "payload"]

    assert serialize_encrypted_data(payload) is payload
