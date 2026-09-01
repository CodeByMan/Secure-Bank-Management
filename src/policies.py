"""Administrative routes for the authoritative policy service."""

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from src.audit_logger import log_action
from src.auth import has_permission, permission_required
from src.models import PolicyHistory, Policy
from src.policy import canonical_key, set_policy

policies_bp = Blueprint("policies", __name__, url_prefix="/admin/policies")


@policies_bp.route("/")
@permission_required("policies.view")
def index():
    from src.db import session_factory
    session = session_factory()
    try:
        rows = session.query(Policy).order_by(Policy.key).all()
        return render_template("admin/policies.html", policies=rows)
    finally:
        session.close()


@policies_bp.route("/<path:key>", methods=("GET", "POST"))
@permission_required("policies.view")
def edit(key):
    from src.db import serialized_session, session_factory
    key = canonical_key(key)
    if request.method == "POST":
        if not has_permission(g.user, "policies.edit"):
            flash("Insufficient permission to edit policies.", "danger")
            return redirect(url_for("policies.index"))
        try:
            with serialized_session() as session:
                set_policy(
                    key, request.form.get("value", ""), request.form.get("type") or "string",
                    request.form.get("description"), g.user.id, request.form.get("comment"),
                    session=session,
                )
                row = session.query(Policy).filter_by(key=key).first()
                row.active = "active" in request.form
        except ValueError as exc:
            flash(f"Policy validation failed: {exc}", "danger")
            return redirect(url_for("policies.edit", key=key))
        except Exception:
            flash("The policy update could not be completed.", "danger")
            return redirect(url_for("policies.edit", key=key))
        flash("Policy updated.", "success")
        return redirect(url_for("policies.index"))

    session = session_factory()
    try:
        row = session.query(Policy).filter_by(key=key).first()
        history = session.query(PolicyHistory).filter_by(key=key).order_by(
            PolicyHistory.updated_at.desc()).limit(20).all()
        return render_template("admin/policies_edit.html", policy=row, history=history, users_map={})
    finally:
        session.close()


@policies_bp.route("/create", methods=("GET", "POST"))
@permission_required("policies.create")
def create():
    if request.method == "GET":
        return render_template("admin/policies_create.html")
    try:
        set_policy(
            request.form.get("key", ""), request.form.get("value", ""),
            request.form.get("type") or "string", request.form.get("description"),
            g.user.id, request.form.get("comment"),
        )
    except ValueError as exc:
        flash(f"Policy validation failed: {exc}", "danger")
        return render_template("admin/policies_create.html")
    except Exception:
        flash("The policy could not be created.", "danger")
        return render_template("admin/policies_create.html")
    flash("Policy created.", "success")
    return redirect(url_for("policies.index"))


@policies_bp.route("/toggle/<int:id>", methods=("POST",))
@permission_required("policies.toggle")
def toggle(id):
    from src.db import serialized_session
    with serialized_session() as session:
        row = session.get(Policy, id)
        if row is None:
            flash("Policy not found.", "danger")
            return redirect(url_for("policies.index"))
        row.active = not row.active
        log_action(g.user.id, "POLICY_TOGGLED", row.key, {"active": row.active}, session=session)
    flash("Policy state updated.", "success")
    return redirect(url_for("policies.index"))


@policies_bp.route("/apply", methods=("POST",))
@permission_required("policies.apply")
def apply_now():
    flash("Policies are read directly from the authoritative store.", "info")
    return redirect(url_for("policies.index"))

