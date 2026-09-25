from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

CLASSIFICATION_DESCRIPTIONS = {
    "A": "General Engineering Contractor",
    "B": "General Building Contractor",
    "B-2": "Residential Remodeling Contractor",
    "C-2": "Insulation and Acoustical Contractor",
    "C-4": "Boiler, Hot Water Heating and Steam Fitting Contractor",
    "C-5": "Framing and Rough Carpentry Contractor",
    "C-6": "Cabinet, Millwork and Finish Carpentry Contractor",
    "C-7": "Low Voltage Systems Contractor",
    "C-8": "Concrete Contractor",
    "C-9": "Drywall Contractor",
    "C10": "Electrical Contractor",
    "C11": "Elevator Contractor",
    "C12": "Earthwork and Paving Contractor",
    "C13": "Fencing Contractor",
    "C15": "Flooring and Floor Covering Contractor",
    "C16": "Fire Protection Contractor",
    "C17": "Glazing Contractor",
    "C20": "Warm-Air Heating, Ventilating and Air-Conditioning Contractor",
    "C21": "Building Moving/Demolition Contractor",
    "C22": "Asbestos Abatement Contractor",
    "C23": "Ornamental Metal Contractor",
    "C27": "Landscaping Contractor",
    "C28": "Lock and Security Equipment Contractor",
    "C29": "Masonry Contractor",
    "C31": "Construction Zone Traffic Control Contractor",
    "C32": "Parking and Highway Improvement Contractor",
    "C33": "Painting and Decorating Contractor",
    "C34": "Pipeline Contractor",
    "C35": "Lathing and Plastering Contractor",
    "C36": "Plumbing Contractor",
    "C38": "Refrigeration Contractor",
    "C39": "Roofing Contractor",
    "C42": "Sanitation System Contractor",
    "C43": "Sheet Metal Contractor",
    "C45": "Sign Contractor",
    "C46": "Solar Contractor",
    "C47": "General Manufactured Housing Contractor",
    "C49": "Tree and Palm Contractor",
    "C50": "Reinforcing Steel Contractor",
    "C51": "Structural Steel Contractor",
    "C53": "Swimming Pool Contractor",
    "C54": "Ceramic and Mosaic Tile Contractor",
    "C55": "Water Conditioning Contractor",
    "C57": "Well Drilling Contractor",
    "C60": "Welding Contractor",
    "D03": "Awnings Contractor",
    "D04": "Central Vacuum Systems Contractor",
    "D06": "Concrete-Related Services Contractor",
    "D09": "Drilling, Blasting and Oil Field Work Contractor",
    "D10": "Elevated Floors Contractor",
    "D12": "Synthetic Products Contractor",
    "D16": "Hardware, Locks and Safes Contractor",
    "D21": "Machinery and Pumps Contractor",
    "D24": "Metal Products Contractor",
    "D28": "Doors, Gates and Activating Devices Contractor",
    "D29": "Paperhanging Contractor",
    "D30": "Pile Driving and Pressure Foundation Jacking Contractor",
    "D31": "Pole Installation and Maintenance Contractor",
    "D34": "Prefabricated Equipment Contractor",
    "D35": "Pool and Spa Maintenance Contractor",
    "D38": "Sand and Water Blasting Contractor",
    "D39": "Scaffolding Contractor",
    "D40": "Service Station Equipment and Maintenance Contractor",
    "D41": "Siding and Decking Contractor",
    "D42": "Non-Electrical Sign Installation",
    "D49": "Tree Service Contractor",
    "D50": "Suspended Ceilings Contractor",
    "D52": "Window Coverings Contractor",
    "D53": "Wood Tanks Contractor",
    "D56": "Trenching Only Contractor",
    "D59": "Hydroseed Spraying Contractor",
    "D62": "Air and Water Balancing Contractor",
    "D63": "Construction Clean-up Contractor",
    "D64": "Non-specialized Contractor",
    "D65": "Weatherization and Energy Conservation Contractor",
    "ASB": "Asbestos Certification",
    "HAZ": "Hazardous Substance Removal Certification",
}


def clean(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def parse_date(value: Any) -> date | None:
    if value is None or clean(value) is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value).strip(), "%m/%d/%Y").date()


def parse_classifications(value: Any) -> list[str]:
    raw = clean(value)
    if not raw:
        return []
    result: list[str] = []
    for item in raw.split("|"):
        code = re.sub(r"\s+", "", item).upper()
        if code and code not in result:
            result.append(code)
    return result


def normalize_phone(value: Any) -> str | None:
    raw = clean(value)
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits or None


def json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def row_digest(record: dict[str, Any]) -> str:
    canonical = json.dumps(
        {k: json_value(v) for k, v in record.items()},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()
