from Models.Models import UserApiKey, UserApiKeyPermission
from Config.Config import db
from datetime import datetime, timedelta
from sqlalchemy.exc import SQLAlchemyError
import logging
import secrets
import string

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ApiKeyCRUD:
    
    @staticmethod
    def generate_api_key(length=32):
        """Generate a random API key"""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    @staticmethod
    def create_api_key(user_id, key_name=None, expires_in_days=None, permissions=None):
        """Create a new API key for a user"""
        try:
            expires_at = None
            if expires_in_days:
                expires_at = datetime.utcnow() + timedelta(days=expires_in_days)

            api_key = UserApiKey(
                user_id=user_id,
                api_key=ApiKeyCRUD.generate_api_key(),
                name=key_name,
                expires_at=expires_at,
                is_active=True
            )
            
            db.session.add(api_key)
            db.session.flush()  # Ensure api_key.id is available

            if permissions:
                for api_id in permissions:
                    permission = UserApiKeyPermission(
                        api_key_id=api_key.id,
                        api_id=api_id
                    )
                    db.session.add(permission)

            db.session.commit()
            return api_key
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Error creating API key for user {user_id}: {str(e)}")
            raise

    @staticmethod
    def get_api_key(key_id):
        """Get API key by ID"""
        return UserApiKey.query.get(key_id)

    @staticmethod
    def get_user_api_keys(user_id):
        """Get all API keys for a user"""
        return UserApiKey.query.filter_by(user_id=user_id).all()

    @staticmethod
    def validate_api_key(api_key_str):
        """Validate an API key and return the user if valid"""
        api_key = UserApiKey.query.filter_by(api_key=api_key_str).first()
        if not api_key or not api_key.is_active:
            return None
        
        if api_key.expires_at and api_key.expires_at < datetime.utcnow():
            return None
            
        return api_key.user

    @staticmethod
    def update_api_key(key_id, update_data):
        """Update API key information"""
        try:
            api_key = UserApiKey.query.get(key_id)
            if not api_key:
                return None

            for key, value in update_data.items():
                setattr(api_key, key, value)
            
            db.session.commit()
            return api_key
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Error updating API key {key_id}: {str(e)}")
            raise

    @staticmethod
    def delete_api_key(key_id):
        """Delete an API key"""
        try:
            api_key = UserApiKey.query.get(key_id)
            if not api_key:
                return False
            
            db.session.delete(api_key)
            db.session.commit()
            return True
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Error deleting API key {key_id}: {str(e)}")
            raise

    @staticmethod
    def add_api_key_permission(key_id, api_id):
        """Add permission for an API key to access a specific API"""
        try:
            existing = UserApiKeyPermission.query.filter_by(
                api_key_id=key_id,
                api_id=api_id
            ).first()
            
            if existing:
                return existing
                
            permission = UserApiKeyPermission(
                api_key_id=key_id,
                api_id=api_id
            )
            
            db.session.add(permission)
            db.session.commit()
            return permission
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Error adding permission to key {key_id} for API {api_id}: {str(e)}")
            raise

    @staticmethod
    def remove_api_key_permission(key_id, api_id):
        """Remove permission for an API key to access a specific API"""
        try:
            permission = UserApiKeyPermission.query.filter_by(
                api_key_id=key_id,
                api_id=api_id
            ).first()
            
            if not permission:
                return False
                
            db.session.delete(permission)
            db.session.commit()
            return True
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Error removing permission from key {key_id} for API {api_id}: {str(e)}")
            raise