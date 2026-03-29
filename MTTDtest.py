"""
Unit tests for MRTD.py with mocks for scanner and database (no real hardware/DB).
Country codes follow ICAO 9303 three-letter codes (e.g. USA, GBR, CHN, DEU, FRA, JPN).
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import MRTD
from MRTD import (
    MRZFormatError,
    MRZDecodedData,
    MRZTravelerData,
    CheckDigitMismatch,
    MRTD as MRTDSystem,
    compute_check_digit,
    decode_mrz,
    encode_mrz,
    validate_check_digits,
    validate_mrz_input,
    MRZ_LINE_LENGTH,
)

# ICAO Doc 9303 style 3-letter codes (nationality / issuing state examples)
L1_ICAO_SAMPLE = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
L2_ICAO_SAMPLE = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"


def _traveler_usa_male() -> MRZTravelerData:
    """USA-issued style record; nationality USA (ICAO alpha-3)."""
    return MRZTravelerData(
        document_type="P<",
        issuing_country="USA",
        surname="SMITH",
        given_names="JOHN PAUL",
        passport_number="A12345678",
        nationality="USA",
        birth_date="900515",
        sex="M",
        expiry_date="300414",
        optional_data="<<<<<<<<<<<<<<<",
    )


def _traveler_chn_female() -> MRZTravelerData:
    """CHN nationality; tests another issuing / nationality pair."""
    return MRZTravelerData(
        document_type="P<",
        issuing_country="CHN",
        surname="LI",
        given_names="WEI",
        passport_number="E12345678",
        nationality="CHN",
        birth_date="950101",
        sex="F",
        expiry_date="350630",
        optional_data="<<<<<<<<<<<<<<<",
    )


def _traveler_deu() -> MRZTravelerData:
    """DEU (Germany) codes and digit-heavy passport number."""
    return MRZTravelerData(
        document_type="P<",
        issuing_country="DEU",
        surname="MUELLER",
        given_names="HANS",
        passport_number="C01X00T47",
        nationality="DEU",
        birth_date="880712",
        sex="M",
        expiry_date="280315",
        optional_data="<<<<<<<<<<<<<<<",
    )


class TestComputeCheckDigit(unittest.TestCase):
    """Tests for compute_check_digit (ICAO weighted mod 10)."""

    def test_known_icao_passport_field(self):
        # ICAO sample: document number L898902C3 must yield check digit 6
        self.assertEqual(compute_check_digit("L898902C3"), "6")

    def test_known_icao_dob_and_expiry(self):
        # Birth date 740812 -> check 2; expiry 120415 -> check 9
        self.assertEqual(compute_check_digit("740812"), "2")
        self.assertEqual(compute_check_digit("120415"), "9")

    def test_filler_and_digits_only(self):
        # '<' maps to 0; ensures filler branch in char value logic
        self.assertEqual(compute_check_digit("<<<<<<<<"), "0")

    def test_invalid_character_raises(self):
        # Branch: non MRZ character in checksum input raises MRZFormatError
        with self.assertRaises(MRZFormatError) as ctx:
            compute_check_digit("HELLO!")
        self.assertIn("bad char", str(ctx.exception))


class TestValidateMrzInput(unittest.TestCase):
    """Tests for validate_mrz_input: length and charset (Req 1)."""

    def test_valid_pair_accepted(self):
        # Both lines 44 chars and valid charset -> no exception
        validate_mrz_input(L1_ICAO_SAMPLE, L2_ICAO_SAMPLE)

    def test_line1_wrong_length(self):
        # Branch: line1 shorter than 44
        with self.assertRaises(MRZFormatError) as ctx:
            validate_mrz_input("P<" + "<" * 40, L2_ICAO_SAMPLE)
        self.assertIn("line1", str(ctx.exception))
        self.assertIn("need 44", str(ctx.exception))

    def test_line2_wrong_length(self):
        # Branch: line2 longer than 44
        with self.assertRaises(MRZFormatError) as ctx:
            validate_mrz_input(L1_ICAO_SAMPLE, L2_ICAO_SAMPLE + "X")
        self.assertIn("line2", str(ctx.exception))

    def test_line1_lowercase_rejected(self):
        # Branch: bad charset on line1
        bad = "p<uto" + "X" * 39
        if len(bad) != 44:
            bad = bad[:44].ljust(44, "<")
        bad = bad[:5] + "a" + bad[6:]
        self.assertEqual(len(bad), 44)
        with self.assertRaises(MRZFormatError) as ctx:
            validate_mrz_input(bad, L2_ICAO_SAMPLE)
        self.assertIn("bad charset", str(ctx.exception))

    def test_line2_invalid_symbol(self):
        # Branch: disallowed punctuation in line2
        bad2 = L2_ICAO_SAMPLE[:20] + "@" + L2_ICAO_SAMPLE[21:]
        self.assertEqual(len(bad2), 44)
        with self.assertRaises(MRZFormatError):
            validate_mrz_input(L1_ICAO_SAMPLE, bad2)


class TestDecodeMrz(unittest.TestCase):
    """Tests for decode_mrz: fixed positions and name parsing (Req 2)."""

    def test_icao_sample_all_fields(self):
        # Golden MRZ: every field and check digit extracted correctly
        d = decode_mrz(L1_ICAO_SAMPLE, L2_ICAO_SAMPLE)
        self.assertEqual(d.document_type, "P<")
        self.assertEqual(d.issuing_country, "UTO")
        self.assertEqual(d.surname, "ERIKSSON")
        self.assertEqual(d.given_names, "ANNA MARIA")
        self.assertEqual(d.passport_number, "L898902C3")
        self.assertEqual(d.nationality, "UTO")
        self.assertEqual(d.birth_date, "740812")
        self.assertEqual(d.sex, "F")
        self.assertEqual(d.expiry_date, "120415")
        self.assertEqual(d.optional_data, "ZE184226B<<<<<1")
        self.assertEqual(d.check_digit_passport, "6")
        self.assertEqual(d.check_digit_birth, "2")
        self.assertEqual(d.check_digit_expiry, "9")
        self.assertEqual(d.check_digit_composite, "0")
        self.assertEqual(d.raw_line1, L1_ICAO_SAMPLE)
        self.assertEqual(d.raw_line2, L2_ICAO_SAMPLE)

    def test_decode_fra_issued_roundtrip_data(self):
        # FRA (France) codes: encode then decode preserves structured fields
        data = MRZTravelerData(
            document_type="P<",
            issuing_country="FRA",
            surname="DUBOIS",
            given_names="MARIE",
            passport_number="12AB34567",
            nationality="FRA",
            birth_date="001231",
            sex="F",
            expiry_date="251231",
            optional_data="<<<<<<<<<<<<<<<",
        )
        l1, l2 = encode_mrz(data)
        d = decode_mrz(l1, l2)
        self.assertEqual(d.issuing_country, "FRA")
        self.assertEqual(d.nationality, "FRA")
        self.assertEqual(d.surname, "DUBOIS")
        self.assertEqual(d.passport_number, "12AB34567")

    def test_name_only_surname_no_double_chevron(self):
        # Branch: name block has no '<<' -> entire block is surname, empty given
        name39 = "SINGLE" + "<" * 33
        self.assertEqual(len(name39), 39)
        line1 = "P<GBR" + name39
        l1, l2 = encode_mrz(_traveler_usa_male())
        line2 = l2
        d = decode_mrz(line1, line2)
        self.assertEqual(d.surname, "SINGLE")
        self.assertEqual(d.given_names, "")

    def test_name_empty_after_strip(self):
        # Branch: all fillers in name -> empty surname and given
        line1 = "P<ITA" + "<" * 39
        _, line2 = encode_mrz(_traveler_deu())
        d = decode_mrz(line1, line2)
        self.assertEqual(d.surname, "")
        self.assertEqual(d.given_names, "")

    def test_decode_rejects_invalid_before_parse(self):
        # decode_mrz calls validate first
        with self.assertRaises(MRZFormatError):
            decode_mrz(L1_ICAO_SAMPLE[:10], L2_ICAO_SAMPLE)


class TestEncodeMrz(unittest.TestCase):
    """Tests for encode_mrz: padding, sex normalization, check digits (Req 3)."""

    def test_roundtrip_usa(self):
        # USA / GBR style data round-trips through encode -> decode
        data = _traveler_usa_male()
        l1, l2 = encode_mrz(data)
        self.assertEqual(len(l1), MRZ_LINE_LENGTH)
        self.assertEqual(len(l2), MRZ_LINE_LENGTH)
        d = decode_mrz(l1, l2)
        self.assertEqual(d.passport_number, data.passport_number.upper())
        self.assertEqual(d.nationality, "USA")
        self.assertEqual(d.sex, "M")

    def test_roundtrip_chn(self):
        # CHN nationality encoding
        data = _traveler_chn_female()
        l1, l2 = encode_mrz(data)
        d = decode_mrz(l1, l2)
        self.assertEqual(d.issuing_country, "CHN")
        self.assertEqual(d.nationality, "CHN")
        self.assertEqual(d.sex, "F")

    def test_sex_invalid_becomes_filler(self):
        # Branch: sex not in M/F/< coerced to '<'
        data = _traveler_usa_male()
        data = MRZTravelerData(
            document_type=data.document_type,
            issuing_country=data.issuing_country,
            surname=data.surname,
            given_names=data.given_names,
            passport_number=data.passport_number,
            nationality=data.nationality,
            birth_date=data.birth_date,
            sex="X",
            expiry_date=data.expiry_date,
            optional_data=data.optional_data,
        )
        _, l2 = encode_mrz(data)
        self.assertEqual(l2[20], "<")

    def test_sex_empty_uses_filler(self):
        # Branch: empty sex -> '<'
        data = _traveler_usa_male()
        data = MRZTravelerData(
            document_type=data.document_type,
            issuing_country=data.issuing_country,
            surname=data.surname,
            given_names=data.given_names,
            passport_number=data.passport_number,
            nationality=data.nationality,
            birth_date=data.birth_date,
            sex="",
            expiry_date=data.expiry_date,
            optional_data=data.optional_data,
        )
        _, l2 = encode_mrz(data)
        self.assertEqual(l2[20], "<")

    def test_lowercase_input_uppercased(self):
        # _pad_field uppercases MRZ fields
        data = MRZTravelerData(
            document_type="p<",
            issuing_country="jpn",
            surname="tanaka",
            given_names="taro",
            passport_number="ab1234567",
            nationality="jpn",
            birth_date="010203",
            sex="m",
            expiry_date="050607",
            optional_data="<<<<<<<<<<<<<<<",
        )
        l1, l2 = encode_mrz(data)
        self.assertTrue(l1.startswith("P<JPN"))
        self.assertIn("TANAKA", l1)

    def test_optional_data_short_padded(self):
        # Optional field shorter than 15 padded with '<'
        data = _traveler_usa_male()
        data = MRZTravelerData(
            document_type=data.document_type,
            issuing_country=data.issuing_country,
            surname=data.surname,
            given_names=data.given_names,
            passport_number=data.passport_number,
            nationality=data.nationality,
            birth_date=data.birth_date,
            sex=data.sex,
            expiry_date=data.expiry_date,
            optional_data="ABC",
        )
        _, l2 = encode_mrz(data)
        opt = l2[28:43]
        self.assertTrue(opt.startswith("ABC"))
        self.assertTrue(opt.endswith("<"))

    def test_name_too_long_raises(self):
        # _encode_name_field: raw surname+given exceeds 39 chars
        long_surname = "A" * 30
        long_given = "B" * 15
        data = MRZTravelerData(
            document_type="P<",
            issuing_country="ESP",
            surname=long_surname,
            given_names=long_given,
            passport_number="123456789",
            nationality="ESP",
            birth_date="000101",
            sex="F",
            expiry_date="990101",
            optional_data="<<<<<<<<<<<<<<<",
        )
        with self.assertRaises(MRZFormatError) as ctx:
            encode_mrz(data)
        self.assertIn("name too long", str(ctx.exception))

    def test_field_too_long_passport_raises(self):
        # _pad_field: value longer than max length
        data = _traveler_usa_male()
        data = MRZTravelerData(
            document_type=data.document_type,
            issuing_country=data.issuing_country,
            surname=data.surname,
            given_names=data.given_names,
            passport_number="1234567890",
            nationality=data.nationality,
            birth_date=data.birth_date,
            sex=data.sex,
            expiry_date=data.expiry_date,
            optional_data=data.optional_data,
        )
        with self.assertRaises(MRZFormatError):
            encode_mrz(data)

    def test_internal_line1_length_guard(self):
        # Branch: defensive check if line1 would not be 44 (patched name field)
        data = _traveler_usa_male()
        with patch("MRTD._encode_name_field", return_value="<" * 38):
            with self.assertRaises(MRZFormatError) as ctx:
                encode_mrz(data)
            self.assertIn("line1", str(ctx.exception))

    def test_internal_line2_length_guard(self):
        # Branch: defensive check if line2 would not be 44 (patched optional width)
        data = _traveler_usa_male()
        real_pad = MRTD._pad_field

        def fake_pad(value: str, length: int) -> str:
            if length == 15:
                return real_pad(value, length)[:14]
            return real_pad(value, length)

        with patch("MRTD._pad_field", side_effect=fake_pad):
            with self.assertRaises(MRZFormatError) as ctx:
                encode_mrz(data)
            self.assertIn("line2", str(ctx.exception))


class TestValidateCheckDigits(unittest.TestCase):
    """Tests for validate_check_digits (Req 4)."""

    def test_all_valid_icao_sample(self):
        # No mismatches on valid MRZ
        self.assertEqual(validate_check_digits(L1_ICAO_SAMPLE, L2_ICAO_SAMPLE), [])

    def test_wrong_passport_check_digit(self):
        # Branch: passport check fails; composite usually fails too
        bad = L2_ICAO_SAMPLE[:9] + "0" + L2_ICAO_SAMPLE[10:]
        errs = validate_check_digits(L1_ICAO_SAMPLE, bad)
        names = {e.field_name for e in errs}
        self.assertIn("passport", names)
        self.assertTrue(any(e.expected_check_digit != e.actual_check_digit for e in errs))

    def test_wrong_dob_check_digit(self):
        # Branch: DOB check digit mismatch
        bad = L2_ICAO_SAMPLE[:19] + "0" + L2_ICAO_SAMPLE[20:]
        errs = validate_check_digits(L1_ICAO_SAMPLE, bad)
        self.assertTrue(any(e.field_name == "dob" for e in errs))

    def test_wrong_expiry_check_digit(self):
        # Branch: expiry check digit mismatch
        bad = L2_ICAO_SAMPLE[:27] + "0" + L2_ICAO_SAMPLE[28:]
        errs = validate_check_digits(L1_ICAO_SAMPLE, bad)
        self.assertTrue(any(e.field_name == "expiry" for e in errs))

    def test_wrong_composite_only(self):
        # Corrupt final check digit; composite mismatch reported
        bad = L2_ICAO_SAMPLE[:43] + ("1" if L2_ICAO_SAMPLE[43] == "0" else "0")
        errs = validate_check_digits(L1_ICAO_SAMPLE, bad)
        self.assertTrue(any(e.field_name == "composite" for e in errs))

    def test_mismatch_includes_expected_and_actual(self):
        # Req 4: report expected vs actual check digit
        bad = L2_ICAO_SAMPLE[:9] + "0" + L2_ICAO_SAMPLE[10:]
        for e in validate_check_digits(L1_ICAO_SAMPLE, bad):
            self.assertIsInstance(e, CheckDigitMismatch)
            self.assertTrue(len(e.expected_check_digit) >= 1)
            self.assertTrue(len(e.actual_check_digit) >= 1)


class TestMRTDClassHardwareAndDbMocks(unittest.TestCase):
    """Mock scanner and SQL/DB layer; exercise MRTD facade methods."""

    def test_scan_hardware_not_implemented_by_default(self):
        # Real stub raises until hardware exists
        sys = MRTDSystem()
        with self.assertRaises(NotImplementedError) as ctx:
            sys.scan_mrz_hardware()
        self.assertIn("scanner", str(ctx.exception).lower())

    def test_scan_hardware_mock_returns_lines_then_decode(self):
        # Mock device returns two strings; software decodes them
        with patch.object(
            MRTDSystem,
            "scan_mrz_hardware",
            return_value=(L1_ICAO_SAMPLE, L2_ICAO_SAMPLE),
        ):
            sys = MRTDSystem()
            l1, l2 = sys.scan_mrz_hardware()
            d = sys.decode(l1, l2)
            self.assertEqual(d.surname, "ERIKSSON")

    def test_fetch_db_not_implemented_by_default(self):
        sys = MRTDSystem()
        with self.assertRaises(NotImplementedError):
            sys.fetch_travel_document_from_db("sql-id-001")

    def test_fetch_db_mock_returns_row_then_encode(self):
        # Mock DB returns MRZTravelerData as if from SQL query
        row = _traveler_gbr()
        with patch.object(MRTDSystem, "fetch_travel_document_from_db", return_value=row):
            sys = MRTDSystem()
            data = sys.fetch_travel_document_from_db("UK-42")
            l1, l2 = sys.encode(data)
            self.assertEqual(len(l1), 44)
            self.assertIn("GBR", l1)

    def test_mrtd_validate_check_digits_delegates(self):
        # Instance method calls module-level validator
        sys = MRTDSystem()
        self.assertEqual(
            sys.validate_check_digits(L1_ICAO_SAMPLE, L2_ICAO_SAMPLE),
            [],
        )


def _traveler_gbr() -> MRZTravelerData:
    """GBR (United Kingdom) ICAO code."""
    return MRZTravelerData(
        document_type="P<",
        issuing_country="GBR",
        surname="JONES",
        given_names="ALICE",
        passport_number="123456789",
        nationality="GBR",
        birth_date="850505",
        sex="F",
        expiry_date="300505",
        optional_data="<<<<<<<<<<<<<<<",
    )


class TestPrivateHelpersForCoverage(unittest.TestCase):
    """Direct calls to module-private helpers for branch / statement coverage."""

    def test_decode_name_double_chevron_and_multiple_given_parts(self):
        # Given names split by '<' joined with spaces
        s, g = MRTD._decode_name_field("DOE<<JOHN<ROBERT<<<<<<<<<<<<<<<<<<<")
        self.assertEqual(s, "DOE")
        self.assertEqual(g, "JOHN ROBERT")

    def test_char_value_branches(self):
        # Explicit branches for '<', digit, letter
        self.assertEqual(MRTD._char_value("<"), 0)
        self.assertEqual(MRTD._char_value("5"), 5)
        self.assertEqual(MRTD._char_value("A"), 10)

    def test_validate_line_charset_branch(self):
        # _validate_line second branch: bad charset
        ok_len = "<" * MRZ_LINE_LENGTH
        bad = ok_len[:10] + "!" + ok_len[11:]
        with self.assertRaises(MRZFormatError):
            MRTD._validate_line(bad, "testline")


class TestDataClasses(unittest.TestCase):
    """Smoke tests for dataclass construction (structured outputs)."""

    def test_mrz_decoded_data_fields(self):
        # MRZDecodedData holds all decoded slots
        d = MRZDecodedData(
            document_type="P<",
            issuing_country="CAN",
            surname="X",
            given_names="Y",
            passport_number="123456789",
            nationality="CAN",
            birth_date="000101",
            sex="M",
            expiry_date="000102",
            optional_data="<" * 15,
            check_digit_passport="0",
            check_digit_birth="0",
            check_digit_expiry="0",
            check_digit_composite="0",
        )
        self.assertEqual(d.issuing_country, "CAN")

    def test_check_digit_mismatch_repr_fields(self):
        # CheckDigitMismatch used in validation reports
        m = CheckDigitMismatch("passport", "6", "0")
        self.assertEqual(m.field_name, "passport")


if __name__ == "__main__":
    unittest.main()
