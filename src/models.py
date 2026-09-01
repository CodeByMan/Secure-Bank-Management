"""English module documentation."""

from datetime import datetime, timedelta, date as py_date
from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, DateTime, Enum, ForeignKey,
    Integer, JSON, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship, declarative_base
import enum
import secrets
from src.config import Config

Base = declarative_base()


class UserRole(enum.Enum):
    """English module documentation."""
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    OPERATOR = "operator"


class OperationType(enum.Enum):
    """English module documentation."""
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"


class AccountStatus(enum.Enum):
    """English module documentation."""
    ACTIVE = "active"
    CLOSED = "closed"
    SUSPENDED = "suspended"


class ClientStatus(enum.Enum):
    """English module documentation."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class PendingStatus(enum.Enum):
    """English module documentation."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


def generate_account_number():
    """English module documentation."""
    return f"CPT{datetime.utcnow().strftime('%y%m%d')}{secrets.randbelow(10**6):06d}"



class User(Base):
    """English module documentation."""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.OPERATOR)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login = Column(DateTime, nullable=True)
    login_attempts = Column(Integer, default=0)

    # English implementation note.
    failed_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime, nullable=True)
    lock_reason = Column(String(500), nullable=True)
    locked_by_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    locked_at = Column(DateTime, nullable=True)

    display_name = Column(String(100), nullable=True)

    # English implementation note.
    mfa_enabled = Column(Boolean, default=False, nullable=False)
    mfa_secret = Column(String(32), nullable=True)
    mfa_backup_codes = Column(Text, nullable=True)

    audit_logs = relationship('AuditLog', back_populates='user', lazy='dynamic')

    def is_locked(self):
        """English module documentation."""
        if self.locked_until is None:
            return False
        return datetime.utcnow() < self.locked_until

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', role='{self.role.value}')>"


class Client(Base):
    """English module documentation."""
    __tablename__ = 'clients'

    id = Column(Integer, primary_key=True, autoincrement=True)
    last_name = Column(String(100), nullable=False)
    first_name = Column(String(100), nullable=False)
    cin = Column(String(20), unique=True, nullable=False, index=True)
    phone = Column(String(20), nullable=False)
    email = Column(String(100), nullable=True)
    address = Column(Text, nullable=True)
    status = Column(Enum(ClientStatus), default=ClientStatus.ACTIVE, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    accounts = relationship('Account', back_populates='client', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Client(id={self.id}, last_name='{self.last_name}', first_name='{self.first_name}', cin='{self.cin}')>"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class Account(Base):
    """English module documentation."""
    __tablename__ = 'accounts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_number = Column(String(20), unique=True, nullable=False, index=True)
    client_id = Column(Integer, ForeignKey('clients.id', ondelete='CASCADE'), nullable=False)
    balance = Column(Numeric(14, 2), default=1000.00, nullable=False)
    status = Column(Enum(AccountStatus), default=AccountStatus.ACTIVE, nullable=False)
    opened_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    client = relationship('Client', back_populates='accounts')
    operations = relationship('Operation', back_populates='account', lazy='dynamic', cascade='all, delete-orphan')
    __table_args__ = (CheckConstraint('balance >= 0', name='ck_account_nonnegative_balance'),)

    def can_withdraw(self, amount):
        """English module documentation."""
        from decimal import Decimal
        amount = Decimal(str(amount))

        if amount <= 0:
            return False
        if amount > Config.WITHDRAWAL_MAXIMUM:
            return False
        return (self.balance - amount) >= Config.MINIMUM_ACCOUNT_BALANCE

    def validate_creation(self, opening_deposit):
        """English module documentation."""
        from decimal import Decimal
        opening_deposit = Decimal(str(opening_deposit))
        return opening_deposit >= Config.MINIMUM_OPENING_BALANCE

    def validate_deposit(self, amount):
        """English module documentation."""
        from decimal import Decimal
        amount = Decimal(str(amount))
        return amount > 0

    def validate_withdrawal(self, amount):
        """English module documentation."""
        return self.can_withdraw(amount)

    def __repr__(self):
        return f"<Account(id={self.id}, account_number='{self.account_number}', balance={self.balance} PKR)>"

class Operation(Base):
    """English module documentation."""
    __tablename__ = 'operations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    operation_type = Column(Enum(OperationType), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    balance_before = Column(Numeric(14, 2), nullable=False)
    balance_after = Column(Numeric(14, 2), nullable=False)
    operation_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    description = Column(Text, nullable=True)

    account = relationship('Account', back_populates='operations')
    user = relationship('User', foreign_keys=[user_id])

    # English implementation note.
    approved_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    approved_by = relationship('User', foreign_keys=[approved_by_id])

    def validate_business_rules(self):
        """English module documentation."""
        if self.amount <= 0:
            raise ValueError("Amount must be greater than zero")

        if self.operation_type == OperationType.DEPOSIT:
            pass

        elif self.operation_type == OperationType.WITHDRAWAL:
            if not self.account.can_withdraw(self.amount):
                raise ValueError(
                    f"Withdrawal denied: limit {Config.WITHDRAWAL_MAXIMUM} {Config.CURRENCY} "
                    f"or insufficient balance (minimum {Config.MINIMUM_ACCOUNT_BALANCE} {Config.CURRENCY})"
                )

    def __repr__(self):
        return f"<Operation(id={self.id}, type='{self.operation_type.value}', amount={self.amount} PKR)>"

    __table_args__ = (
        CheckConstraint('amount > 0', name='ck_operation_positive_amount'),
        CheckConstraint('balance_after >= 0', name='ck_operation_nonnegative_result'),
    )


class AuditLog(Base):
    """English module documentation."""
    __tablename__ = 'audit_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(36), unique=True, nullable=False, index=True)
    sequence = Column(Integer, unique=True, nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    action = Column(String(100), nullable=False, index=True)
    target = Column(String(100), nullable=True)
    details = Column(Text, nullable=True)
    previous_hash = Column(String(64), nullable=True)
    current_hash = Column(String(64), nullable=False, unique=True)
    hmac_signature = Column(String(64), nullable=False)

    user = relationship('User', back_populates='audit_logs')

    def __repr__(self):
        return f"<AuditLog(id={self.id}, action='{self.action}', timestamp='{self.timestamp}')>"


class AuditClosure(Base):
    """English module documentation."""
    __tablename__ = 'audit_closures'

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, unique=True, index=True)
    last_log_id = Column(Integer, ForeignKey('audit_logs.id'), nullable=False)
    root_hash = Column(String(64), nullable=False)
    hmac_signature = Column(String(64), nullable=False)
    closed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    last_log = relationship('AuditLog')

    def __repr__(self):
        return f"<AuditClosure(id={self.id}, date='{self.date}', hash='{self.root_hash[:10]}...')>"


class PendingOperation(Base):
    """English module documentation."""
    __tablename__ = 'pending_operations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    operation_type = Column(String(50), nullable=False)
    payload = Column(JSON, nullable=False)

    created_by_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    approved_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)

    status = Column(Enum(PendingStatus), default=PendingStatus.PENDING, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    approved_at = Column(DateTime, nullable=True)

    decision_reason = Column(String(255), nullable=True)
    decision_comment = Column(Text, nullable=True)

    created_by = relationship('User', foreign_keys=[created_by_id])
    approved_by = relationship('User', foreign_keys=[approved_by_id])

    __table_args__ = (
        CheckConstraint(
            'approved_by_id IS NULL OR approved_by_id != created_by_id',
            name='ck_maker_differs_from_checker',
        ),
    )

    def __repr__(self):
        return f"<PendingOperation(id={self.id}, type='{self.operation_type}', status='{self.status.value}')>"


class Policy(Base):
    """English module documentation."""
    __tablename__ = 'policies'

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(255), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=False)
    type = Column(String(50), nullable=False, default='string')
    description = Column(Text, nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Policy(key='{self.key}', type='{self.type}', active={self.active})>"


class PolicyHistory(Base):
    """English module documentation."""
    __tablename__ = 'policy_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    policy_id = Column(Integer, ForeignKey('policies.id'), nullable=False)
    key = Column(String(255), nullable=False)
    value = Column(Text, nullable=False)
    type = Column(String(50), nullable=False, default='string')
    updated_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    comment = Column(Text, nullable=True)

    def __repr__(self):
        return f"<PolicyHistory(policy_id={self.policy_id}, key='{self.key}', updated_at='{self.updated_at.isoformat()}')>"
