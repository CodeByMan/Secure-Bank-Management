"""English module documentation."""

import functools
import pyotp
import io
import base64
import qrcode
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for
)
from passlib.hash import bcrypt
from src.db import get_session
from src.models import User, UserRole
from src.config import Config
from datetime import datetime, timedelta

# English implementation note.
GENERIC_LOGIN_ERROR = "Invalid username or password."

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

def login_required(view):
    """English module documentation."""
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('auth.login'))

        return view(**kwargs)

    return wrapped_view

def admin_required(view):
    """English module documentation."""
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('auth.login'))

        if g.user.role not in [UserRole.ADMIN, UserRole.SUPERADMIN]:
            # English implementation note.
            from src.audit_logger import log_action
            log_action(g.user.id, "ACCESS_DENIED", "Admin required", {"path": request.path})
            flash("Administrator access is required.", "danger")
            return redirect(url_for('home'))

        return view(**kwargs)

    return wrapped_view

def operator_required(view):
    """English module documentation."""
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('auth.login'))

        if g.user.role not in [UserRole.OPERATOR, UserRole.ADMIN, UserRole.SUPERADMIN]:
            # English implementation note.
            from src.audit_logger import log_action
            log_action(g.user.id, "ACCESS_DENIED", "Operator required", {"path": request.path})
            flash("Access denied.", "danger")
            return redirect(url_for('home'))

        return view(**kwargs)

    return wrapped_view


# English implementation note.
PERMISSION_MAP = {
    UserRole.SUPERADMIN.name: {'*'},
    UserRole.ADMIN.name: {
        'clients.view', 'clients.create', 'clients.update',
        'clients.deactivate','clients.reactivate','clients.archived',
        'accounts.view', 'accounts.create', 'accounts.close',
        'operations.create', 'operations.view',
        'audit.view', 'users.view', 'users.create', 'users.update', 'users.deactivate', 'users.reactivate',
        'policies.view', 'policies.create', 'policies.edit', 'policies.toggle', 'policies.apply',
        'approvals.view', 'approvals.approve', 'approvals.reject'
    },
    UserRole.OPERATOR.name: {
        'clients.view', 'clients.create', 'clients.update',
        'clients.deactivate','clients.reactivate',
        'accounts.view', 'accounts.create', 'accounts.close',
        'operations.create', 'operations.view'
    },
    'clients.suspend': set(),
    'clients.deactivate': set(),
    'clients.archived': set(),
    'clients.reactivate': set(),
    'policies.history': set(),
}


def has_permission(user, perm: str) -> bool:
    """English module documentation."""
    if user is None:
        return False
    role_name = user.role.name if hasattr(user.role, 'name') else str(user.role)
    perms = PERMISSION_MAP.get(role_name, set())
    return '*' in perms or perm in perms


def permission_required(perm: str):
    """English module documentation."""
    def decorator(view):
        @functools.wraps(view)
        def wrapped_view(*args, **kwargs):
            from flask import g, request, url_for
            from src.audit_logger import log_action

            if g.user is None:
                return redirect(url_for('auth.login'))

            if not has_permission(g.user, perm):
                try:
                    log_action(g.user.id if g.user else None, 'ACCESS_DENIED', perm, {'path': request.path})
                except Exception:
                    pass
                flash("Insufficient permission.", 'danger')
                return redirect(url_for('home'))

            return view(*args, **kwargs)

        return wrapped_view
    return decorator

@auth_bp.before_app_request
def load_logged_in_user():
    """English module documentation."""
    user_id = session.get('user_id')

    if user_id is None:
        g.user = None
    else:
        last_activity = session.get('last_activity')
        if last_activity:
            from src.policy import get_policy
            timeout = int(get_policy('session.timeout_seconds', Config.SESSION_TIMEOUT))
            if datetime.utcnow() - datetime.fromisoformat(last_activity) > timedelta(seconds=timeout):
                # English implementation note.
                try:
                    from src.audit_logger import log_action
                    duration = (datetime.utcnow() - datetime.fromisoformat(last_activity)).total_seconds()
                    log_action(user_id, "SESSION_EXPIRED", "System",
                               {"inactive_seconds": int(duration), "timeout": timeout})
                except Exception:
                    pass
                session.clear()
                g.user = None
                return

        session['last_activity'] = datetime.utcnow().isoformat()

        db_session = get_session()
        g.user = db_session.query(User).filter_by(id=user_id).first()

@auth_bp.route('/login', methods=('GET', 'POST'))
def login():
    """English module documentation."""
    if g.user:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        db_session = get_session()
        error = None

        user = db_session.query(User).filter_by(username=username).first()

        if user is None:
            # English implementation note.
            error = GENERIC_LOGIN_ERROR
            # English implementation note.
            from src.audit_logger import log_action
            log_action(None, "LOGIN_FAILED", "System",
                      {"username": username, "reason": "user_not_found", "user_id": None})
        else:
            user_id_local = user.id
            if not user.is_active:
                error = GENERIC_LOGIN_ERROR
                # English implementation note.
                from src.audit_logger import log_action
                log_action(user_id_local, "LOGIN_FAILED", "System",
                          {"username": username, "user_id": user_id_local, "reason": "account_inactive"})

            elif user.is_locked():
                error = GENERIC_LOGIN_ERROR
                # English implementation note.
                from src.audit_logger import log_action
                log_action(user_id_local, "LOGIN_FAILED", "System",
                          {"username": username, "user_id": user_id_local, "reason": "account_locked"})

            elif not bcrypt.verify(password, user.password_hash):
                error = GENERIC_LOGIN_ERROR
                # English implementation note.
                user.login_attempts = (user.login_attempts or 0) + 1

                if user.login_attempts >= Config.MAX_LOGIN_ATTEMPTS:
                    # English implementation note.
                    from src.audit_logger import log_action
                    now_utc = datetime.utcnow()
                    user.locked_until = now_utc + timedelta(minutes=Config.LOCKOUT_MINUTES)
                    user.lock_reason = 'too_many_attempts'
                    user.locked_at = now_utc
                    user.locked_by_id = None
                    user.login_attempts = 0
                    db_session.commit()

                    # English implementation note.
                    try:
                        log_action(user_id_local, "USER_AUTO_LOCKED", "System",
                                  {"username": username, "user_id": user_id_local, "reason": "too_many_attempts", "duration_minutes": Config.LOCKOUT_MINUTES, "until": user.locked_until.isoformat()})
                    except Exception:
                        pass
                else:
                    db_session.commit()
                    # English implementation note.
                    from src.audit_logger import log_action
                    log_action(user_id_local, "LOGIN_FAILED", "System",
                              {"username": username, "user_id": user_id_local, "reason": "incorrect_password"})

            was_locked = user.locked_until is not None

            if error:
                flash(error, 'danger')
            else:
                user.last_login = datetime.utcnow()
                user.login_attempts = 0
                user.locked_until = None
                db_session.commit()

                # English implementation note.
                if was_locked:
                    from src.audit_logger import log_action
                    log_action(user_id_local, "USER_AUTO_UNLOCKED", "System",
                              {"username": username, "user_id": user_id_local, "reason": "lockout_expired"})

                # English implementation note.
                from src.audit_logger import log_action
                log_action(user_id_local, "LOGIN_PASSWORD_VERIFIED", "System", {"username": username, "user_id": user_id_local})

                # English implementation note.
                from src.policy_helpers import get_policy
                mfa_roles = get_policy('mfa.required_roles', default=[])
                role_name = user.role.value if hasattr(user.role, 'value') else str(user.role)

                mfa_required = user.mfa_enabled or (role_name in mfa_roles)

                if mfa_required:
                    if not user.mfa_enabled:
                        # English implementation note.
                        session.clear()
                        session['mfa_setup_user_id'] = user_id_local
                        flash("Multi-factor authentication is required for this role. Set it up to continue.", "warning")
                        return redirect(url_for('auth.mfa_setup'))

                    # English implementation note.
                    session.clear()
                    session['mfa_user_id'] = user_id_local
                    return redirect(url_for('auth.mfa_verify'))

                session.clear()
                session['user_id'] = user_id_local
                session['last_activity'] = datetime.utcnow().isoformat()
                flash('Signed in successfully.', 'success')
                return redirect(url_for('home'))

        if error:
            existing = session.get('_flashes') or []
            if not any(c == 'danger' and m == error for c, m in existing):
                flash(error, 'danger')

    return render_template('auth/login.html')

@auth_bp.route('/logout', methods=('POST',))
def logout():
    """English module documentation."""
    if g.user:
        # English implementation note.
        from src.audit_logger import log_action
        log_action(g.user.id, "LOGOUT", "System", {"username": g.user.username, "user_id": g.user.id})

    session.clear()
    flash('You have been signed out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/mfa/verify', methods=('GET', 'POST'))
def mfa_verify():
    """English module documentation."""
    user_id = session.get('mfa_user_id')
    if not user_id:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        code = request.form.get('code')
        db_session = get_session()
        user = db_session.query(User).get(user_id)

        # English implementation note.
        is_totp_valid = bool(user and user.mfa_secret and code and pyotp.TOTP(user.mfa_secret).verify(code))

        is_backup_valid = False
        if user and not is_totp_valid and user.mfa_backup_codes:
            # English implementation note.
            clean_code = code.strip().upper()
            hashed_list = user.mfa_backup_codes.split(',')
            new_hashed_list = []

            for h in hashed_list:
                if not is_backup_valid and bcrypt.verify(clean_code, h):
                    is_backup_valid = True
                else:
                    new_hashed_list.append(h)

            if is_backup_valid:
                # English implementation note.
                user.mfa_backup_codes = ",".join(new_hashed_list)
                db_session.commit()

        if is_totp_valid or is_backup_valid:
            session.clear()
            session['user_id'] = user.id
            session['last_activity'] = datetime.utcnow().isoformat()

            # English implementation note.
            from src.audit_logger import log_action
            log_type = "MFA_LOGIN_SUCCESS" if is_totp_valid else "BACKUP_CODE_LOGIN"
            log_action(user.id, log_type, "System", {"user_id": user.id})

            flash('Signed in successfully.', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid code. Try again.', 'danger')
            # English implementation note.
            from src.audit_logger import log_action
            log_action(user_id, "MFA_FAILED", "System", {"user_id": user_id, "reason": "invalid_code"})

    return render_template('auth/mfa_verify.html')


@auth_bp.route('/mfa/recovery', methods=('GET', 'POST'))
def mfa_recovery():
    """English module documentation."""
    user_id = session.get('mfa_user_id')
    if not user_id:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        code = request.form.get('code')
        db_session = get_session()
        user = db_session.query(User).get(user_id)

        is_backup_valid = False
        if user and user.mfa_backup_codes:
            clean_code = code.strip().upper()
            hashed_list = user.mfa_backup_codes.split(',')
            new_hashed_list = []

            for h in hashed_list:
                if not is_backup_valid and bcrypt.verify(clean_code, h):
                    is_backup_valid = True
                else:
                    new_hashed_list.append(h)

            if is_backup_valid:
                # English implementation note.
                user.mfa_backup_codes = ",".join(new_hashed_list)
                db_session.commit()

                session.clear()
                session['user_id'] = user.id
                session['last_activity'] = datetime.utcnow().isoformat()

                # English implementation note.
                from src.audit_logger import log_action
                log_action(user.id, "LOGIN_RECOVERY_CODE", "System", {"user_id": user.id})

                flash('Signed in with a recovery code.', 'success')
                return redirect(url_for('home'))

        flash('The recovery code is invalid or has already been used.', 'danger')
        # English implementation note.
        from src.audit_logger import log_action
        log_action(user_id, "MFA_RECOVERY_FAILED", "System", {"user_id": user_id, "reason": "invalid_code"})

    return render_template('auth/mfa_recovery.html')


@auth_bp.route('/mfa/setup', methods=('GET', 'POST'))
def mfa_setup():
    """English module documentation."""
    user_id = session.get('mfa_setup_user_id') or (g.user.id if g.user else None)

    if not user_id:
        return redirect(url_for('auth.login'))

    db_session = get_session()
    user = db_session.query(User).get(user_id)

    if request.method == 'POST':
        code = request.form.get('code')
        secret = session.get('temp_mfa_secret')

        if secret and pyotp.TOTP(secret).verify(code):
            # English implementation note.
            import secrets
            recovery_codes = [secrets.token_hex(4).upper() for _ in range(8)]
            hashed_codes = ",".join([bcrypt.hash(c) for c in recovery_codes])

            user.mfa_secret = secret
            user.mfa_enabled = True
            user.mfa_backup_codes = hashed_codes
            db_session.commit()

            completing_login = not g.user
            session.clear()
            if not g.user:
                session['user_id'] = user.id
                session['last_activity'] = datetime.utcnow().isoformat()

            # English implementation note.
            from src.audit_logger import log_action
            log_action(user.id, "MFA_ENABLED", "User", {"user_id": user.id, "completed_login": completing_login})

            return render_template('auth/mfa_setup.html', success=True, recovery_codes=recovery_codes)
        else:
            flash('Invalid confirmation code. Scan the QR code again.', 'danger')

    if 'temp_mfa_secret' not in session:
        session['temp_mfa_secret'] = pyotp.random_base32()

    secret = session['temp_mfa_secret']
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(name=user.username, issuer_name="Secure Bank Manager")

    # English implementation note.
    img = qrcode.make(provisioning_uri)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    qr_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')

    return render_template('auth/mfa_setup.html', qr_code=qr_base64, secret=secret)


@auth_bp.route('/mfa/disable', methods=('POST',))
@login_required
def mfa_disable():
    """Disable optional MFA while preserving role-mandated MFA."""
    db_session = get_session()
    user = db_session.query(User).get(g.user.id)
    from src.policy import get_policy
    required_roles = set(get_policy("mfa.required_roles", [], session=db_session) or [])
    if user.role.value in required_roles:
        flash('Multi-factor authentication is required for this role.', 'danger')
        return redirect(url_for('profile'))
    user.mfa_enabled = False
    user.mfa_secret = None
    user.mfa_backup_codes = None
    db_session.commit()

    from src.audit_logger import log_action
    log_action(user.id, "MFA_DISABLED", "User", {"user_id": user.id})

    flash('Multi-factor authentication disabled.', 'warning')
    return redirect(url_for('home'))
