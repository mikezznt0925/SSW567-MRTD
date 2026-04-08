import json
import time
import csv
from MRTD import encode_mrz, decode_mrz, MRZTravelerData

INPUT_FILE = "records_decoded.json"
OUTPUT_FILE = "records_encoded.json"
CSV_FILE = "performance.csv"

SIZES = [100] + list(range(1000, 10001, 1000))


# ====== Transform JSON to MRZTravelerData ======
def to_traveler(record):
    return MRZTravelerData(
        document_type="P",  # beginning in the passport P（default）
        issuing_country=record["line1"]["issuing_country"],
        surname=record["line1"]["last_name"],
        given_names=record["line1"]["given_name"],
        passport_number=record["line2"]["passport_number"],
        nationality=record["line2"]["country_code"],
        birth_date=record["line2"]["birth_date"],
        sex=record["line2"]["sex"],
        expiry_date=record["line2"]["expiration_date"],
        optional_data=record["line2"]["personal_number"]
    )


# ====== Read data ======
def load_data():
    with open(INPUT_FILE, "r") as f:
        raw = json.load(f)

    return [to_traveler(r) for r in raw["records_decoded"]]


# ====== Encode and save ======
def encode_all(data):
    with open(OUTPUT_FILE, "w") as f:
        for record in data:
            line1, line2 = encode_mrz(record)
            f.write(f"{line1};{line2}\n")


# ====== Performance testing ======
def measure_time(data, k, use_test=False):
    subset = data[:k]

    # Encode
    start = time.perf_counter()
    encoded = []

    for record in subset:
        line1, line2 = encode_mrz(record)
        encoded.append((line1, line2))

        if use_test:
            assert len(line1) == 44
            assert len(line2) == 44

    encode_time = time.perf_counter() - start

    # Decode
    start = time.perf_counter()

    for line1, line2 in encoded:
        result = decode_mrz(line1, line2)

        if use_test:
            assert result.passport_number != ""

    decode_time = time.perf_counter() - start

    return encode_time, decode_time


# ====== Main ======
def main():
    data = load_data()

    print("Encoding all records...")
    encode_all(data)

    results = []

    print("Running performance tests...")

    for k in SIZES:
        print(f"Testing {k} records...")

        enc_no_test, dec_no_test = measure_time(data, k, False)
        enc_test, dec_test = measure_time(data, k, True)

        results.append([
            k,
            enc_no_test,
            enc_test,
            dec_no_test,
            dec_test
        ])

    # write into CSV
    with open(CSV_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "InputSize",
            "Encode_NoTest",
            "Encode_WithTest",
            "Decode_NoTest",
            "Decode_WithTest"
        ])
        writer.writerows(results)


if __name__ == "__main__":
    main()