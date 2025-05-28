from Models.Models import User
from Config.Config import db
from sqlalchemy.exc import SQLAlchemyError
import logging
import bcrypt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UserCRUD:
    
    @staticmethod
    def hash_password(password):
        """Hash a password using bcrypt"""
        try:
            # Convert password to bytes if it's a string
            if isinstance(password, str):
                password = password.encode('utf-8')
            
            # Generate salt and hash the password
            salt = bcrypt.gensalt()
            hashed = bcrypt.hashpw(password, salt)
            
            # Return as string for database storage
            return hashed.decode('utf-8')
        except Exception as e:
            logger.error(f"Error hashing password: {str(e)}")
            raise

    @staticmethod
    def verify_password(password, hashed_password):
        """Verify a password against its hash"""
        try:
            # Convert to bytes if they're strings
            if isinstance(password, str):
                password = password.encode('utf-8')
            if isinstance(hashed_password, str):
                hashed_password = hashed_password.encode('utf-8')
            
            # Verify the password
            return bcrypt.checkpw(password, hashed_password)
        except Exception as e:
            logger.error(f"Error verifying password: {str(e)}")
            return False

    @staticmethod
    def create_user(user_data):
        """Create a new user"""
        try:
            user = User(**user_data)
            db.session.add(user)
            db.session.commit()
            return user
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Error creating user: {str(e)}")
            raise

    @staticmethod
    def get_user_by_id(user_id):
        """Get user by ID"""
        return User.query.get(user_id)

    @staticmethod
    def get_user_by_email(email):
        """Get user by email"""
        return User.query.filter_by(email=email).first()

    @staticmethod
    def get_user_by_username(username):
        """Get user by username"""
        return User.query.filter_by(username=username).first()

    @staticmethod
    def update_user(user_id, update_data):
        """Update user information"""
        try:
            user = User.query.get(user_id)
            if not user:
                return None

            for key, value in update_data.items():
                setattr(user, key, value)
            
            db.session.commit()
            return user
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Error updating user {user_id}: {str(e)}")
            raise

    @staticmethod
    def delete_user(user_id):
        """Delete a user and all associated data"""
        try:
            user = User.query.get(user_id)
            if not user:
                return False

            db.session.delete(user)
            db.session.commit()
            return True
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Error deleting user {user_id}: {str(e)}")
            raise