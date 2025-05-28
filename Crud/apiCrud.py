from Models.Models import Api
from Config.Config import db
from sqlalchemy.exc import SQLAlchemyError
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ApiCRUD:
    
    @staticmethod
    def create_api(api_data):
        """Create a new API"""
        try:
            api = Api(**api_data)
            db.session.add(api)
            db.session.commit()
            return api
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Error creating API: {str(e)}")
            raise

    @staticmethod
    def get_api(api_id):
        """Get API by ID"""
        return Api.query.get(api_id)

    @staticmethod
    def get_all_apis():
        """Get all APIs"""
        return Api.query.all()

    @staticmethod
    def update_api(api_id, update_data):
        """Update API information"""
        try:
            api = Api.query.get(api_id)
            if not api:
                return None

            for key, value in update_data.items():
                setattr(api, key, value)
            
            db.session.commit()
            return api
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Error updating API {api_id}: {str(e)}")
            raise

    @staticmethod
    def delete_api(api_id):
        """Delete an API"""
        try:
            api = Api.query.get(api_id)
            if not api:
                return False
            
            db.session.delete(api)
            db.session.commit()
            return True
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Error deleting API {api_id}: {str(e)}")
            raise