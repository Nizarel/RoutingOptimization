import openpyxl

wb = openpyxl.load_workbook(
    r"data\SLC  Restrictions & Locations2026-03-02.xlsx",
    read_only=True, data_only=True,
)
ws = wb["Locations"]
rows = list(ws.iter_rows(values_only=True))
headers = rows[0]
code_i    = headers.index("Location Code")
desc_i    = headers.index("Description")
type_i    = headers.index("Location Type")
grp_i     = headers.index("Location Group")
enabled_i = list(headers).index("Is Enabled for Site")

print("=== DCs ===")
for r in rows[1:]:
    if r[enabled_i] and r[type_i] and "DC" in str(r[type_i]).upper():
        print(f"  code={r[code_i]}  type={r[type_i]}  desc={r[desc_i]}")

print("\n=== SLC-group (first 10) ===")
count = 0
for r in rows[1:]:
    if r[enabled_i] and r[grp_i] == "SLC":
        print(f"  code={r[code_i]}  type={r[type_i]}  desc={r[desc_i]}")
        count += 1
        if count >= 10:
            break
