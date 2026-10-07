import re
from datetime import datetime

# Matches the Co-op Bank deposit notification, e.g.
# "Dear POWER T/A  power leaders inv ltd, you have received Ksh. 500.0 from
#  DANIEL MUIA for 1019476 on 08/10/2026 at 13:46:52. MPESA Ref. UHAPR2ITMD.."
SMS_PATTERN = re.compile(
    r"you\s+have\s+received\s+Ksh\.?\s*(?P<amount>[\d,]+(?:\.\d+)?)"
    r"\s+from\s+(?P<name>.+?)"
    r"\s+for\s+(?P<account>\d+)"
    r"\s+on\s+(?P<date>\d{1,2}/\d{1,2}/\d{4})"
    r"\s+at\s+(?P<time>\d{1,2}:\d{2}:\d{2})"
    r"\.?\s*MPESA\s+Ref\.?\s*(?P<ref>[A-Za-z0-9]+)",
    re.IGNORECASE | re.DOTALL,
)


def normalize_name(name):
    """Uppercase and collapse extra spaces so 'Daniel  muia' == 'DANIEL MUIA'."""
    return " ".join((name or "").upper().split())


def parse_bank_sms(text, expected_account=None):
    """
    Returns a dict of payment details if the text is a valid deposit
    notification, otherwise None.
    """
    match = SMS_PATTERN.search(text or "")
    if not match:
        return None

    account = match.group("account")
    if expected_account and account != str(expected_account):
        return None

    try:
        amount = float(match.group("amount").replace(",", ""))
        # The bank writes dates as MM/DD/YYYY
        paid_at = datetime.strptime(
            f"{match.group('date')} {match.group('time')}", "%m/%d/%Y %H:%M:%S"
        )
    except ValueError:
        return None

    raw_name = " ".join(match.group("name").split())

    return {
        "amount": amount,
        "payer_name": raw_name,
        "payer_name_normalized": normalize_name(raw_name),
        "account": account,
        "date": paid_at.strftime("%Y-%m-%d"),
        "time": paid_at.strftime("%H:%M:%S"),
        "mpesa_ref": match.group("ref").upper(),
    }


def find_member_by_name(members, payer_name):
    """
    Looks for a member whose name (or any saved alias) matches the payer name.
    Returns the member dict, or None if there is no match.
    """
    target = normalize_name(payer_name)
    for member in members:
        names = [member["name"]] + member.get("aliases", [])
        if any(normalize_name(n) == target for n in names):
            return member
    return None