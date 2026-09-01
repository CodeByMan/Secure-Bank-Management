"""English module documentation."""

from flask import (
    Blueprint, flash, g, redirect, render_template, request, url_for, session as flask_session
)
from src.auth import login_required, permission_required
from src.db import get_session
from src.models import User, UserRole, AuditLog
from src.audit_logger import log_action
from passlib.hash import bcrypt
from datetime import datetime, timedelta
from src.config import Config

users_bp = Blueprint('users', __name__, url_prefix='/users')


def _minimum_password_length():
    from src.policy import get_policy
    return int(get_policy('password.minimum_length', 12))


def can_manage_user(current_user, target_user):
    """English module documentation."""
    if current_user.role == UserRole.SUPERADMIN:
        return True

    if current_user.role == UserRole.ADMIN:
        # English implementation note.
        return target_user.role == UserRole.OPERATOR

    return False


def can_create_role(current_user, target_role):
    """English module documentation."""
    if current_user.role == UserRole.SUPERADMIN:
        return True

    if current_user.role == UserRole.ADMIN:
        return target_role == UserRole.OPERATOR

    return False


def get_manageable_roles(current_user):
    """English module documentation."""
    if current_user.role == UserRole.SUPERADMIN:
        return [UserRole.SUPERADMIN, UserRole.ADMIN, UserRole.OPERATOR]

    if current_user.role == UserRole.ADMIN:
        return [UserRole.OPERATOR]

    return []


@users_bp.route('/')
@login_required
def index():
    """English module documentation."""
    if g.user.role == UserRole.OPERATOR:
        log_action(g.user.id, "ACCESS_DENIED", "Listing users", {"path": request.path})
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))

    session_db = get_session()

    # English implementation note.
    if g.user.role == UserRole.SUPERADMIN:
        users = session_db.query(User).order_by(User.id).all()
    else:
        users = session_db.query(User)\
            .filter_by(role=UserRole.OPERATOR)\
            .order_by(User.id)\
            .all()

    nb_users = len(users)
    log_action(g.user.id, "USER_LIST_VIEWED", "Users",
               {"user_count": nb_users, "role_viewer": g.user.role.value})

    users_local = []
    for user in users:
        locked_by_name = None
        if user.locked_by_id:
            lb = session_db.query(User).filter_by(id=user.locked_by_id).first()
            locked_by_name = lb.username if lb else None

        user_dict = {
            'id': user.id,
            'username': user.username,
            'role': user.role,
            'is_active': user.is_active,
            'created_at': user.created_at + timedelta(hours=Config.TIMEZONE_OFFSET_HOURS) if user.created_at else None,
            'last_login': user.last_login + timedelta(hours=Config.TIMEZONE_OFFSET_HOURS) if user.last_login else None,
            'locked_until': user.locked_until,
            'lock_reason': user.lock_reason,
            'locked_by_name': locked_by_name
        }
        users_local.append(type('obj', (object,), user_dict)())

    return render_template('users/list.html', users=users_local)


@users_bp.route('/new', methods=('GET', 'POST'))
@login_required
def create():
    """English module documentation."""
    if g.user.role == UserRole.OPERATOR:
        log_action(g.user.id, "ACCESS_DENIED", "Creating user", {"path": request.path})
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role_str = request.form['role']
        error = None

        if not username:
            error = 'Username is required.'
        elif not password:
            error = 'Password is required.'
        elif len(password) < _minimum_password_length():
            # English implementation note.
            error = f'Password must contain at least {_minimum_password_length()} characters.'

        try:
            role = UserRole(role_str)
            if not can_create_role(g.user, role):
                error = 'You cannot assign that role.'
        except ValueError:
            error = 'Invalid role.'

        if error is None:
            session_db = get_session()
            existing = session_db.query(User).filter_by(username=username).first()
            if existing:
                error = f'User {username} already exists.'
            else:
                try:
                    new_user = User(
                        username=username,
                        password_hash=bcrypt.hash(password),
                        role=role,
                        is_active=True
                    )
                    session_db.add(new_user)
                    session_db.commit()
                    # English implementation note.
                    log_action(g.user.id, "USER_CREATED", f"User {username}",
                               {"role": role.value, "user_id": new_user.id})
                    flash(f'User {username} created.', 'success')
                    return redirect(url_for('users.index'))
                except Exception as e:
                    session_db.rollback()
                    error = "The request could not be completed."

        if error:
            flash(error, 'danger')

    manageable_roles = get_manageable_roles(g.user)
    return render_template('users/create.html', manageable_roles=manageable_roles)


@users_bp.route('/<int:id>')
@login_required
def view(id):
    """English module documentation."""
    session_db = get_session()
    user = session_db.query(User).filter_by(id=id).first()

    if user is None:
        flash('User not found.', 'danger')
        return redirect(url_for('users.index'))

    # English implementation note.
    if not can_manage_user(g.user, user) and g.user.id != user.id:
        log_action(g.user.id, "ACCESS_DENIED", f"Viewing user {user.username}", {"target_user_id": id})
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))

    nb_actions = session_db.query(AuditLog).filter_by(user_id=user.id).count()
    log_action(g.user.id, "USER_VIEWED", f"User {user.username}",
               {"user_id": id, "username": user.username, "role": user.role.value})

    locked_by_user = None
    if user.locked_by_id:
        locked_by_user = session_db.query(User).filter_by(id=user.locked_by_id).first()

    user_local = type('obj', (object,), {
        'id': user.id,
        'username': user.username,
        'role': user.role,
        'is_active': user.is_active,
        'created_at': user.created_at + timedelta(hours=Config.TIMEZONE_OFFSET_HOURS) if user.created_at else None,
        'last_login': user.last_login + timedelta(hours=Config.TIMEZONE_OFFSET_HOURS) if user.last_login else None,
        'locked_until': user.locked_until,
        'lock_reason': user.lock_reason,
        'locked_at': user.locked_at + timedelta(hours=Config.TIMEZONE_OFFSET_HOURS) if user.locked_at else None,
        'login_attempts': user.login_attempts
    })()

    lock_time_local = None
    locked_by_name = None
    if user.locked_until:
        lock_time_local = user.locked_until + timedelta(hours=Config.TIMEZONE_OFFSET_HOURS)
    if locked_by_user:
        locked_by_name = locked_by_user.username

    return render_template('users/view.html', user=user_local, nb_actions=nb_actions,
                            now=datetime.utcnow(), lock_time_local=lock_time_local,
                            locked_by_name=locked_by_name)


@users_bp.route('/<int:id>/edit', methods=('GET', 'POST'))
@login_required
def edit(id):
    """English module documentation."""
    session_db = get_session()
    user = session_db.query(User).filter_by(id=id).first()

    if user is None:
        flash('User not found.', 'danger')
        return redirect(url_for('users.index'))

    if not can_manage_user(g.user, user):
        log_action(g.user.id, "ACCESS_DENIED", f"Action on user {user.username}", {"target_user_id": id, "path": request.path})
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form['username']
        role_str = request.form.get('role')
        error = None

        if not username:
            error = 'Username is required.'

        if role_str:
            try:
                new_role = UserRole(role_str)
                if new_role != user.role:
                    if user.id == g.user.id:
                        # English implementation note.
                        error = 'You cannot change your own role.'
                    elif not can_create_role(g.user, new_role):
                        error = 'You cannot assign that role.'
            except ValueError:
                error = 'Invalid role.'

        if error is None:
            try:
                user.username = username
                if role_str:
                    new_role = UserRole(role_str)
                    if new_role != user.role:
                        old_role = user.role.value
                        user.role = new_role
                        # English implementation note.
                        log_action(g.user.id, "USER_ROLE_UPDATED",
                                   f"User {user.username}",
                                   {"old_role": old_role, "new_role": new_role.value})

                session_db.commit()
                log_action(g.user.id, "USER_UPDATED",
                           f"User {user.username}", {})
                flash(f'User {username} updated.', 'success')
                return redirect(url_for('users.view', id=id))
            except Exception as e:
                session_db.rollback()
                error = "The request could not be completed."

        if error:
            flash(error, 'danger')

    manageable_roles = get_manageable_roles(g.user)
    return render_template('users/edit.html', user=user, manageable_roles=manageable_roles)


@users_bp.route('/<int:id>/toggle-active', methods=('POST',))
@login_required
def toggle_active(id):
    """English module documentation."""
    session_db = get_session()
    user = session_db.query(User).filter_by(id=id).first()

    if user is None:
        flash('User not found.', 'danger')
        return redirect(url_for('users.index'))

    if not can_manage_user(g.user, user):
        log_action(g.user.id, "ACCESS_DENIED", f"Action on user {user.username}", {"target_user_id": id, "path": request.path})
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))

    if user.id == g.user.id:
        flash('You cannot deactivate yourself.', 'danger')
        return redirect(url_for('users.view', id=id))

    try:
        user.is_active = not user.is_active
        session_db.commit()
        # English implementation note.
        action = "USER_ACTIVATED" if user.is_active else "USER_DEACTIVATED"
        log_action(g.user.id, action, f"User {user.username}", {})
        status = "active" if user.is_active else "inactive"
        flash(f'User {user.username} is now {status}.', 'success')
    except Exception as e:
        session_db.rollback()
        flash("The request could not be completed.", 'danger')

    return redirect(url_for('users.view', id=id))


@users_bp.route('/<int:id>/reset-password', methods=('POST',))
@login_required
def reset_password(id):
    """English module documentation."""
    session_db = get_session()
    user = session_db.query(User).filter_by(id=id).first()

    if user is None:
        flash('User not found.', 'danger')
        return redirect(url_for('users.index'))

    if not can_manage_user(g.user, user):
        log_action(g.user.id, "ACCESS_DENIED", f"Action on user {user.username}", {"target_user_id": id, "path": request.path})
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))

    new_password = request.form.get('new_password')
    if not new_password or len(new_password) < _minimum_password_length():
        flash(f'Password must contain at least {_minimum_password_length()} characters.', 'danger')
    else:
        try:
            # English implementation note.
            user.password_hash = bcrypt.hash(new_password)
            session_db.commit()
            log_action(g.user.id, "USER_PASSWORD_RESET", f"User {user.username}", {})
            flash(f'Password for {user.username} was reset.', 'success')
        except Exception as e:
            session_db.rollback()
            flash("The request could not be completed.", 'danger')

    return redirect(url_for('users.view', id=id))


@users_bp.route('/<int:id>/lock', methods=('POST',))
@login_required
def lock_account(id):
    """English module documentation."""
    session_db = get_session()
    user = session_db.query(User).filter_by(id=id).first()

    if user is None:
        flash('User not found.', 'danger')
        return redirect(url_for('users.index'))

    if not can_manage_user(g.user, user):
        log_action(g.user.id, "ACCESS_DENIED", f"Action on user {user.username}", {"target_user_id": id, "path": request.path})
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))

    if user.id == g.user.id:
        flash('You cannot lock yourself.', 'danger')
        return redirect(url_for('users.view', id=id))

    duration_minutes = request.form.get('duration_minutes', type=int)
    reason = request.form.get('reason', 'Manual account lock')

    if not duration_minutes or duration_minutes <= 0:
        flash('Invalid lock duration.', 'danger')
    else:
        try:
            now_utc = datetime.utcnow()
            user.locked_until = now_utc + timedelta(minutes=duration_minutes)
            user.lock_reason = reason
            user.locked_by_id = g.user.id
            user.locked_at = now_utc
            session_db.commit()
            # English implementation note.
            log_action(g.user.id, "USER_MANUALLY_LOCKED",
                       f"User {user.username}",
                       {"duration_minutes": duration_minutes, "until": user.locked_until.isoformat(), "reason": reason})

            unlock_local = user.locked_until + timedelta(hours=Config.TIMEZONE_OFFSET_HOURS)
            flash(f"User {user.username} is locked until {unlock_local.strftime('%Y-%m-%d %H:%M')}.", 'success')
        except Exception as e:
            session_db.rollback()
            flash("The request could not be completed.", 'danger')

    return redirect(url_for('users.view', id=id))


@users_bp.route('/<int:id>/unlock', methods=('POST',))
@login_required
def unlock_account(id):
    """English module documentation."""
    session_db = get_session()
    user = session_db.query(User).filter_by(id=id).first()

    if user is None:
        flash('User not found.', 'danger')
        return redirect(url_for('users.index'))

    if not can_manage_user(g.user, user):
        log_action(g.user.id, "ACCESS_DENIED", f"Action on user {user.username}", {"target_user_id": id, "path": request.path})
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))

    if user.locked_until is None:
        flash('The account is not locked.', 'danger')
        return redirect(url_for('users.view', id=id))

    try:
        was_locked_until = user.locked_until.isoformat()
        user.locked_until = None
        user.lock_reason = None
        user.locked_by_id = None
        user.locked_at = None
        user.login_attempts = 0
        session_db.commit()
        log_action(g.user.id, "USER_MANUALLY_UNLOCKED",
                   f"User {user.username}",
                   {"was_locked_until": was_locked_until})
        flash(f'User {user.username} was unlocked.', 'success')
    except Exception as e:
        session_db.rollback()
        flash("The request could not be completed.", 'danger')

    return redirect(url_for('users.view', id=id))


@users_bp.route('/profile', methods=('GET','POST'))
@login_required
def profile():
    """English module documentation."""
    session_db = get_session()
    user = session_db.query(User).filter_by(id=g.user.id).first()

    if user is None:
        flash('User not found.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'update_profile':
            new_display = request.form.get('display_name', '').strip()
            if len(new_display) > 100:
                flash('The display name is too long.', 'danger')
            else:
                user.display_name = new_display or None
                session_db.commit()
                flash('Profile updated.', 'success')
        elif action == 'change_password':
            current = request.form.get('current_password', '')
            new = request.form.get('new_password', '')
            confirm = request.form.get('confirm_password', '')
            # English implementation note.
            if not bcrypt.verify(current, user.password_hash):
                flash('Current password is incorrect.', 'danger')
            elif len(new) < _minimum_password_length():
                flash(f'The new password must contain at least {_minimum_password_length()} characters.', 'danger')
            elif new != confirm:
                flash('New passwords do not match.', 'danger')
            else:
                user.password_hash = bcrypt.hash(new)
                session_db.commit()
                # English implementation note.
                log_action(g.user.id, "PROFILE_PASSWORD_CHANGED", "Profile", {})
                flash('Password changed.', 'success')

    user_local = type('obj', (object,), {
        'username': user.username,
        'display_name': user.display_name,
        'mfa_enabled': user.mfa_enabled,
        'created_at': user.created_at + timedelta(hours=Config.TIMEZONE_OFFSET_HOURS) if user.created_at else None,
        'last_login': user.last_login + timedelta(hours=Config.TIMEZONE_OFFSET_HOURS) if user.last_login else None
    })()

    return render_template('users/profile.html', user=user_local)
