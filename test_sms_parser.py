from sms_parser import parse_bank_sms, find_member_by_name

ACCOUNT = "1019476"

real_messages = [
    "Dear POWER T/A  power leaders inv ltd, you have received Ksh. 1000.0 from Meshack Mutinda for 1019476 on 08/01/2026 at 09:48:42. MPESA Ref. UH18122I8A..",
    "Dear POWER T/A  power leaders inv ltd, you have received Ksh. 500.0 from DANIEL MUIA for 1019476 on 08/10/2026 at 13:46:52. MPESA Ref. UHAPR2ITMD..",
    "Dear POWER T/A  power leaders inv ltd, you have received Ksh. 1000.0 from DUNCAN MULI for 1019476 on 08/10/2026 at 19:47:04. MPESA Ref. UHADU2W52C..",
    "Dear POWER T/A  power leaders inv ltd, you have received Ksh. 2000.0 from Joyce Muasya for 1019476 on 08/20/2026 at 10:11:41. MPESA Ref. UHKDW3KZV2..",
    "Dear POWER T/A  power leaders inv ltd, you have received Ksh. 3000.0 from Joyce Muasya for 1019476 on 09/11/2026 at 16:39:11. MPESA Ref. UIBDW68462..",
]

members = [
    {"name": "Meshack Mutinda", "phone": "0799660888"},
    {"name": "Daniel Muia", "phone": "0798918541"},
    {"name": "Duncan Muli", "phone": "0797316296"},
    {"name": "Joseph Muasya", "phone": "0798217728", "aliases": ["Joyce Muasya"]},
]

print("=== REAL BANK MESSAGES ===")
for text in real_messages:
    result = parse_bank_sms(text, expected_account=ACCOUNT)
    if result is None:
        print("NOT PARSED:", text[:60])
        continue
    member = find_member_by_name(members, result["payer_name"])
    who = member["name"] if member else "-> SUSPENSE POOL"
    print(f"{result['date']} | KES {result['amount']:>8,.2f} | {result['payer_name']:<16} | {result['mpesa_ref']:<11} | {who}")

print()
print("=== MESSAGES THAT MUST BE IGNORED ===")
ignored = {
    "Personal text": "Bring bread on your way home",
    "Outgoing alert": "Dear POWER T/A power leaders inv ltd, you have paid Ksh. 500.0 to KPLC on 08/10/2026 at 13:46:52.",
    "Wrong account": "Dear POWER T/A  power leaders inv ltd, you have received Ksh. 500.0 from DANIEL MUIA for 9999999 on 08/10/2026 at 13:46:52. MPESA Ref. UHAPR2ITMD..",
}
for label, text in ignored.items():
    result = parse_bank_sms(text, expected_account=ACCOUNT)
    print(f"{label:<15}: {'IGNORED (correct)' if result is None else 'WRONGLY ACCEPTED'}")

print()
print("=== NON-MEMBER PAYER ===")
stranger = parse_bank_sms(
    "Dear POWER T/A  power leaders inv ltd, you have received Ksh. 700.0 from PETER KAMAU for 1019476 on 09/12/2026 at 08:00:00. MPESA Ref. UIXX11AA22..",
    expected_account=ACCOUNT,
)
match = find_member_by_name(members, stranger["payer_name"])
print(f"{stranger['payer_name']} -> {'member' if match else 'no match, goes to SUSPENSE POOL'}")