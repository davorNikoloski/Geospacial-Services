from Config.Config import db
from datetime import datetime

class User(db.Model):
    __tablename__ = 'users'
    u_id = db.Column('u_id', db.Integer, primary_key=True)
    u_username = db.Column('u_username', db.String(255), unique=True)
    u_email = db.Column('u_email', db.String(255), unique=True, nullable=False)
    u_phonenumber = db.Column('u_phonenumber', db.String(255), unique=True, nullable=False)
    u_firstname = db.Column('u_firstname', db.String(255), nullable=False)
    u_lastname = db.Column('u_lastname', db.String(255), nullable=False)
    u_password = db.Column('u_password', db.String(255), nullable=False)
    u_avatar = db.Column('u_avatar', db.String(255), default='default_avatar.png')
    u_utid = db.Column('u_utid', db.Integer, nullable=False)
    u_authenticated = db.Column('u_authenticated', db.Boolean, default=False)
    u_created_at = db.Column('u_created_at', db.DateTime, default=datetime.utcnow)
    u_modified_at = db.Column('u_modified_at', db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    u_archived = db.Column('u_archived', db.Boolean, default=False)
    u_did = db.Column('u_did', db.Integer, db.ForeignKey('departments.d_id'), nullable=True)
    u_vehicle_id = db.Column('u_vehicle_id', db.Integer, db.ForeignKey('vehicles.v_id'), nullable=True)

# Define relationships
    password_resets = db.relationship('PasswordReset', backref='related_user', lazy=True)
    verifications = db.relationship('UserVerification', backref=db.backref('related_user', lazy=True))
    
class UserType(db.Model):
    __tablename__ = 'user_types'
    ut_id = db.Column('ut_id', db.Integer, primary_key=True)
    ut_name = db.Column('ut_name', db.String(255))

class PasswordReset(db.Model):
    __tablename__ = 'password_resets'
    pr_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    pr_user_id = db.Column(db.Integer, db.ForeignKey('users.u_id'), nullable=False)
    pr_reset_token = db.Column(db.String(255), nullable=False, unique=True)
    pr_expires_at = db.Column(db.DateTime, nullable=False)

    related_user = db.relationship('User', backref=db.backref('password_resets', lazy=True))
    
