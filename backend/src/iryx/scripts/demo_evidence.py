"""Deterministic, programmatically generated demo evidence for Story 9.3.

The fixtures are intentionally small, synthetic, and reproducible: no opaque
binary blob is versioned in the repository. The EVTX fixture is a real binary
EVTX container (file header, chunk, records, binary XML template) that
``python-evtx`` and ``EvtxParserTool`` can parse without mocks.
"""

from __future__ import annotations

import binascii
import struct
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache

EVTX_CHUNK_SIZE = 0x10000
EVTX_FILE_HEADER_SIZE = 0x1000
EVTX_RECORD_HEADER_SIZE = 0x18
EVTX_TEMPLATE_ID = 1
EVTX_NAMESPACE = "http://schemas.microsoft.com/win/2004/08/events/event"

SECURITY_EVTX_NAME = "Security.evtx"
POWERSHELL_PREFETCH_NAME = "POWERSHELL.EXE-DEMO1234.pf"
MEMORY_DUMP_NAME = "MEMORY.DMP"

# 2026-11-24 02:14:22 UTC, the synthetic PowerShell execution timestamp.
_PREFETCH_LAST_RUN = datetime(2026, 11, 24, 2, 14, 22, tzinfo=UTC)
_PREFETCH_VOLUME_CREATION = datetime(2026, 11, 20, 9, 30, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class DemoEvidence:
    """One deterministic evidence fixture ready to be written and sealed."""

    original_name: str
    description: str
    content: bytes


def _filetime(timestamp: datetime) -> int:
    """Convert a timezone-aware datetime to a Windows FILETIME integer."""
    return (int(timestamp.timestamp()) + 11_644_473_600) * 10_000_000 + timestamp.microsecond * 10


def _utf16(value: str) -> bytes:
    return value.encode("utf-16-le")


def _wstring_value(value: str) -> bytes:
    """Encode a literal BXml WSTRING value node."""
    return b"\x05\x01" + struct.pack("<H", len(value)) + _utf16(value)


def _substitution(index: int, value_type: int = 0x01) -> bytes:
    """Encode a BXml normal substitution referencing a record substitution slot."""
    return b"\x0d" + struct.pack("<H", index) + bytes([value_type])


class _EvtxChunkBuilder:
    """Minimal EVTX chunk writer sufficient for python-evtx and IRYX tools.

    Layout produced:
      * 4 KiB file header (``ElfFile\\x00``)
      * 64 KiB chunk (``ElfChnk\\x00``)
      * records starting at chunk offset ``0x200``
      * one resident binary XML template in the first record, reused by the
        following records through a non-resident template instance.
    """

    def __init__(self) -> None:
        self._buffer = bytearray(EVTX_CHUNK_SIZE)
        self._cursor = 0x200
        self._string_offsets: list[int] = []
        self._template_offset: int | None = None
        self._record_offsets: list[int] = []

    def _write(self, data: bytes) -> int:
        end = self._cursor + len(data)
        if end > EVTX_CHUNK_SIZE:
            raise ValueError("Le contenu EVTX de démonstration dépasse un chunk de 64 Kio.")
        offset = self._cursor
        self._buffer[offset:end] = data
        self._cursor = end
        return offset

    def _add_name_string(self, name: str) -> int:
        offset = self._cursor
        self._write(struct.pack("<IHH", 0, 0, len(name)))
        self._write(_utf16(name))
        self._write(b"\x00\x00")
        self._string_offsets.append(offset)
        return offset

    def _open_element(
        self,
        name: str,
        attributes: list[tuple[str, bytes]] | None = None,
        *,
        empty: bool = False,
    ) -> None:
        attributes = attributes or []
        offset = self._cursor
        tag_length = 15 if attributes else 11
        header = bytearray(tag_length)
        header[0] = 0x01 | ((0x04 if attributes else 0x00) << 4)
        struct.pack_into("<I", header, 7, offset + tag_length)
        self._write(bytes(header))
        self._add_name_string(name)
        for attribute_name, attribute_value in attributes:
            self._write_attribute(attribute_name, attribute_value)
        self._write(b"\x03" if empty else b"\x02")

    def _write_attribute(self, name: str, value: bytes) -> None:
        offset = self._cursor
        header = bytearray(5)
        header[0] = 0x06
        struct.pack_into("<I", header, 1, offset + 5)
        self._write(bytes(header))
        self._add_name_string(name)
        self._write(value)

    def _close_element(self) -> None:
        self._write(b"\x04")

    def _element_with_value(self, name: str, value: bytes) -> None:
        self._open_element(name)
        self._write(value)
        self._close_element()

    def _write_template(self) -> None:
        """Write the resident template definition and remember its offset."""
        template_offset = self._cursor
        self._template_offset = template_offset
        self._write(struct.pack("<I", 0))  # next template offset
        # python-evtx reads the GUID at offset 4, overlapping the template id.
        self._write(struct.pack("<I", EVTX_TEMPLATE_ID) + b"\x00" * 12)
        data_length_offset = self._cursor
        self._write(struct.pack("<I", 0))  # data length placeholder
        content_start = self._cursor

        self._open_element("Event", [("xmlns", _wstring_value(EVTX_NAMESPACE))])
        self._open_element("System")
        self._open_element("Provider", [("Name", _substitution(0))], empty=True)
        self._element_with_value("EventID", _substitution(1))
        self._element_with_value("Level", _substitution(2))
        self._element_with_value("Task", _substitution(3))
        self._element_with_value("Opcode", _substitution(4))
        self._element_with_value("Keywords", _substitution(5))
        self._open_element("TimeCreated", [("SystemTime", _substitution(6))], empty=True)
        self._element_with_value("EventRecordID", _substitution(7))
        self._open_element(
            "Execution",
            [("ProcessID", _substitution(8)), ("ThreadID", _substitution(9))],
            empty=True,
        )
        self._element_with_value("Channel", _substitution(10))
        self._element_with_value("Computer", _substitution(11))
        self._open_element("Security", [("UserID", _substitution(12))], empty=True)
        self._close_element()  # System

        self._open_element("EventData")
        for field_name, index in (
            ("SubjectUserName", 13),
            ("TargetUserName", 14),
            ("LogonType", 15),
            ("NewProcessName", 16),
            ("CommandLine", 17),
            ("ProcessId", 18),
        ):
            self._open_element("Data", [("Name", _wstring_value(field_name))])
            self._write(_substitution(index))
            self._close_element()
        self._close_element()  # EventData
        self._close_element()  # Event
        self._write(b"\x00")  # template end-of-stream

        struct.pack_into("<I", self._buffer, data_length_offset, self._cursor - content_start)

    def add_record(
        self,
        record_number: int,
        timestamp: datetime,
        substitutions: list[str],
        *,
        resident_template: bool = False,
    ) -> None:
        record_offset = self._cursor
        self._record_offsets.append(record_offset)
        self._write(b"\x00" * EVTX_RECORD_HEADER_SIZE)

        self._write(b"\x0f\x01\x01\x00")  # start of stream
        if resident_template:
            template_offset = self._cursor + 10
        else:
            if self._template_offset is None:
                raise ValueError("Le template EVTX doit être écrit par le premier enregistrement.")
            template_offset = self._template_offset
        self._write(
            b"\x0c\x00" + struct.pack("<I", EVTX_TEMPLATE_ID) + struct.pack("<I", template_offset)
        )
        if resident_template:
            self._write_template()

        self._write(struct.pack("<I", len(substitutions)))
        for value in substitutions:
            encoded = _utf16(value)
            self._write(struct.pack("<HB", len(encoded), 0x01) + b"\x00")
        for value in substitutions:
            self._write(_utf16(value))

        record_size = self._cursor - record_offset + 4
        struct.pack_into("<I", self._buffer, record_offset, 0x2A2A)
        struct.pack_into("<I", self._buffer, record_offset + 4, record_size)
        struct.pack_into("<Q", self._buffer, record_offset + 8, record_number)
        struct.pack_into("<Q", self._buffer, record_offset + 16, _filetime(timestamp))
        self._write(struct.pack("<I", record_size))

    def _finalize_chunk(self) -> bytes:
        for index, string_offset in enumerate(self._string_offsets):
            next_offset = (
                self._string_offsets[index + 1] if index + 1 < len(self._string_offsets) else 0
            )
            struct.pack_into("<I", self._buffer, string_offset, next_offset)

        if self._string_offsets:
            struct.pack_into("<I", self._buffer, 0x80, self._string_offsets[0])
        if self._template_offset is not None:
            struct.pack_into("<I", self._buffer, 0x180, self._template_offset)

        next_record_offset = self._cursor
        struct.pack_into("<8s", self._buffer, 0x00, b"ElfChnk\x00")
        struct.pack_into("<Q", self._buffer, 0x08, 1)
        struct.pack_into("<Q", self._buffer, 0x10, len(self._record_offsets))
        struct.pack_into("<Q", self._buffer, 0x18, 1)
        struct.pack_into("<Q", self._buffer, 0x20, len(self._record_offsets))
        struct.pack_into("<I", self._buffer, 0x28, 0x200)
        struct.pack_into("<I", self._buffer, 0x2C, self._record_offsets[-1])
        struct.pack_into("<I", self._buffer, 0x30, next_record_offset)
        struct.pack_into(
            "<I",
            self._buffer,
            0x34,
            binascii.crc32(bytes(self._buffer[0x200:next_record_offset])) & 0xFFFFFFFF,
        )
        struct.pack_into(
            "<I",
            self._buffer,
            0x7C,
            binascii.crc32(bytes(self._buffer[0x00:0x78]) + bytes(self._buffer[0x80:0x200]))
            & 0xFFFFFFFF,
        )
        return bytes(self._buffer)

    def to_bytes(self) -> bytes:
        chunk = self._finalize_chunk()
        file_header = bytearray(EVTX_FILE_HEADER_SIZE)
        struct.pack_into("<8s", file_header, 0x00, b"ElfFile\x00")
        struct.pack_into("<Q", file_header, 0x08, 0)
        struct.pack_into("<Q", file_header, 0x10, 0)
        struct.pack_into("<Q", file_header, 0x18, len(self._record_offsets) + 1)
        struct.pack_into("<I", file_header, 0x20, 0x80)
        struct.pack_into("<H", file_header, 0x24, 1)
        struct.pack_into("<H", file_header, 0x26, 3)
        struct.pack_into("<H", file_header, 0x28, EVTX_FILE_HEADER_SIZE)
        struct.pack_into("<H", file_header, 0x2A, 1)
        struct.pack_into("<I", file_header, 0x78, 0)
        struct.pack_into(
            "<I",
            file_header,
            0x7C,
            binascii.crc32(bytes(file_header[0x00:0x78])) & 0xFFFFFFFF,
        )
        return bytes(file_header) + chunk


def _event_substitutions(
    *,
    event_id: str,
    record_id: str,
    timestamp: str,
    subject_user: str,
    target_user: str,
    logon_type: str,
    opcode: str = "0",
    new_process: str = "",
    command_line: str = "",
    process_id: str = "",
) -> list[str]:
    return [
        "Microsoft-Windows-Security-Auditing",
        event_id,
        "0",
        "12544",
        opcode,
        "0x8020000000000000",
        timestamp,
        record_id,
        "4",
        "12",
        "Security",
        "DC01.banque-atlantique.local",
        "S-1-5-18",
        subject_user,
        target_user,
        logon_type,
        new_process,
        command_line,
        process_id,
    ]


@lru_cache(maxsize=1)
def generate_security_evtx() -> bytes:
    """Generate a valid ``Security.evtx`` containing Event IDs 4624 and 4688."""
    builder = _EvtxChunkBuilder()
    builder.add_record(
        1,
        datetime(2026, 11, 24, 2, 13, 7, 123456, tzinfo=UTC),
        _event_substitutions(
            event_id="4624",
            record_id="1",
            timestamp="2026-11-24T02:13:07.123456Z",
            subject_user="SYSTEM",
            target_user="Administrateur",
            logon_type="10",
            opcode="1",
        ),
        resident_template=True,
    )
    builder.add_record(
        2,
        datetime(2026, 11, 24, 2, 14, 22, 654321, tzinfo=UTC),
        _event_substitutions(
            event_id="4688",
            record_id="2",
            timestamp="2026-11-24T02:14:22.654321Z",
            subject_user="Administrateur",
            target_user="Administrateur",
            logon_type="",
            new_process=r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
            command_line="powershell.exe -NoP -EncodedCommand SQBFAFgA",
            process_id="0x1a2b",
        ),
    )
    builder.add_record(
        3,
        datetime(2026, 11, 24, 2, 16, 3, tzinfo=UTC),
        _event_substitutions(
            event_id="4624",
            record_id="3",
            timestamp="2026-11-24T02:16:03.000000Z",
            subject_user="SYSTEM",
            target_user="svc_backup",
            logon_type="3",
        ),
    )
    return builder.to_bytes()


def _build_scca_prefetch_v30() -> bytes:
    """Build an uncompressed Windows 10 SCCA Prefetch v30 stream."""
    from dissect.target.plugins.os.windows.prefetch import c_prefetch

    executable_name = "POWERSHELL.EXE"
    prefetch_hash = 0xDE401234
    last_run_time = _filetime(_PREFETCH_LAST_RUN)
    previous_runs = [last_run_time - 10_000_000, last_run_time - 20_000_000]
    dlls = [
        r"\DEVICE\HARDDISKVOLUME3\WINDOWS\SYSTEM32\NTDLL.DLL",
        r"\DEVICE\HARDDISKVOLUME3\WINDOWS\SYSTEM32\KERNEL32.DLL",
        r"\DEVICE\HARDDISKVOLUME3\WINDOWS\SYSTEM32\WINDOWSPOWERSHELL\V1.0\POWERSHELL.EXE",
    ]
    volumes = [
        (
            r"\DEVICE\HARDDISKVOLUME3",
            0xA1B2C3D4,
            _filetime(_PREFETCH_VOLUME_CREATION),
        )
    ]

    header = c_prefetch.PREFETCH_HEADER()
    header.version = 30
    header.signature = b"SCCA"
    header.name = executable_name.encode("utf-16-le").ljust(60, b"\x00")
    header.hash = prefetch_hash

    file_info = c_prefetch.FILE_INFORMATION_26()
    file_info.last_run_time = last_run_time
    file_info.run_count = 3
    file_info.last_run_remains = (previous_runs + [0] * 7)[:7]

    metric_struct = c_prefetch.FILE_METRICS_ARRAY_ENTRY_23
    metric_size = 32
    volume_struct = c_prefetch.VOLUME_INFORMATION_30
    volume_size = 96
    file_info_size = 224

    metrics_offset = 84 + file_info_size
    file_info.metrics_array_offset = metrics_offset
    file_info.number_of_file_metrics_entries = len(dlls)

    strings_offset = metrics_offset + (len(dlls) * metric_size)
    file_info.filename_strings_offset = strings_offset

    dll_data = bytearray()
    metrics: list[object] = []
    for dll in dlls:
        metric = metric_struct()
        metric.filename_string_offset = len(dll_data)
        metric.filename_string_number_of_characters = len(dll)
        metrics.append(metric)
        dll_data.extend(dll.encode("utf-16-le"))
    file_info.filename_strings_size = len(dll_data)

    volumes_offset = strings_offset + len(dll_data)
    file_info.volumes_information_offset = volumes_offset
    file_info.number_of_volumes = len(volumes)

    volume_data = bytearray()
    for device_path, serial_number, creation_time in volumes:
        volume = volume_struct()
        volume.creation_time = creation_time
        volume.serial_number = serial_number
        volume.device_path_number_of_characters = len(device_path)
        volume.device_path_offset = volume_size
        volume_data.extend(volume.dumps())
        volume_data.extend(device_path.encode("utf-16-le"))
    file_info.volumes_information_size = len(volume_data)

    total_size = volumes_offset + len(volume_data)
    header.size = total_size

    buffer = bytearray(total_size)
    buffer[0:84] = header.dumps()
    buffer[84 : 84 + file_info_size] = file_info.dumps()
    cursor = metrics_offset
    for metric in metrics:
        buffer[cursor : cursor + metric_size] = metric.dumps()
        cursor += metric_size
    buffer[strings_offset : strings_offset + len(dll_data)] = dll_data
    buffer[volumes_offset : volumes_offset + len(volume_data)] = volume_data
    return bytes(buffer)


@lru_cache(maxsize=1)
def generate_powershell_prefetch() -> bytes:
    """Generate a valid ``POWERSHELL.EXE-DEMO1234.pf`` Prefetch fixture."""
    return _build_scca_prefetch_v30()


@lru_cache(maxsize=1)
def generate_memory_dump_extract() -> bytes:
    """Generate a small, deterministic Windows minidump-style memory extract.

    This is a synthetic extract for demonstration and ingestion only. It is not
    a complete RAM image and cannot be analyzed by Volatility 3 without a real
    memory capture and matching symbols.
    """
    page_size = 4096
    page = bytes((index * 37 + 11) & 0xFF for index in range(page_size))
    memory_ranges = [
        (0xFFFFF80000000000, page_size),
        (0xFFFFF88000000000, page_size),
    ]

    header_size = 32
    directory_rva = header_size
    directory_size = 2 * 12
    system_info_rva = directory_rva + directory_size
    system_info_size = 56
    memory_list_rva = system_info_rva + system_info_size
    memory_list_size = 16 + (len(memory_ranges) * 16)
    memory_data_rva = memory_list_rva + memory_list_size

    header = bytearray(header_size)
    struct.pack_into("<4s", header, 0x00, b"MDMP")
    struct.pack_into("<I", header, 0x04, 0xA793)
    struct.pack_into("<I", header, 0x08, 2)
    struct.pack_into("<I", header, 0x0C, directory_rva)
    struct.pack_into("<I", header, 0x10, 0)
    struct.pack_into("<I", header, 0x14, int(_PREFETCH_LAST_RUN.timestamp()))
    struct.pack_into("<Q", header, 0x18, 0)

    directory = bytearray(directory_size)
    struct.pack_into("<III", directory, 0, 7, system_info_size, system_info_rva)
    struct.pack_into("<III", directory, 12, 9, memory_list_size, memory_list_rva)

    system_info = bytearray(system_info_size)
    struct.pack_into("<H", system_info, 0, 9)  # PROCESSOR_ARCHITECTURE_AMD64
    struct.pack_into("<H", system_info, 2, 6)
    struct.pack_into("<H", system_info, 4, 0)
    struct.pack_into("<B", system_info, 6, 4)
    struct.pack_into("<B", system_info, 7, 1)
    struct.pack_into("<I", system_info, 8, 10)
    struct.pack_into("<I", system_info, 12, 0)
    struct.pack_into("<I", system_info, 16, 19045)
    struct.pack_into("<I", system_info, 20, 2)
    struct.pack_into("<I", system_info, 24, 0)
    struct.pack_into("<H", system_info, 28, 0)
    struct.pack_into("<H", system_info, 30, 0)

    memory_list = bytearray(memory_list_size)
    struct.pack_into("<Q", memory_list, 0, len(memory_ranges))
    struct.pack_into("<Q", memory_list, 8, memory_data_rva)
    for index, (start, size) in enumerate(memory_ranges):
        struct.pack_into("<QQ", memory_list, 16 + (index * 16), start, size)

    return bytes(header) + bytes(directory) + bytes(system_info) + bytes(memory_list) + page + page


def build_demo_evidences() -> tuple[DemoEvidence, ...]:
    """Return the three deterministic demo evidence fixtures."""
    return (
        DemoEvidence(
            original_name=SECURITY_EVTX_NAME,
            description="Journal de sécurité Windows contenant les Event IDs 4624 et 4688.",
            content=generate_security_evtx(),
        ),
        DemoEvidence(
            original_name=POWERSHELL_PREFETCH_NAME,
            description="Artefact Prefetch de l'exécution PowerShell malveillante.",
            content=generate_powershell_prefetch(),
        ),
        DemoEvidence(
            original_name=MEMORY_DUMP_NAME,
            description="Extrait synthétique de dump mémoire pour la démonstration.",
            content=generate_memory_dump_extract(),
        ),
    )
