"""English module documentation."""

from flask import (
    Blueprint, flash, g, redirect, render_template, request, url_for
)
from src.auth import login_required, permission_required
from src.db import get_session
from src.models import Client, Account, Operation, OperationType, AccountStatus, generate_account_number
from src.config import Config
from src.audit_logger import log_action
from decimal import Decimal

accounts_bp = Blueprint('accounts', __name__, url_prefix='/accounts')

@accounts_bp.route('/new/<int:client_id>', methods=('GET', 'POST'))
@permission_required('accounts.create')
def create(client_id):
    """English module documentation."""
    session = get_session()
    client = session.query(Client).filter_by(id=client_id).first()

    if client is None:
        flash('Client not found.', 'danger')
        return redirect(url_for('clients.index'))

    # English implementation note.
    client_status = client.status.value
    if client_status != 'active':
        flash(f'Action unavailable for client status: {client_status}.', 'danger')
        return redirect(url_for('clients.view', id=client_id))

    if request.method == 'POST':
        opening_amount = request.form['opening_amount']
        error = None

        try:
            amount = Decimal(opening_amount)
            # English implementation note.
            if amount < Config.MINIMUM_OPENING_BALANCE:
                error = f'The opening deposit must be at least {Config.MINIMUM_OPENING_BALANCE} {Config.CURRENCY}.'
        except:
            error = 'Invalid amount.'

        if error is None:
            try:
                # English implementation note.
                new_account = Account(
                    account_number=generate_account_number(),
                    client_id=client.id,
                    balance=amount,
                    status=AccountStatus.ACTIVE
                )
                session.add(new_account)
                session.flush()

                # English implementation note.
                operation = Operation(
                    account_id=new_account.id,
                    user_id=g.user.id,
                    operation_type=OperationType.DEPOSIT,
                    amount=amount,
                    balance_before=0,
                    balance_after=amount,
                    description="Opening deposit"
                )
                session.add(operation)

                # English implementation note.
                log_action(g.user.id, "ACCOUNT_CREATED", f"Account {new_account.account_number}",
                           {"client_id": client.id, "opening_deposit": str(amount)}, session=session)

                session.commit()
                flash('Account created.', 'success')
                return redirect(url_for('clients.view', id=client.id))

            except Exception as e:
                session.rollback()
                error = "The request could not be completed."

        if error is not None:
            flash(error, 'danger')

    result = render_template('accounts/create.html', client=client, config=Config)
    return result

@accounts_bp.route('/<account_number>')
@login_required
def view(account_number):
    """English module documentation."""
    session = get_session()
    account = session.query(Account).filter_by(account_number=account_number).first()

    if account is None:
        flash('Account not found.', 'danger')
        return redirect(url_for('clients.index'))

    client_id = account.client_id
    operations = session.query(Operation).filter_by(account_id=account.id).order_by(Operation.operation_date.desc()).all()
    operation_count = len(operations)

    # English implementation note.
    log_action(g.user.id, "ACCOUNT_VIEWED", f"Account {account.account_number}",
               {"account_id": account.id, "account_number": account.account_number,
                "client_id": client_id, "operation_count": operation_count})

    response = render_template('accounts/view.html', account=account, client_id=client_id, operations=operations)
    return response

@accounts_bp.route('/<int:id>/close', methods=('POST',))
@permission_required('accounts.close')
def close(id):
    """English module documentation."""
    session = get_session()
    account = session.query(Account).filter_by(id=id).first()

    if account is None:
        flash('Account not found.', 'danger')
        return redirect(url_for('clients.index'))

    if account.balance != 0:
        flash('An account with a positive balance cannot be closed.', 'danger')
        return redirect(url_for('accounts.view', account_number=account.account_number))

    reason = request.form.get('reason', 'Client request')
    client_id = account.client_id

    try:
        account.status = AccountStatus.CLOSED
        # English implementation note.
        log_action(g.user.id, "ACCOUNT_CLOSED", f"Account {account.account_number}",
                   {"reason": reason}, session=session)
        session.commit()
        flash('Account closed.', 'success')
    except Exception as e:
        session.rollback()
        flash('The request could not be completed.', 'danger')

    return redirect(url_for('clients.view', id=client_id))


@accounts_bp.route('/<int:id>/reopen', methods=('POST',))
@permission_required('accounts.close')
def reopen(id):
    """English module documentation."""
    session = get_session()
    account = session.query(Account).filter_by(id=id).first()

    if account is None:
        flash('Account not found.', 'danger')
        return redirect(url_for('clients.index'))

    if account.status.value != 'closed':
        flash('The account is not closed.', 'danger')
        return redirect(url_for('accounts.view', account_number=account.account_number))

    # English implementation note.
    holder_status = account.client.status.value
    if holder_status != 'active':
        flash(f'Action unavailable for fictional client status: {holder_status}.', 'danger')
        return redirect(url_for('accounts.view', account_number=account.account_number))

    reason = request.form.get('reason', 'Administrative decision')
    account_id = account.id

    try:
        account.status = AccountStatus.ACTIVE
        # English implementation note.
        log_action(g.user.id, "ACCOUNT_REOPENED", f"Account {account.account_number}",
                   {"reason": reason}, session=session)
        session.commit()
        flash('Account reopened.', 'success')
    except Exception as e:
        session.rollback()
        flash('The request could not be completed.', 'danger')

    return redirect(url_for('accounts.view', account_number=account.account_number))
