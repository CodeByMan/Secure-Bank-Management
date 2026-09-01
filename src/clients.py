"""English module documentation."""

from flask import (
    Blueprint, flash, g, redirect, render_template, request, url_for
)
from src.auth import login_required, permission_required, has_permission
from src.db import get_session
from src.models import Client, Account, ClientStatus, AccountStatus
from src.audit_logger import log_action

clients_bp = Blueprint('clients', __name__, url_prefix='/clients')

@clients_bp.route('/')
@login_required
def index():
    """English module documentation."""
    session = get_session()
    clients = session.query(Client).all()
    client_count = len(clients)

    log_action(g.user.id, "CLIENT_LIST_VIEWED", "Clients",
               {"client_count": client_count})

    return render_template('clients/list.html', clients=clients)

@clients_bp.route('/new', methods=('GET', 'POST'))
@permission_required('clients.create')
def create():
    """English module documentation."""
    if request.method == 'POST':
        last_name = request.form['last_name']
        first_name = request.form['first_name']
        cin = request.form['cin']
        phone = request.form['phone']
        email = request.form.get('email')
        address = request.form['address']

        session = get_session()
        error = None

        # English implementation note.
        if not last_name or not first_name or not cin or not phone:
            error = 'Last name, first name, synthetic identity reference, and phone are required.'
        elif session.query(Client).filter_by(cin=cin).first() is not None:
            # English implementation note.
            error = f'A client with reference {cin} already exists.'

        if error is None:
            new_client = Client(
                last_name=last_name,
                first_name=first_name,
                cin=cin,
                phone=phone,
                email=email,
                address=address
            )
            session.add(new_client)
            session.commit()

            client_id = new_client.id

            # English implementation note.
            log_action(g.user.id, "CLIENT_CREATED", f"Client {client_id}",
                       {"last_name": last_name, "first_name": first_name, "cin": cin})

            flash('Client created.', 'success')
            return redirect(url_for('clients.view', id=client_id))

        flash(error, 'danger')

    return render_template('clients/create.html')

@clients_bp.route('/<int:id>')
@login_required
def view(id):
    """English module documentation."""
    session = get_session()
    client = session.query(Client).filter_by(id=id).first()

    if client is None:
        flash('Client not found.', 'danger')
        return redirect(url_for('clients.index'))

    accounts = session.query(Account).filter_by(client_id=id).all()
    account_count = len(accounts)

    log_action(g.user.id, "CLIENT_VIEWED", f"Client {id}",
               {"client_id": id, "cin": client.cin, "account_count": account_count})

    return render_template('clients/view.html', client=client, accounts=accounts)

@clients_bp.route('/<int:id>/deactivate', methods=('POST',))
@permission_required('clients.deactivate')
def deactivate(id):
    """English module documentation."""
    session = get_session()
    client = session.query(Client).filter_by(id=id).first()

    if client is None:
        flash('Client not found.', 'danger')
        return redirect(url_for('clients.index'))

    # English implementation note.
    open_accounts = [c for c in client.accounts if c.status != AccountStatus.CLOSED]
    if open_accounts:
        flash(f'Status cannot change while {len(open_accounts)} accounts remain active.', 'danger')
        return redirect(url_for('clients.view', id=id))

    try:
        reason = request.form.get('reason', 'Deactivation requested')
        new_status_str = request.form.get('status', 'inactive').upper()

        try:
            new_status = ClientStatus[new_status_str]
        except KeyError:
            new_status = ClientStatus.INACTIVE

        # Fine-grained permission checks depending on requested status
        if new_status == ClientStatus.SUSPENDED and not has_permission(g.user, 'clients.suspend'):
            try:
                log_action(g.user.id if g.user else None, 'ACCESS_DENIED', f"Action on client {client.cin}", {"target_client_id": id, "attempted": "suspend", "path": request.path})
            except Exception:
                pass
            flash('Insufficient permission to suspend a client.', 'danger')
            return redirect(url_for('clients.view', id=id))

        if new_status == ClientStatus.ARCHIVED and not has_permission(g.user, 'clients.archived'):
            try:
                log_action(g.user.id if g.user else None, 'ACCESS_DENIED', f"Action on client {client.cin}", {"target_client_id": id, "attempted": "archived", "path": request.path})
            except Exception:
                pass
            flash('Insufficient permission to archive a client.', 'danger')
            return redirect(url_for('clients.view', id=id))

        # 'inactive' or other deactivations require deactivation permission
        if new_status == ClientStatus.INACTIVE and not has_permission(g.user, 'clients.deactivate'):
            try:
                log_action(g.user.id if g.user else None, 'ACCESS_DENIED', f"Action on client {client.cin}", {"target_client_id": id, "attempted": "deactivate", "path": request.path})
            except Exception:
                pass
            flash('Insufficient permission to deactivate a client.', 'danger')
            return redirect(url_for('clients.view', id=id))

        client.status = new_status
        log_action(g.user.id, "CLIENT_DEACTIVATED", f"Client {id}", {"new_status": new_status.value, "reason": reason})
        session.commit()
        flash(f'Client status changed to {new_status.value}.', 'success')
    except Exception as e:
        session.rollback()
        flash('The request could not be completed.', 'danger')

    return redirect(url_for('clients.view', id=id))


@clients_bp.route('/<int:id>/reactivate', methods=('POST',))
@permission_required('clients.reactivate')
def reactivate(id):
    """English module documentation."""
    session = get_session()
    client = session.query(Client).filter_by(id=id).first()

    if client is None:
        flash('Client not found.', 'danger')
        return redirect(url_for('clients.index'))

    # Permission check (redundant with decorator but explicit for clarity)
    if not has_permission(g.user, 'clients.reactivate'):
        try:
            log_action(g.user.id if g.user else None, 'ACCESS_DENIED', f"Action on client {client.cin}", {"target_client_id": id, "attempted": "reactivate", "path": request.path})
        except Exception:
            pass
        flash('Insufficient permission to reactivate a client.', 'danger')
        return redirect(url_for('clients.view', id=id))

    try:
        reason = request.form.get('reason', 'Administrative reactivation')
        client.status = ClientStatus.ACTIVE
        log_action(g.user.id, "CLIENT_REACTIVATED", f"Client {id}", {"reason": reason})
        session.commit()
        flash('Client reactivated.', 'success')
    except Exception as e:
        session.rollback()
        flash('The request could not be completed.', 'danger')

    return redirect(url_for('clients.view', id=id))
