"""Small, explicit MCC/MNC display table for LTE diagnostics.

The table intentionally focuses on German assignments plus the live-confirmed
home network used by the tested modem SIM.  Unknown networks stay unknown; this
module must never infer an operator name from free-form modem text.

German allocations: Bundesnetzagentur IMSI allocations, status 2026-02-24.
208/01: ARCEP open mobile data identifies Orange France.
"""

from __future__ import annotations

from dataclasses import dataclass


# Current German MCC/MNC allocation holders published by Bundesnetzagentur.
# Multiple MNCs can intentionally map to the same allocation holder.
OPERATORS: dict[tuple[int, int], str] = {
    (262, 1): "Telekom Deutschland GmbH",
    (262, 2): "Vodafone GmbH",
    (262, 3): "Telefónica Germany GmbH & Co. oHG",
    (262, 4): "Vodafone GmbH",
    (262, 5): "Telefónica Germany GmbH & Co. oHG",
    (262, 6): "Telekom Deutschland GmbH",
    (262, 7): "Telefónica Germany GmbH & Co. oHG",
    (262, 8): "Telefónica Germany GmbH & Co. oHG",
    (262, 9): "Vodafone GmbH",
    (262, 10): "DB Netz AG",
    (262, 11): "Telefónica Germany GmbH & Co. oHG",
    (262, 12): "Telefónica Germany GmbH & Co. oHG",
    (262, 13): "BAAINBw",
    (262, 14): "Lebara Limited",
    (262, 15): "Airdata AG",
    (262, 18): "NetCologne GmbH",
    (262, 19): "Inquam Deutschland GmbH",
    (262, 20): "Telefónica Germany GmbH & Co. oHG",
    (262, 21): "spusu Deutschland GmbH",
    (262, 22): "sipgate Wireless GmbH",
    (262, 23): "Drillisch Netz AG",
    (262, 24): "TelcoVillage GmbH",
    (262, 25): "MTEL Deutschland GmbH",
    (262, 26): "Simsalasim Germany GmbH",
    (262, 42): "Vodafone GmbH",
    (262, 43): "Vodafone GmbH",
    (262, 70): "BDBOS",
    # Live SIM in the reverse-engineering fixture; official ARCEP mapping.
    (208, 1): "Orange France",
}


@dataclass(frozen=True, slots=True)
class OperatorIdentity:
    mcc: int
    mnc: int
    name: str | None = None

    @property
    def code(self) -> str:
        return f"{self.mcc:03d} / {self.mnc:02d}"

    @property
    def display(self) -> str:
        if self.name:
            return f"{self.name} ({self.code})"
        return self.code


def lookup_operator(mcc: int | None, mnc: int | None) -> OperatorIdentity | None:
    if mcc is None or mnc is None:
        return None
    if not (0 <= int(mcc) <= 999 and 0 <= int(mnc) <= 999):
        return None
    mcc_value = int(mcc)
    mnc_value = int(mnc)
    return OperatorIdentity(mcc_value, mnc_value, OPERATORS.get((mcc_value, mnc_value)))


def home_operator_from_imsi(imsi: str | None) -> OperatorIdentity | None:
    """Resolve only IMSI prefixes whose MNC length is known in our local table.

    Germany (262) uses two-digit MNCs in the BNetzA IMSI plan.  The explicitly
    supported French Orange prefix 208/01 is also two digits.  Unknown countries
    are deliberately not guessed because E.212 MNC length may be two or three
    digits depending on the allocation.
    """
    digits = "".join(ch for ch in str(imsi or "") if ch.isdigit())
    if len(digits) < 5:
        return None
    try:
        mcc = int(digits[:3])
        mnc = int(digits[3:5])
    except ValueError:
        return None
    identity = lookup_operator(mcc, mnc)
    if identity and ((mcc == 262) or (mcc, mnc) == (208, 1)):
        return identity
    return None
