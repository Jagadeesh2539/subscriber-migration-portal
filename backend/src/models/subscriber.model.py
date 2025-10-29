#!/usr/bin/env python3
"""
Enhanced Subscriber Model - Rich Data Structure
Supports rich subscriber data structure for RDS and DynamoDB
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union


@dataclass
class BarringControls:
    """Barring and control flags"""
    bar_all: bool = False  # Maps from BARRRING yes/no
    odbic: str = 'notbarred'  # barred | notbarred
    odboc: str = 'notbarred'  # barred | notbarred
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'barAll': self.bar_all,
            'odbic': self.odbic,
            'odboc': self.odboc
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BarringControls':
        return cls(
            bar_all=data.get('barAll', False),
            odbic=data.get('odbic', 'notbarred'),
            odboc=data.get('odboc', 'notbarred')
        )
    
    @classmethod
    def from_legacy(cls, barr_all: Union[int, bool], odbic: str, odboc: str) -> 'BarringControls':
        """Create from legacy MySQL format"""
        return cls(
            bar_all=bool(barr_all),
            odbic=odbic if odbic in ['barred', 'notbarred'] else 'notbarred',
            odboc=odboc if odboc in ['barred', 'notbarred'] else 'notbarred'
        )

@dataclass
class SubscriberData:
    """Enhanced subscriber data structure"""
    # Core identifiers
    uid: str
    imsi: str = ''
    msisdn: str = ''
    
    # Status and plan
    status: str = 'ACTIVE'  # ACTIVE | INACTIVE | SUSPENDED | DELETED
    plan_id: str = ''
    
    # Barring controls
    barring: Optional[BarringControls] = None
    
    # Feature bundles
    addons: List[str] = None
    services: List[str] = None
    
    # Network settings
    apn: str = ''
    service_profile: str = ''
    roaming_allowed: bool = True
    data_limit: Optional[int] = None
    
    # Metadata
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    source_system: Optional[str] = None
    migrated_from: Optional[str] = None
    migrated_at: Optional[str] = None
    
    def __post_init__(self):
        if self.addons is None:
            self.addons = []
        if self.services is None:
            self.services = []
        if self.barring is None:
            self.barring = BarringControls()
    
    def to_dynamodb_item(self) -> Dict[str, Any]:
        """Convert to DynamoDB item format"""
        item = {
            'subscriberId': self.uid,
            'uid': self.uid,
            'imsi': self.imsi,
            'msisdn': self.msisdn,
            'status': self.status,
            'planId': self.plan_id,
            'barring': self.barring.to_dict() if self.barring else BarringControls().to_dict(),
            'addons': self.addons,
            'services': self.services,
            'apn': self.apn,
            'service_profile': self.service_profile,
            'roaming_allowed': self.roaming_allowed,
            'created_at': self.created_at or datetime.utcnow().isoformat(),
            'updated_at': self.updated_at or datetime.utcnow().isoformat()
        }
        
        # Add optional fields
        if self.data_limit is not None:
            item['data_limit'] = Decimal(str(self.data_limit))
        
        if self.source_system:
            item['source_system'] = self.source_system
        
        if self.migrated_from:
            item['migrated_from'] = self.migrated_from
            item['migrated_at'] = self.migrated_at or datetime.utcnow().isoformat()
        
        return item
    
    def to_mysql_values(self) -> tuple:
        """Convert to MySQL INSERT/UPDATE values"""
        return (
            self.uid,
            self.imsi,
            self.msisdn,
            self.status,
            self.plan_id,
            1 if (self.barring and self.barring.bar_all) else 0,
            self.barring.odbic if self.barring else 'notbarred',
            self.barring.odboc if self.barring else 'notbarred',
            json.dumps(self.addons) if self.addons else None,
            json.dumps(self.services) if self.services else None,
            self.apn,
            self.service_profile,
            1 if self.roaming_allowed else 0,
            self.data_limit,
            self.created_at or datetime.utcnow().isoformat(),
            self.updated_at or datetime.utcnow().isoformat()
        )
    
    def to_mysql_update_values(self, uid: str) -> tuple:
        """Convert to MySQL UPDATE values with WHERE uid"""
        values = list(self.to_mysql_values()[1:])  # Skip uid (first field)
        values.append(uid)  # Add uid for WHERE clause
        return tuple(values)
    
    @classmethod
    def from_dynamodb_item(cls, item: Dict[str, Any]) -> 'SubscriberData':
        """Create from DynamoDB item"""
        barring_data = item.get('barring', {})
        barring = BarringControls.from_dict(barring_data) if barring_data else BarringControls()
        
        return cls(
            uid=item.get('uid', item.get('subscriberId', '')),
            imsi=item.get('imsi', ''),
            msisdn=item.get('msisdn', ''),
            status=item.get('status', 'ACTIVE'),
            plan_id=item.get('planId', ''),
            barring=barring,
            addons=item.get('addons', []),
            services=item.get('services', []),
            apn=item.get('apn', ''),
            service_profile=item.get('service_profile', ''),
            roaming_allowed=item.get('roaming_allowed', True),
            data_limit=int(item['data_limit']) if item.get('data_limit') else None,
            created_at=item.get('created_at'),
            updated_at=item.get('updated_at'),
            source_system=item.get('source_system'),
            migrated_from=item.get('migrated_from'),
            migrated_at=item.get('migrated_at')
        )
    
    @classmethod
    def from_mysql_row(cls, row: Dict[str, Any]) -> 'SubscriberData':
        """Create from MySQL row"""
        # Parse JSON fields
        addons = []
        services = []
        
        try:
            if row.get('addons'):
                addons = json.loads(row['addons'])
        except (json.JSONDecodeError, TypeError):
            addons = []
        
        try:
            if row.get('services'):
                services = json.loads(row['services'])
        except (json.JSONDecodeError, TypeError):
            services = []
        
        # Create barring controls
        barring = BarringControls.from_legacy(
            row.get('barr_all', 0),
            row.get('odbic', 'notbarred'),
            row.get('odboc', 'notbarred')
        )
        
        return cls(
            uid=row.get('uid', ''),
            imsi=row.get('imsi', ''),
            msisdn=row.get('msisdn', ''),
            status=row.get('status', 'ACTIVE'),
            plan_id=row.get('plan_id', ''),
            barring=barring,
            addons=addons,
            services=services,
            apn=row.get('apn', ''),
            service_profile=row.get('service_profile', ''),
            roaming_allowed=bool(row.get('roaming_allowed', 1)),
            data_limit=row.get('data_limit'),
            created_at=row.get('created_at').isoformat() if row.get('created_at') else None,
            updated_at=row.get('updated_at').isoformat() if row.get('updated_at') else None
        )
    
    @classmethod
    def from_api_payload(cls, data: Dict[str, Any]) -> 'SubscriberData':
        """Create from API request payload"""
        # Handle barring field
        barring = None
        if 'barring' in data:
            if isinstance(data['barring'], dict):
                barring = BarringControls.from_dict(data['barring'])
            elif str(data['barring']).lower() in ['yes', 'true', '1']:
                # Legacy BARRRING field
                barring = BarringControls(bar_all=True)
        
        return cls(
            uid=data.get('uid', ''),
            imsi=data.get('imsi', ''),
            msisdn=data.get('msisdn', ''),
            status=data.get('status', 'ACTIVE'),
            plan_id=data.get('planId', data.get('plan_id', '')),
            barring=barring or BarringControls(),
            addons=data.get('addons', []),
            services=data.get('services', []),
            apn=data.get('apn', ''),
            service_profile=data.get('service_profile', ''),
            roaming_allowed=data.get('roaming_allowed', True),
            data_limit=data.get('data_limit'),
            source_system=data.get('source_system')
        )
    
    def validate(self) -> List[str]:
        """Validate subscriber data and return list of errors"""
        errors = []
        
        # Validate required fields
        if not self.uid or len(self.uid.strip()) == 0:
            errors.append('UID is required')
        elif len(self.uid) > 64:
            errors.append('UID must be 64 characters or less')
        
        # Validate IMSI (10-20 digits)
        if self.imsi:
            if not self.imsi.isdigit() or len(self.imsi) < 10 or len(self.imsi) > 20:
                errors.append('IMSI must be 10-20 digits')
        
        # Validate MSISDN
        if self.msisdn:
            # Remove + if present for validation
            msisdn_digits = self.msisdn.replace('+', '').replace('-', '').replace(' ', '')
            if not msisdn_digits.isdigit() or len(msisdn_digits) < 10 or len(msisdn_digits) > 15:
                errors.append('MSISDN must be 10-15 digits (E.164 format preferred)')
        
        # Validate status
        if self.status not in ['ACTIVE', 'INACTIVE', 'SUSPENDED', 'DELETED']:
            errors.append('Status must be one of: ACTIVE, INACTIVE, SUSPENDED, DELETED')
        
        # Validate planId
        if self.plan_id and len(self.plan_id) > 64:
            errors.append('Plan ID must be 64 characters or less')
        
        # Validate barring controls
        if self.barring:
            if self.barring.odbic not in ['barred', 'notbarred']:
                errors.append('ODBIC must be "barred" or "notbarred"')
            if self.barring.odboc not in ['barred', 'notbarred']:
                errors.append('ODBOC must be "barred" or "notbarred"')
        
        # Validate addons (uppercase tokens)
        if self.addons:
            for addon in self.addons:
                if not isinstance(addon, str) or len(addon.strip()) == 0:
                    errors.append('All addons must be non-empty strings')
                    break
                if len(addon) > 32:
                    errors.append(f'Addon "{addon}" too long (max 32 characters)')
        
        # Validate services (uppercase tokens)
        if self.services:
            for service in self.services:
                if not isinstance(service, str) or len(service.strip()) == 0:
                    errors.append('All services must be non-empty strings')
                    break
                if len(service) > 32:
                    errors.append(f'Service "{service}" too long (max 32 characters)')
        
        # Validate data limit
        if self.data_limit is not None and self.data_limit < 0:
            errors.append('Data limit must be 0 or greater')
        
        return errors
    
    def normalize(self):
        """Normalize data fields in place"""
        # Trim strings
        self.uid = self.uid.strip() if self.uid else ''
        self.imsi = self.imsi.strip() if self.imsi else ''
        self.msisdn = self.msisdn.strip() if self.msisdn else ''
        self.plan_id = self.plan_id.strip() if self.plan_id else ''
        self.apn = self.apn.strip() if self.apn else ''
        self.service_profile = self.service_profile.strip() if self.service_profile else ''
        
        # Normalize status
        self.status = self.status.upper() if self.status else 'ACTIVE'
        
        # Normalize MSISDN (basic E.164)
        if self.msisdn and not self.msisdn.startswith('+'):
            # Add + if looks like international format starting with country code
            if len(self.msisdn) > 10 and self.msisdn.startswith(('1', '44', '49', '33', '39', '91')):
                self.msisdn = '+' + self.msisdn
        
        # Normalize barring controls
        if self.barring:
            self.barring.odbic = self.barring.odbic.lower() if self.barring.odbic else 'notbarred'
            self.barring.odboc = self.barring.odboc.lower() if self.barring.odboc else 'notbarred'
        
        # Normalize addons and services (uppercase, no spaces)
        if self.addons:
            self.addons = [addon.upper().replace(' ', '_') for addon in self.addons if addon.strip()]
        
        if self.services:
            self.services = [service.upper().replace(' ', '_') for service in self.services if service.strip()]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        result = {
            'uid': self.uid,
            'imsi': self.imsi,
            'msisdn': self.msisdn,
            'status': self.status,
            'planId': self.plan_id,
            'barring': self.barring.to_dict() if self.barring else BarringControls().to_dict(),
            'addons': self.addons,
            'services': self.services,
            'apn': self.apn,
            'service_profile': self.service_profile,
            'roaming_allowed': self.roaming_allowed,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }
        
        if self.data_limit is not None:
            result['data_limit'] = self.data_limit
        
        if self.source_system:
            result['source_system'] = self.source_system
        
        if self.migrated_from:
            result['migrated_from'] = self.migrated_from
            result['migrated_at'] = self.migrated_at
        
        return result
    
    def get_mysql_schema(self) -> str:
        """Get MySQL table schema for this model"""
        return """
        CREATE TABLE IF NOT EXISTS subscribers (
            uid VARCHAR(64) PRIMARY KEY,
            imsi VARCHAR(32) UNIQUE,
            msisdn VARCHAR(32) UNIQUE,
            status ENUM('ACTIVE','INACTIVE','SUSPENDED','DELETED') DEFAULT 'ACTIVE',
            plan_id VARCHAR(64),
            barr_all TINYINT(1) DEFAULT 0,
            odbic ENUM('barred','notbarred') DEFAULT 'notbarred',
            odboc ENUM('barred','notbarred') DEFAULT 'notbarred',
            addons JSON,
            services JSON,
            apn VARCHAR(64),
            service_profile VARCHAR(64),
            roaming_allowed TINYINT(1) DEFAULT 1,
            data_limit BIGINT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            
            INDEX idx_imsi (imsi),
            INDEX idx_msisdn (msisdn),
            INDEX idx_status (status),
            INDEX idx_plan_id (plan_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
    
    def get_dynamodb_table_definition(self) -> Dict[str, Any]:
        """Get DynamoDB table definition for this model"""
        return {
            'TableName': 'subscriber-table',
            'KeySchema': [
                {'AttributeName': 'subscriberId', 'KeyType': 'HASH'}
            ],
            'AttributeDefinitions': [
                {'AttributeName': 'subscriberId', 'AttributeType': 'S'},
                {'AttributeName': 'msisdn', 'AttributeType': 'S'},
                {'AttributeName': 'imsi', 'AttributeType': 'S'},
                {'AttributeName': 'planId', 'AttributeType': 'S'}
            ],
            'GlobalSecondaryIndexes': [
                {
                    'IndexName': 'msisdn-index',
                    'KeySchema': [{'AttributeName': 'msisdn', 'KeyType': 'HASH'}],
                    'Projection': {'ProjectionType': 'ALL'},
                    'BillingMode': 'PAY_PER_REQUEST'
                },
                {
                    'IndexName': 'imsi-index',
                    'KeySchema': [{'AttributeName': 'imsi', 'KeyType': 'HASH'}],
                    'Projection': {'ProjectionType': 'ALL'},
                    'BillingMode': 'PAY_PER_REQUEST'
                },
                {
                    'IndexName': 'planId-index',
                    'KeySchema': [{'AttributeName': 'planId', 'KeyType': 'HASH'}],
                    'Projection': {'ProjectionType': 'ALL'},
                    'BillingMode': 'PAY_PER_REQUEST'
                }
            ],
            'BillingMode': 'PAY_PER_REQUEST',
            'Tags': [
                {'Key': 'Environment', 'Value': 'Production'},
                {'Key': 'Service', 'Value': 'SubscriberMigrationPortal'}
            ]
        }