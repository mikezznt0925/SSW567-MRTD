from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

MRZ_LINE_LENGTH = 44
_ALLOWED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<")
_WEIGHTS = (7, 3, 1)


class MRZFormatError(ValueError):
    pass


@dataclass
class MRZDecodedData:
    document_type: str
    issuing_country: str
    surname: str
    given_names: str
    passport_number: str
    nationality: str
    birth_date: str
    sex: str
    expiry_date: str
    optional_data: str
    check_digit_passport: str
    check_digit_birth: str
    check_digit_expiry: str
    check_digit_composite: str
    raw_line1: str = ""
    raw_line2: str = ""


@dataclass
class MRZTravelerData:
    document_type: str
    issuing_country: str
    surname: str
    given_names: str
    passport_number: str
    nationality: str
    birth_date: str
    sex: str
    expiry_date: str
    optional_data: str


@dataclass
class CheckDigitMismatch:
    field_name: str
    expected_check_digit: str
    actual_check_digit: str


def _char_value(ch: str) -> int:
    if ch == "<":
        return 0
    if "0" <= ch <= "9":
        return ord(ch) - ord("0")
    if "A" <= ch <= "Z":
        return ord(ch) - ord("A") + 10
    raise MRZFormatError(f"bad char {ch!r}")


def _checksum_for_check_digit(data: str) -> int:
    total = 0
    for i, ch in enumerate(data):
        total += _char_value(ch) * _WEIGHTS[i % 3]
    return total % 10


def compute_check_digit(data: str) -> str:
    return str(_checksum_for_check_digit(data))


def _validate_line(line: str, label: str) -> None:
    if len(line) != MRZ_LINE_LENGTH:
        raise MRZFormatError(f"{label}: need {MRZ_LINE_LENGTH}, got {len(line)}")
    bad = [c for c in line if c not in _ALLOWED]
    if bad:
        raise MRZFormatError(f"{label}: bad charset")


def validate_mrz_input(line1: str, line2: str) -> None:
    _validate_line(line1, "line1")
    _validate_line(line2, "line2")


def _decode_name_field(block: str) -> Tuple[str, str]:
    block = block.rstrip("<")
    if not block:
        return "", ""
    if "<<" not in block:
        return block, ""
    surname, rest = block.split("<<", 1)
    given = " ".join(p for p in rest.split("<") if p)
    return surname, given


def _encode_name_field(surname: str, given_names: str, length: int = 39) -> str:
    sn = surname.upper().replace(" ", "<")
    gn = given_names.upper().replace(" ", "<")
    raw = f"{sn}<<{gn}"
    if len(raw) > length:
        raise MRZFormatError(f"name too long (max {length})")
    return raw.ljust(length, "<")


def _pad_field(value: str, length: int) -> str:
    v = value.upper()
    if len(v) > length:
        raise MRZFormatError(f"field too long (max {length})")
    return v.ljust(length, "<")


def decode_mrz(line1: str, line2: str) -> MRZDecodedData:
    validate_mrz_input(line1, line2)

    doc_type = line1[0:2]
    issuing = line1[2:5]
    name_block = line1[5:44]
    surname, given = _decode_name_field(name_block)

    passport_number = line2[0:9]
    cd_pass = line2[9]
    nationality = line2[10:13]
    birth_date = line2[13:19]
    cd_birth = line2[19]
    sex = line2[20]
    expiry_date = line2[21:27]
    cd_expiry = line2[27]
    optional_data = line2[28:43]
    cd_comp = line2[43]

    return MRZDecodedData(
        document_type=doc_type,
        issuing_country=issuing,
        surname=surname,
        given_names=given,
        passport_number=passport_number,
        nationality=nationality,
        birth_date=birth_date,
        sex=sex,
        expiry_date=expiry_date,
        optional_data=optional_data,
        check_digit_passport=cd_pass,
        check_digit_birth=cd_birth,
        check_digit_expiry=cd_expiry,
        check_digit_composite=cd_comp,
        raw_line1=line1,
        raw_line2=line2,
    )


def encode_mrz(data: MRZTravelerData) -> Tuple[str, str]:
    line1 = (
        _pad_field(data.document_type, 2)
        + _pad_field(data.issuing_country, 3)
        + _encode_name_field(data.surname, data.given_names, 39)
    )
    if len(line1) != MRZ_LINE_LENGTH:
        raise MRZFormatError("line1 != 44")

    pn = _pad_field(data.passport_number, 9)
    nat = _pad_field(data.nationality, 3)
    dob = _pad_field(data.birth_date, 6)
    sex_c = (data.sex or "<").upper()[:1]
    if sex_c not in "MF<":
        sex_c = "<"
    exp = _pad_field(data.expiry_date, 6)
    opt = _pad_field(data.optional_data, 15)

    cd1 = compute_check_digit(pn)
    cd2 = compute_check_digit(dob)
    cd3 = compute_check_digit(exp)
    composite_input = pn + cd1 + dob + cd2 + exp + cd3 + opt
    cd4 = compute_check_digit(composite_input)

    line2 = pn + cd1 + nat + dob + cd2 + sex_c + exp + cd3 + opt + cd4
    if len(line2) != MRZ_LINE_LENGTH:
        raise MRZFormatError("line2 != 44")

    validate_mrz_input(line1, line2)
    return line1, line2


def validate_check_digits(line1: str, line2: str) -> List[CheckDigitMismatch]:
    validate_mrz_input(line1, line2)
    decoded = decode_mrz(line1, line2)
    mismatches: List[CheckDigitMismatch] = []

    exp_pass = compute_check_digit(decoded.passport_number)
    if exp_pass != decoded.check_digit_passport:
        mismatches.append(
            CheckDigitMismatch(
                "passport",
                exp_pass,
                decoded.check_digit_passport,
            )
        )

    exp_birth = compute_check_digit(decoded.birth_date)
    if exp_birth != decoded.check_digit_birth:
        mismatches.append(
            CheckDigitMismatch(
                "dob",
                exp_birth,
                decoded.check_digit_birth,
            )
        )

    exp_expiry = compute_check_digit(decoded.expiry_date)
    if exp_expiry != decoded.check_digit_expiry:
        mismatches.append(
            CheckDigitMismatch(
                "expiry",
                exp_expiry,
                decoded.check_digit_expiry,
            )
        )

    comp_str = (
        decoded.passport_number
        + decoded.check_digit_passport
        + decoded.birth_date
        + decoded.check_digit_birth
        + decoded.expiry_date
        + decoded.check_digit_expiry
        + decoded.optional_data
    )
    exp_comp = compute_check_digit(comp_str)
    if exp_comp != decoded.check_digit_composite:
        mismatches.append(
            CheckDigitMismatch(
                "composite",
                exp_comp,
                decoded.check_digit_composite,
            )
        )

    return mismatches


class MRTD:
    def scan_mrz_hardware(self) -> Tuple[str, str]:
        raise NotImplementedError("scanner not implemented")

    def fetch_travel_document_from_db(self, document_id: str) -> MRZTravelerData:
        raise NotImplementedError("db not implemented")

    def decode(self, line1: str, line2: str) -> MRZDecodedData:
        return decode_mrz(line1, line2)

    def encode(self, data: MRZTravelerData) -> Tuple[str, str]:
        return encode_mrz(data)

    def validate_check_digits(self, line1: str, line2: str) -> List[CheckDigitMismatch]:
        return validate_check_digits(line1, line2)


__all__ = [
    "MRZ_LINE_LENGTH",
    "MRZFormatError",
    "MRZDecodedData",
    "MRZTravelerData",
    "CheckDigitMismatch",
    "MRTD",
    "validate_mrz_input",
    "decode_mrz",
    "encode_mrz",
    "validate_check_digits",
    "compute_check_digit",
]
