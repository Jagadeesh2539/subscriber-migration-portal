#!/usr/bin/env python3
"""
Enhanced Subscriber Model - Rich Data Structure
Supports rich subscriber data structure for RDS and DynamoDB
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional


@dataclass
class BarringControls:
    """Barring controls for subscriber restrictions"""

    barr_all: bool = False  # Bar all outgoing calls
    odbic: str = "notbarred"  # Outgoing Domestic Barring for IC (notbarred, barred)
    odboc: str = "notbarred"  # Outgoing Domestic Barring for OC (notbarred, barred)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BarringControls":
        return cls(
            barr_all=data.get("barr_all", False),
            odbic=data.get("odbic", "notbarred"),
            odboc=data.get("odboc", "notbarred"),
        )


@dataclass
class SubscriberData:
    """Enhanced subscriber data model with rich fields"""

    uid: str
    imsi: str = ""
    msisdn: str = ""
    status: str = "ACTIVE"
    plan_id: Optional[str] = None
    apn: str = ""
    service_profile: str = ""
    roaming_allowed: bool = True
    data_limit: int = 0  # In MB
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    # Enhanced fields
    barring: Optional[BarringControls] = None
    addons: List[str] = None  # List of addon codes
    services: List[str] = None  # List of service codes

    def __post_init__(self):
        if self.addons is None:
            self.addons = []
        if self.services is None:
            self.services = []
        if self.barring is None:
            self.barring = BarringControls()

    def normalize(self):
        """Normalize and clean subscriber data"""
        # Normalize MSISDN to E.164 format
        if self.msisdn and not self.msisdn.startswith("+"):
            self.msisdn = f"+{self.msisdn.lstrip('+')}"

        # Ensure status is uppercase
        self.status = self.status.upper()

        # Set timestamps if not provided
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()
        if not self.updated_at:
            self.updated_at = datetime.utcnow().isoformat()

    def validate(self) -> List[str]:
        """Validate subscriber data and return list of errors"""
        errors = []

        # UID validation
        if not self.uid or len(self.uid) > 50:
            errors.append("UID must be 1-50 characters")

        # IMSI validation (10-15 digits)
        if self.imsi and (not self.imsi.isdigit() or len(self.imsi) < 10 or len(self.imsi) > 15):
            errors.append("IMSI must be 10-15 digits")

        # MSISDN validation (E.164 format)
        if self.msisdn:
            msisdn_clean = self.msisdn.lstrip("+")
            if not msisdn_clean.isdigit() or len(msisdn_clean) < 8 or len(msisdn_clean) > 15:
                errors.append("MSISDN must be valid E.164 format")

        # Status validation
        if self.status not in ["ACTIVE", "INACTIVE", "SUSPENDED", "DELETED"]:
            errors.append("Status must be ACTIVE, INACTIVE, SUSPENDED, or DELETED")

        # Barring controls validation
        if self.barring:
            if self.barring.odbic not in ["notbarred", "barred"]:
                errors.append("ODBIC must be 'notbarred' or 'barred'")
            if self.barring.odboc not in ["notbarred", "barred"]:
                errors.append("ODBOC must be 'notbarred' or 'barred'")

        return errors

    def to_dynamodb_item(self) -> Dict[str, Any]:
        """Convert to DynamoDB item format"""
        item = {
            "subscriberId": self.uid,
            "uid": self.uid,
            "imsi": self.imsi,
            "msisdn": self.msisdn,
            "status": self.status,
            "apn": self.apn,
            "service_profile": self.service_profile,
            "roaming_allowed": self.roaming_allowed,
            "data_limit": Decimal(str(self.data_limit)),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

        # Add enhanced fields
        if self.plan_id:
            item["plan_id"] = self.plan_id

        if self.barring:
            item["barring_controls"] = self.barring.to_dict()

        if self.addons:
            item["addons"] = self.addons

        if self.services:
            item["services"] = self.services

        return item

    def to_mysql_values(self) -> tuple:
        """Convert to MySQL INSERT/UPDATE values tuple"""
        return (
            self.uid,
            self.imsi,
            self.msisdn,
            self.status,
            self.plan_id,
            self.barring.barr_all if self.barring else False,
            self.barring.odbic if self.barring else "notbarred",
            self.barring.odboc if self.barring else "notbarred",
            json.dumps(self.addons) if self.addons else None,
            json.dumps(self.services) if self.services else None,
            self.apn,
            self.service_profile,
            self.roaming_allowed,
            self.data_limit,
            self.created_at,
            self.updated_at,
        )

    @classmethod
    def from_dynamodb_item(cls, item: Dict[str, Any]) -> "SubscriberData":
        """Create from DynamoDB item"""
        barring = None
        if "barring_controls" in item:
            barring = BarringControls.from_dict(item["barring_controls"])

        return cls(
            uid=item.get("uid", ""),
            imsi=item.get("imsi", ""),
            msisdn=item.get("msisdn", ""),
            status=item.get("status", "ACTIVE"),
            plan_id=item.get("plan_id"),
            apn=item.get("apn", ""),
            service_profile=item.get("service_profile", ""),
            roaming_allowed=item.get("roaming_allowed", True),
            data_limit=int(item.get("data_limit", 0)),
            created_at=item.get("created_at"),
            updated_at=item.get("updated_at"),
            barring=barring,
            addons=item.get("addons", []),
            services=item.get("services", []),
        )

    @classmethod
    def from_mysql_row(cls, row: Dict[str, Any]) -> "SubscriberData":
        """Create from MySQL row"""
        # Handle JSON fields
        addons = []
        if row.get("addons"):
            try:
                addons = json.loads(row["addons"])
            except (json.JSONDecodeError, TypeError):
                addons = []

        services = []
        if row.get("services"):
            try:
                services = json.loads(row["services"])
            except (json.JSONDecodeError, TypeError):
                services = []

        # Handle barring controls
        barring = BarringControls(
            barr_all=row.get("barr_all", False),
            odbic=row.get("odbic", "notbarred"),
            odboc=row.get("odboc", "notbarred"),
        )

        # Handle datetime fields
        created_at = row.get("created_at")
        if created_at and hasattr(created_at, "isoformat"):
            created_at = created_at.isoformat()

        updated_at = row.get("updated_at")
        if updated_at and hasattr(updated_at, "isoformat"):
            updated_at = updated_at.isoformat()

        return cls(
            uid=row.get("uid", ""),
            imsi=row.get("imsi", ""),
            msisdn=row.get("msisdn", ""),
            status=row.get("status", "ACTIVE"),
            plan_id=row.get("plan_id"),
            apn=row.get("apn", ""),
            service_profile=row.get("service_profile", ""),
            roaming_allowed=row.get("roaming_allowed", True),
            data_limit=row.get("data_limit", 0),
            created_at=created_at,
            updated_at=updated_at,
            barring=barring,
            addons=addons,
            services=services,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        result = asdict(self)

        # Convert barring to dict if present
        if self.barring:
            result["barring"] = self.barring.to_dict()

        return result
